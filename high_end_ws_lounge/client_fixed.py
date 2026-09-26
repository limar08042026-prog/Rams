"""
client.py
Contains all client-facing blueprints: auth, main, and api.
"""

import os
import logging
from datetime import datetime, timedelta
import pytz
import stripe

from database_fixed import (
    db,
    Room,
    User,
    TimeLog,
    SoloPlan,
    LoginForm,
    Membership,
    PaymentInfo,
    ProfileForm,
    Reservation,
    AttendanceLog,
    UserActivityLog,
    ReservationForm,
    RegistrationForm,
    ChangePasswordForm,
    generate_customer_id,
    get_user_by_email,
    mail,
)
from flask import (
    flash,
    jsonify,
    request,
    session,
    url_for,
    redirect,
    Blueprint,
    current_app,
    render_template,
)
from sqlalchemy import and_, func, or_
from werkzeug.utils import secure_filename
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer


# Auth Blueprint
auth_bp = Blueprint("auth", __name__)
main_bp = Blueprint('main', __name__, template_folder='templates')


def _customer_hidden_attendance_ids():
    return {
        int(log_id)
        for log_id in session.get("customer_hidden_attendance_ids", [])
        if str(log_id).isdigit()
    }


def _save_customer_hidden_attendance_ids(log_ids):
    session["customer_hidden_attendance_ids"] = sorted(log_ids)
    session.modified = True


@main_bp.route("/api/customer/attendance/<int:log_id>/delete", methods=["DELETE"])
@login_required
def delete_customer_attendance(log_id):
    log = (
        AttendanceLog.query
        .join(Membership)
        .filter(AttendanceLog.id == log_id, Membership.user_id == current_user.id)
        .first()
    )
    if not log:
        return jsonify({"success": False, "message": "Attendance record not found."}), 404

    hidden_ids = _customer_hidden_attendance_ids()
    hidden_ids.add(log.id)
    _save_customer_hidden_attendance_ids(hidden_ids)
    return jsonify({"success": True, "message": "Attendance record removed."})


@main_bp.route("/api/customer/attendance/clear-all", methods=["DELETE"])
@login_required
def clear_customer_attendance():
    membership_ids = [
        membership.id
        for membership in Membership.query.filter_by(user_id=current_user.id).all()
    ]
    if membership_ids:
        log_ids = db.session.query(AttendanceLog.id).filter(
            AttendanceLog.membership_id.in_(membership_ids)
        ).all()
        _save_customer_hidden_attendance_ids({log_id for (log_id,) in log_ids})
    else:
        _save_customer_hidden_attendance_ids(set())

    return jsonify({"success": True, "message": "All attendance history cleared."})


def get_custom_tier_rate(room_name, pax_count, default_base_rate):
    if not room_name:
        return default_base_rate

    room_name_lower = room_name.lower()
    pax = pax_count or 1

    if "lecture room" in room_name_lower:
        if 1 <= pax <= 5:
            return 150.0
        elif 6 <= pax <= 10:
            return 200.0
        elif 11 <= pax <= 15:
            return 250.0
    elif "event room" in room_name_lower:
        if 1 <= pax <= 15:
            return 300.0
        elif 16 <= pax <= 30:
            return 400.0
        else:
            return 500.0
        

    return float(default_base_rate or 0.0)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        return redirect(url_for("main.index", show_login="true"))

    form = LoginForm(meta={"csrf": False})
    if form.validate():
        email = form.email.data.strip().lower()
        user = get_user_by_email(email)
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password", "danger")
            return redirect(url_for("main.index", show_login="true"))
        if not user.is_active:
            flash("Access Restricted: Account is inactive. Contact your administrator.", "danger")
            return redirect(url_for("main.index", show_login="true"))
        login_user(user, remember=form.remember_me.data)
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        next_page = request.args.get("next")
        return redirect(next_page or url_for("main.dashboard"))

    flash("Please enter valid credentials and try again.", "danger")
    return redirect(url_for("main.index", show_login="true"))


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_user_by_email(email)

        if user:
            serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
            token = serializer.dumps(user.email, salt="reset-password-salt")
            reset_url = url_for("auth.reset_password", token=token, _external=True)

            try:
                msg = Message(
                    subject="WS Lounge - Password Reset Request",
                    recipients=[email],
                    body=(
                        f"Hello {user.name or 'Member'},\n\n"
                        "A password reset was requested for your WS Lounge account.\n\n"
                        "Please click the link below to reset your password. "
                        "This link is valid for 30 minutes:\n\n"
                        f"{reset_url}\n\n"
                        "If you did not request a password reset, please ignore this email.\n\n"
                        "WS Students & Professionals Lounge"
                    ),
                )
                mail.send(msg)

                flash(
                    "A password reset link has been sent to your email. Please check your inbox or spam folder.",
                    "success"
                )

            except Exception:
                logging.exception("Password reset mail delivery failed for %s", email)
                flash("Failed to send password reset email. Please try again later.", "danger")

        else:
            flash(
                "If that email address is registered, a password reset link has been sent to your inbox.",
                "info"
            )

        return redirect(url_for("auth.forgot_password"))

    return render_template("forgot_password.html")


@auth_bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        email = serializer.loads(token, salt="reset-password-salt", max_age=1800)
    except Exception:
        flash("The password reset link is invalid or has expired. Please try requesting a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = get_user_by_email(email)
    if not user:
        flash("User account not found.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if not new_password or new_password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return render_template("reset_password.html", token=token)

        user.set_password(new_password) 
        db.session.commit()

        flash("Your password has been reset successfully! You can now log in with your new password.", "success")
        return redirect(url_for("main.index", show_login="true"))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "GET":
        return redirect(url_for("main.index", show_register="true"))

    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered. Please login or use a different email.", "danger")
            return redirect(url_for("main.index", show_register="true"))
        
        try:
            user = User(name=form.name.data, email=email, phone=form.phone.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash("Registration failed. Please try again with a different email.", "danger")
            return redirect(url_for("main.index", show_register="true"))
        
        flash("Account created successfully! Please log in with your credentials.", "success")
        return redirect(url_for("main.index", show_login="true"))

    flash("Please complete all required fields correctly.", "danger")
    return redirect(url_for("main.index", show_register="true"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_role", None)
    return redirect(url_for("main.index"))


def get_admin_stats():
    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz)

    total_members = User.query.filter_by(role="member").count()
    active_timelogs = (
        db.session.query(TimeLog).filter(TimeLog.time_out.is_(None)).count()
    )
    
    # Calculate today's boundary based on PHT
    today_start = ph_tz.localize(datetime(now.year, now.month, now.day))
    today_end = today_start + timedelta(days=1)

    res_today = (
        Reservation.query.filter(
            Reservation.start_time >= today_start,
            Reservation.start_time < today_end,
            Reservation.status == "Confirmed",
        ).count()
    )
    
    revenue_today = (
        db.session.query(func.sum(Reservation.total_amount))
        .filter(
            Reservation.start_time >= today_start,
            Reservation.start_time < today_end,
            Reservation.status == "Confirmed",
        )
        .scalar()
        or 0
    )
    
    return total_members, active_timelogs, res_today, revenue_today

@auth_bp.app_context_processor
def inject_member_notifications():
    if current_user.is_authenticated and current_user.role == "member":

        # Membership approval notifications
        unread_approval_count = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.ilike("approved"),
            SoloPlan.member_notification_seen == False
        ).count()

        # Membership renewal notifications
        unread_renewal_count = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.ilike("approved"),
            SoloPlan.renewal_notification_seen == False
        ).count()

        # Confirmed room reservation notifications
        unread_reservation_notification_count = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            Reservation.status.ilike("confirmed"),
            Reservation.confirmation_notification_seen == False
        ).count()

        unread_membership_notification_count = (
            unread_approval_count + unread_renewal_count
        )

        return dict(
            unread_membership_notification_count=unread_membership_notification_count,
            unread_reservation_notification_count=unread_reservation_notification_count
        )

    return dict(
        unread_membership_notification_count=0,
        unread_reservation_notification_count=0
    )

@main_bp.route("/api/notifications/membership/read", methods=["POST"])
@login_required
def mark_membership_notifications_read():
    if current_user.role != "member":
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 403

    approval_updated = SoloPlan.query.filter(
        SoloPlan.user_id == current_user.id,
        SoloPlan.status.ilike("approved"),
        SoloPlan.member_notification_seen == False
    ).update(
        {"member_notification_seen": True},
        synchronize_session=False
    )

    renewal_updated = SoloPlan.query.filter(
        SoloPlan.user_id == current_user.id,
        SoloPlan.status.ilike("approved"),
        SoloPlan.renewal_notification_seen == False
    ).update(
        {"renewal_notification_seen": True},
        synchronize_session=False
    )

    db.session.commit()

    return jsonify({
        "status": "success",
        "user_id": current_user.id,
        "approval_updated": approval_updated,
        "renewal_updated": renewal_updated
    })


@main_bp.route("/api/notifications/reservations/read", methods=["POST"])
@login_required
def mark_reservation_notifications_read():
    if current_user.role != "member":
        return jsonify({
            "status": "error",
            "message": "Unauthorized"
        }), 403

    Reservation.query.filter(
        Reservation.user_id == current_user.id,
        Reservation.status.ilike("confirmed"),
        Reservation.confirmation_notification_seen == False
    ).update(
        {"confirmation_notification_seen": True},
        synchronize_session=False
    )

    db.session.commit()

    return jsonify({
        "status": "success"
    })


def _expire_membership_if_needed(membership):
    if not membership or membership.status != 'active' or not membership.expiry_date:
        return

    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz)
    
    expiry_dt = membership.expiry_date
    if expiry_dt.tzinfo is None:
        expiry_dt = ph_tz.localize(expiry_dt)

    if now >= expiry_dt:
        membership.status = 'expired'
        membership.hours_left = 0.0
        membership.is_checked_in = False
        
        # FIX: Force reset is_paused para indi mag-stuck sa "Session Paused" badge
        if hasattr(membership, 'is_paused'):
            membership.is_paused = False

        active_log = membership.attendance_logs.filter(AttendanceLog.check_out_time.is_(None)).first()
        if active_log:
            # Check-out time set to expiry date
            active_log.check_out_time = membership.expiry_date
            
            # Synchronize active_log dates for subtraction if needed
            check_in = active_log.check_in_time
            check_out = active_log.check_out_time
            
            if check_in.tzinfo is None:
                check_in = ph_tz.localize(check_in)
            if check_out.tzinfo is None:
                check_out = ph_tz.localize(check_out)

            # Calculate exact hours deducted
            time_diff = check_out - check_in
            active_log.hours_deducted = round(time_diff.total_seconds() / 3600, 2)

        db.session.commit()


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    login_form = LoginForm()
    register_form = RegistrationForm()
    show_register = request.args.get("show_register", "false").lower() == "true"
    show_login = request.args.get("show_login", "false").lower() == "true"

    return render_template(
        "landing.html",
        login_form=login_form,
        register_form=register_form,
        show_register=show_register,
        show_login=show_login,
    )

@main_bp.route("/dashboard")
@login_required
def dashboard():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    now_naive = now_ph.replace(second=0, microsecond=0, tzinfo=None)

    reservations = (
        Reservation.query.filter_by(user_id=current_user.id)
        .order_by(Reservation.created_at.desc())
        .limit(10)
        .all()
    )
    active_reservation = Reservation.query.filter(
        Reservation.user_id == current_user.id,
        func.lower(Reservation.status).in_(
            ["in_progress", "paused", "confirmed", "pending", "checked-in"]
        ),
        Reservation.start_time >= now_naive,
    ).order_by(Reservation.start_time.asc()).first()
    if not active_reservation:
        active_reservation = Reservation.query.filter(
            Reservation.user_id == current_user.id,
            func.lower(Reservation.status).in_(
                ["in_progress", "paused", "confirmed", "pending", "checked-in"]
            ),
            Reservation.start_time <= now_naive,
            or_(
                Reservation.end_time.is_(None),
                Reservation.end_time >= now_naive,
                Reservation.is_open_time.is_(True),
            ),
        ).order_by(Reservation.start_time.desc()).first()
    latest_log = (
        TimeLog.query.filter_by(user_id=current_user.id)
        .order_by(TimeLog.time_in.desc())
        .first()
    )

    if current_user.role in ["admin", "staff"]:
        return redirect(url_for("admin.dashboard"))

    # 1. Fetch Membership Data
    membership = Membership.query.filter(
        Membership.user_id == current_user.id,
        func.lower(Membership.status).in_(["active", "approved", "pending_checkin"]),
    ).order_by(Membership.updated_at.desc(), Membership.id.desc()).first()
    attendance_logs = []
    remaining_days = None
    all_user_attendance_logs = AttendanceLog.query.join(Membership).filter(
        Membership.user_id == current_user.id
    ).all()
    total_solo_plans = len(all_user_attendance_logs)

    if membership:
        _expire_membership_if_needed(membership)
        hidden_attendance_ids = _customer_hidden_attendance_ids()
        attendance_logs = (
            AttendanceLog.query.filter_by(membership_id=membership.id)
            .filter(~AttendanceLog.id.in_(hidden_attendance_ids) if hidden_attendance_ids else True)
            .order_by(AttendanceLog.check_in_time.desc())
            .limit(20)
            .all()
        )
        if membership.expiry_date:
            expiry_dt = membership.expiry_date
            if expiry_dt.tzinfo is None:
                expiry_dt = ph_tz.localize(expiry_dt)

            diff = expiry_dt - now_ph
            if diff.total_seconds() > 0:
                remaining_days = max(round(diff.total_seconds() / 86400, 1), 0)
            else:
                remaining_days = 0

    # 2. Fetch Solo Plans
    solo_plans = (
        SoloPlan.query.filter_by(user_id=current_user.id)
        .order_by(SoloPlan.created_at.desc())
        .limit(5)
        .all()
    )

    # Membership approval and renewal notifications
    membership_notifications = (
        SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.ilike("approved"),
            or_(
                SoloPlan.member_notification_seen == False,
                SoloPlan.renewal_notification_seen == False
            )
        )
        .order_by(
            func.coalesce(
                SoloPlan.renewed_at,
                SoloPlan.approved_at,
                SoloPlan.created_at
            ).desc()
        )
        .limit(10)
        .all()
    )

    unread_membership_notification_count = 0

    for plan in membership_notifications:
        if not plan.member_notification_seen:
            unread_membership_notification_count += 1

        if plan.renewed_at and not plan.renewal_notification_seen:
            unread_membership_notification_count += 1
            

    # CALCULATE TOTAL SOLO HOURS (Safe Join & Status Check)
    try:
        all_user_solo_plans = SoloPlan.query.join(Membership).filter(
            Membership.user_id == current_user.id
        ).all()
    except Exception:
        all_user_solo_plans = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id
        ).all()


    active_membership = Membership.query.filter(
        Membership.user_id == current_user.id,
        Membership.status.ilike("active")
    ).first()

    user_logs = []
    is_checked_in = False

    if active_membership:
        user_logs = AttendanceLog.query.filter_by(
            membership_id=active_membership.id
        ).order_by(AttendanceLog.check_in_time.desc()).all()
        
        if user_logs and user_logs[0].check_in_time and not user_logs[0].check_out_time:
            is_checked_in = True

    total_consumed_seconds = sum(
        (log.check_out_time - log.check_in_time).total_seconds()
        for log in all_user_attendance_logs
        if log.check_in_time and log.check_out_time
    )
    total_solo_hours = round(total_consumed_seconds / 3600.0, 1)

    # Strict Attendance Log & Is_Checked_In Validation para sa Active Session
    open_log = None
    if membership:
        open_log = AttendanceLog.query.filter_by(
            membership_id=membership.id,
            check_out_time=None
        ).first()

    is_user_checked_in = (membership and membership.is_checked_in) or (open_log is not None)

    is_session_paused = False
    if is_user_checked_in:
        if open_log and getattr(open_log, 'is_paused', False):
            is_session_paused = True
        elif membership and getattr(membership, 'is_paused', False):
            is_session_paused = True

    active_solo = None
    if is_user_checked_in:
        active_solo = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.ilike("approved"),
            SoloPlan.status.notin_(["checked_out", "checked-out", "completed"])
        ).order_by(SoloPlan.created_at.desc()).first()

    active_session = None
    if is_user_checked_in:
        if active_solo:
            active_session = active_solo
        elif membership:
            active_session = membership
        else:
            active_session = open_log

    is_reservation_paused = bool(
        active_reservation and (
            getattr(active_reservation, 'is_paused', False)
            or str(getattr(active_reservation, 'status', '') or '').strip().upper() == 'PAUSED'
        )
    )

    return render_template(
        "dashboard/member_dashboard.html",
        reservations=reservations,
        active_plan=active_session,
        active_session=active_session,
        active_reservation=active_reservation,
        is_reservation_paused=is_reservation_paused,
        remaining_days=remaining_days,
        solo_plans=solo_plans,
        total_solo_plans=total_solo_plans,
        total_solo_hours=total_solo_hours,
        membership=membership,
        attendance_logs=attendance_logs,
        now_ph=now_ph,
        is_session_paused=is_session_paused,
        membership_notifications=membership_notifications,
        unread_membership_notification_count=unread_membership_notification_count
    )


@main_bp.route("/api/user-active-reservation", methods=["GET"])
@login_required
def user_active_reservation():
    now_naive = datetime.now(pytz.timezone("Asia/Manila")).replace(
        second=0, microsecond=0, tzinfo=None
    )
    reservation = Reservation.query.filter(
        Reservation.user_id == current_user.id,
        func.lower(Reservation.status).in_(
            ["in_progress", "paused", "confirmed", "pending", "checked-in"]
        ),
        or_(
            Reservation.start_time >= now_naive,
            and_(
                Reservation.start_time <= now_naive,
                or_(
                    Reservation.end_time.is_(None),
                    Reservation.end_time >= now_naive,
                    Reservation.is_open_time.is_(True),
                ),
            ),
        ),
    ).order_by(Reservation.start_time.asc()).first()

    if not reservation:
        return jsonify({"has_active": False})

    is_paused = bool(
        getattr(reservation, "is_paused", False)
        or str(getattr(reservation, "status", "") or "").strip().upper() == "PAUSED"
    )

    return jsonify({
        "has_active": True,
        "id": reservation.id,
        "status": "PAUSED" if is_paused else (reservation.status or "IN_PROGRESS"),
        "is_paused": is_paused,
        "room_name": reservation.room.name if reservation.room else "Common Area",
        "start_time": reservation.start_time.isoformat() if reservation.start_time else None,
        "end_time": reservation.end_time.isoformat() if reservation.end_time else None,
        "is_open_time": bool(reservation.is_open_time),
    })


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile_form = ProfileForm(obj=current_user)
    password_form = ChangePasswordForm()

    if request.method == "POST" and request.form.get("profile_submit") is not None:
        if profile_form.validate_on_submit():
            email = profile_form.email.data.strip().lower()
            existing_user = User.query.filter(func.lower(User.email) == email).first()
            if existing_user and existing_user.id != current_user.id:
                profile_form.email.errors.append("Email already in use by another account.")
            else:
                current_user.name = profile_form.name.data.strip()
                current_user.email = email
                current_user.phone = profile_form.phone.data.strip() or None
                db.session.commit()
                flash("Profile updated successfully.", "success")
                return redirect(url_for("main.profile"))

    if request.method == "POST" and request.form.get("password_submit") is not None:
        if password_form.validate_on_submit():
            if not current_user.check_password(password_form.current_password.data):
                password_form.current_password.errors.append("Current password is incorrect.")
            elif password_form.new_password.data != password_form.confirm_password.data:
                password_form.confirm_password.errors.append("Passwords do not match.")
            else:
                current_user.set_password(password_form.new_password.data)
                db.session.commit()
                flash("Password changed successfully.", "success")
                return redirect(url_for("main.profile"))

    return render_template("profile.html", profile_form=profile_form, password_form=password_form)


@main_bp.route("/rooms", methods=["GET", "POST"])
@login_required
def rooms():
    ph_tz = pytz.timezone("Asia/Manila")

    form = ReservationForm()
    rooms = Room.query.filter(~Room.name.ilike('Test Room%')).order_by(Room.id).all()

    now_ph = datetime.now(ph_tz).replace(tzinfo=None)

    active_occupied_reservations = Reservation.query.filter(
        Reservation.room_id.isnot(None),
        Reservation.status.in_(["Confirmed", "Occupied", "Walk-in", "Pending", "Checked-in"]),
        Reservation.start_time <= now_ph,
        or_(
            Reservation.end_time >= now_ph,
            Reservation.is_open_time == True
        )
    ).all()

    room_pax_count = {}
    occupied_room_ids = set()

    for res in active_occupied_reservations:
        if res.room_id:
            occupied_room_ids.add(res.room_id)
            room_pax_count[res.room_id] = room_pax_count.get(res.room_id, 0) + (res.pax_count or 1)

    available_rooms = []
    for r in rooms:
        if r.status and r.status.lower() == "available":
            if "common area" in r.name.lower():
                max_capacity = getattr(r, 'capacity', 70) or 70
                current_pax = room_pax_count.get(r.id, 0)
                if current_pax < max_capacity:
                    available_rooms.append(r)
            else:
                if r.id not in occupied_room_ids:
                    available_rooms.append(r)

    selected_room_id = None
    try:
        selected_room_id = int(form.room_id.data) if form.room_id.data is not None else None
    except (TypeError, ValueError):
        selected_room_id = None

    if selected_room_id is not None:
        selected_room = Room.query.get(selected_room_id)
        if selected_room and selected_room.id not in {room.id for room in available_rooms}:
            available_rooms.append(selected_room)

    available_rooms = sorted(available_rooms, key=lambda room: room.id)
    
    form.room_id.choices = [
        (room.id, f"{room.name} - ₱{room.base_rate}/hr") for room in available_rooms
    ]

    payment_info = {
        info.method: {
            "account_number": info.account_number,
            "account_name": info.account_name,
            "qr_image": url_for("static", filename=f"uploads/payment/{info.qr_image}") if info.qr_image else None,
            "instructions": info.instructions,
        }
        for info in PaymentInfo.query.all()
    }

    bookings = (
        db.session.query(
            Reservation.start_time, Reservation.end_time, Reservation.status, Room.name
        )
        .join(Room)
        .filter(
            Reservation.status == "Confirmed",
            ~Room.name.ilike('Test Room%'),
            or_(
                Reservation.end_time >= now_ph,
                Reservation.is_open_time == True
            )
        )
        .order_by(Reservation.start_time)
        .all()
    )

    if form.validate_on_submit() and current_user.role == "member":
        payment_method = request.form.get("payment_method", "")
        receipt_file = request.files.get("receipt_image")

        # 1. KUHAON ANG ROOM KAG PAX COUNT GIKAN SA FORM
        room_id = form.room_id.data
        selected_room_obj = Room.query.get(room_id)
        
        # Kuhaon ang pax_count gikan sa form (default sa 1 kon wala)
        pax_count = request.form.get("pax_count", type=int) or 1

        # 2. DYNAMIC PAX-TIER RATE LOGIC
        base_rate = float(selected_room_obj.base_rate) if selected_room_obj else 0.0

        if selected_room_obj:
            room_name_lower = selected_room_obj.name.lower()
            
            if "lecture room" in room_name_lower:
                if 1 <= pax_count <= 5:
                    base_rate = 150.0
                elif 6 <= pax_count <= 10:
                    base_rate = 200.0
                elif 11 <= pax_count <= 15:
                    base_rate = 250.0
            elif "event room" in room_name_lower:
                if 1 <= pax_count <= 10:
                    base_rate = 300.0
                elif 11 <= pax_count <= 20:
                    base_rate = 400.0
                elif pax_count > 20:
                    base_rate = 500.0

        room = Room.query.get(form.room_id.data)
        start_time = form.start_time.data
        end_time = form.end_time.data
        
        # Reliable Open Time Check halin sa Request Form o WTForm
        is_open_time_val = request.form.get("is_open_time")
        is_open_time = True if (is_open_time_val in ["true", "True", "1", 1] or form.is_open_time.data) else False

        if payment_method not in ["GCash", "Maya"]:
            flash("Please select GCash or Maya as payment method.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        if not receipt_file or receipt_file.filename == "":
            flash("Please upload your payment receipt for verification.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.jpe', '.gif', '.webp', '.pdf'}
        original_name = receipt_file.filename or ''
        ext = os.path.splitext(original_name)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            flash("Unsupported receipt file type. Allowed: PNG, JPG, JPEG, JPE, GIF, WEBP, PDF.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)
        
        receipt_file.seek(0, os.SEEK_END)
        size = receipt_file.tell()
        receipt_file.seek(0)
        max_bytes = 5 * 1024 * 1024

        if size > max_bytes:
            flash("Receipt file too large (max 5MB).", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        if not room:
            flash("Please select a valid room.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        # Validation Check
        if not end_time and not is_open_time:
            flash("Please choose a valid reservation end time.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        # Force end_time to None kon Open Time
        if is_open_time:
            end_time = None

        room_name_lower = (room.name or "").strip().lower()
        is_common_area = "common area" in room_name_lower

        pax_count_val = form.pax_count.data or 1
        if "lecture room" in room_name_lower and pax_count_val > 15:
            flash("Lecture Room capacity is limited to a maximum of 15 persons only.", "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        if not is_common_area:
            reservation_conflict_query = Reservation.query.filter(
                Reservation.room_id == room.id,
                Reservation.status.in_(["Confirmed", "APPROVED", "Pending", "Walk-in", "Checked-in"]),
            )
            if end_time is None:
                reservation_conflict_query = reservation_conflict_query.filter(
                    or_(
                        Reservation.end_time.is_(None),
                        Reservation.end_time > start_time,
                    )
                )
            else:
                reservation_conflict_query = reservation_conflict_query.filter(
                    Reservation.start_time < end_time,
                    or_(
                        Reservation.end_time.is_(None),
                        Reservation.end_time > start_time,
                    ),
                )

            reservation_conflict = reservation_conflict_query.first()
            if reservation_conflict:
                conflict_end = (
                    reservation_conflict.end_time.strftime('%I:%M %p')
                    if reservation_conflict.end_time
                    else "open time"
                )
                flash(
                    f"Time Conflict: Reserved until {conflict_end}",
                    "danger",
                )
                return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        if is_common_area:
            # Common Area Capacity Check - bypass strict room overlap validation by using shared-space capacity logic instead.
            check_end = end_time if end_time else (start_time + timedelta(hours=12))
            overlapping_reservations = Reservation.query.filter(
                Reservation.room_id == form.room_id.data,
                Reservation.status.in_(["Confirmed", "Pending", "Walk-in", "Checked-in"]),
                or_(
                    Reservation.end_time > start_time,
                    Reservation.is_open_time == True
                )
            ).all()

            current_booked_pax = sum(r.pax_count or 1 for r in overlapping_reservations)
            requested_pax = form.pax_count.data or 1
            max_capacity = getattr(room, 'capacity', 70) or 70

            if (current_booked_pax + requested_pax) > max_capacity:
                flash("Common Area reached maximum capacity for selected schedule.", "danger")
                return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)
        else:
            conflict = Reservation.check_conflict(
                room_id=form.room_id.data,
                start_dt=start_time,
                end_dt=end_time
            )

            if conflict:
                flash("Room unavailable for selected time.", "danger")
                return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        # Safe Amount Calculation (1 Hour base rate minimum rate for Open Time initial payment)
        if is_open_time or not end_time:
            hours = 1.0
        else:
            hours = (end_time - start_time).total_seconds() / 3600

        hourly_rate = get_custom_tier_rate(room.name, pax_count_val, room.base_rate)

        total = max(hourly_rate * hours, hourly_rate)

        extra_fee_total = 0.0
        try:
            extra_fee_total = float(request.form.get('extra_fee_total', 0) or 0)
        except ValueError:
            extra_fee_total = 0.0

        total = round(total + extra_fee_total, 2)
        
        payment_type = form.payment_type.data if hasattr(form, 'payment_type') else "Downpayment"
        if payment_type == "Full Payment":
            amount_paid = round(total, 2)
        else:
            amount_paid = round(total * 0.5, 2)

        try:
            customer_id = generate_customer_id(
                "common area" if room.name.strip().lower() == "common area" else "other"
            )
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("rooms.html", rooms=rooms, bookings=bookings, form=form, payment_info=payment_info, occupied_room_ids=occupied_room_ids, room_pax_count=room_pax_count)

        now_timestamp = int(datetime.now(ph_tz).timestamp())
        filename = secure_filename(
            f"receipt_{current_user.id}_{now_timestamp}_{receipt_file.filename}"
        )
        upload_folder = os.path.join(current_app.root_path, "static/uploads/receipts")
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        receipt_file.save(file_path)

        # Clean Reservation Creation
        reservation = Reservation(
            user_id=current_user.id,
            customer_id=customer_id,
            room_id=form.room_id.data,
            customer_name=form.customer_name.data,
            contact_number=form.contact_number.data,
            pax_count=form.pax_count.data,
            start_time=start_time,
            end_time=end_time, # Will save as NULL/None if Open Time!
            is_open_time=is_open_time,
            status="Pending",
            added_by=current_user.name,
            extra_notes=form.extra_notes.data,
            extra_fee=extra_fee_total,
            total_amount=total,
            amount_paid=amount_paid,
            payment_method=payment_method,
            payment_type=form.payment_type.data,
            receipt_image=filename,
            paid=False,
        )
        db.session.add(reservation)
        db.session.commit()
        
        flash(
            "Reservation created and payment receipt uploaded. Awaiting admin approval.",
            "success",
        )
        return redirect(url_for("main.rooms"))
    
    unread_confirmed_reservations = Reservation.query.filter(
        Reservation.user_id == current_user.id,
        Reservation.status.ilike("confirmed"),
        Reservation.confirmation_notification_seen == False
    ).order_by(
        Reservation.start_time.desc()
    ).limit(5).all()

    return render_template(
        "rooms.html",
        rooms=rooms,
        bookings=bookings,
        form=form,
        payment_info=payment_info,
        occupied_room_ids=occupied_room_ids,
        room_pax_count=room_pax_count,
        unread_confirmed_reservations=unread_confirmed_reservations

    )


@main_bp.route("/timelog")
@login_required
def timelog():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    now_naive = now_ph.replace(second=0, microsecond=0, tzinfo=None)
    month_start = ph_tz.localize(datetime(now_ph.year, now_ph.month, 1))

    # 1. FETCH MEMBERSHIP & ATTENDANCE LOGS
    membership = Membership.query.filter_by(user_id=current_user.id).first()

    # 2. DYNAMIC ACTIVE SESSION CHECK (Checked-In Validation)
    open_log = None
    if membership:
        open_log = AttendanceLog.query.filter_by(
            membership_id=membership.id,
            check_out_time=None
        ).first()

    # Dapa checked in gid man sa Membership flag O may nabilin nga open AttendanceLog
    is_checked_in = (membership and membership.is_checked_in) or (open_log is not None)

    active_session = None
    if is_checked_in:
        active_solo = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.ilike("approved"),
            SoloPlan.expiry_date > now_naive,
            SoloPlan.status.notin_(["checked_out", "checked-out", "completed"])
        ).order_by(SoloPlan.id.desc()).first()

        if active_solo:
            active_session = active_solo
        elif membership and membership.expiry_date and membership.expiry_date > now_naive and membership.status not in ["checked_out", "completed"]:
            active_session = membership

    logs = []
    completed_sessions_count = 0
    total_time_all = 0
    total_time_month = 0
    today_logs = 0
    plan_counts = {}

    # 3. COMPUTE ATTENDANCE LOGS (If exists)
    if membership:
        raw_logs = (
            AttendanceLog.query.filter_by(membership_id=membership.id)
            .order_by(AttendanceLog.check_in_time.desc())
            .limit(10)
            .all()
        )

        for l in raw_logs:
            check_in = l.check_in_time
            if check_in and check_in.tzinfo is None:
                check_in = ph_tz.localize(check_in)

            if l.check_out_time:
                check_out = l.check_out_time
                if check_out.tzinfo is None:
                    check_out = ph_tz.localize(check_out)
                duration_hours = l.session_duration_hours or ((check_out - check_in).total_seconds() / 3600)
            else:
                duration_hours = max((now_ph - check_in).total_seconds() / 3600, 0)

            p_name = membership.plan_name or 'INDIVIDUAL RATE'
            plan_counts[p_name] = plan_counts.get(p_name, 0) + 1

            logs.append({
                'time_in': check_in,
                'time_out': l.check_out_time,
                'status': 'Ended' if l.check_out_time else 'Active',
                'plan': p_name,
                'total_time': int(duration_hours * 60),
            })

        completed_sessions_count = AttendanceLog.query.filter(
            AttendanceLog.membership_id == membership.id,
            AttendanceLog.check_out_time != None
        ).count()

        all_attendance_logs = AttendanceLog.query.filter_by(membership_id=membership.id).all()

        for log in all_attendance_logs:
            c_in = log.check_in_time
            if c_in and c_in.tzinfo is None:
                c_in = ph_tz.localize(c_in)

            if log.check_out_time:
                c_out = log.check_out_time
                if c_out.tzinfo is None:
                    c_out = ph_tz.localize(c_out)
                dur = (c_out - c_in).total_seconds() / 3600
            else:
                dur = max((now_ph - c_in).total_seconds() / 3600, 0)

            dur_minutes = int(dur * 60)
            total_time_all += dur_minutes

            if c_in >= month_start:
                total_time_month += dur_minutes

            if c_in.date() == now_ph.date():
                today_logs += dur_minutes

    # 4. COMPUTE SOLO PLANS (If Attendance Logs are empty or to complement history)
    solo_history = SoloPlan.query.filter_by(user_id=current_user.id).order_by(SoloPlan.created_at.desc()).all()
    
    for sp in solo_history:
        p_name = sp.plan_name or 'INDIVIDUAL RATE'
        plan_counts[p_name] = plan_counts.get(p_name, 0) + 1

        if not logs:  # Populated lang kun wala pa ma-populate sang AttendanceLog
            is_ended = sp.status in ['completed', 'ended', 'checked_out'] or (sp.expiry_date and sp.expiry_date <= now_naive)
            logs.append({
                'time_in': getattr(sp, 'created_at', None) or getattr(sp, 'start_time', None),
                'time_out': sp.expiry_date if is_ended else None,
                'status': 'Ended' if is_ended else 'Active',
                'plan': p_name,
                'total_time': 0,
            })

    if not membership and solo_history:
        completed_sessions_count = SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status.in_(['completed', 'ended', 'checked_out'])
        ).count()

    most_frequent_plan = db.session.query(
        SoloPlan.plan_name, 
        func.count(SoloPlan.id).label('plan_count')
    ).filter(
        SoloPlan.user_id == current_user.id
    ).group_by(
        SoloPlan.plan_name
    ).order_by(
        db.desc('plan_count')
    ).first()

    if most_frequent_plan:
        most_used_room = most_frequent_plan.plan_name
    else:
        # Fallback sa plan_counts dict kon walang query match
        most_used_room = max(plan_counts, key=plan_counts.get) if plan_counts else "None"

    # CALCULATE AVG SESSION LENGTH (Safe Join sa Membership)
    all_user_logs = AttendanceLog.query.join(Membership).filter(
        Membership.user_id == current_user.id
    ).all()

    completed_session_minutes = []
    for log in all_user_logs:
        c_in = getattr(log, 'check_in_time', None)
        c_out = getattr(log, 'check_out_time', None)

        if c_in and c_out:
            diff_seconds = (c_out - c_in).total_seconds()
            if diff_seconds > 0:
                completed_session_minutes.append(diff_seconds / 60)
        elif getattr(log, 'duration_minutes', 0) and getattr(log, 'duration_minutes', 0) > 0:
            completed_session_minutes.append(float(log.duration_minutes))
        elif getattr(log, 'duration', 0) and getattr(log, 'duration', 0) > 0:
            completed_session_minutes.append(float(log.duration))

    if len(completed_session_minutes) > 0:
        avg_session_length = round(sum(completed_session_minutes) / len(completed_session_minutes))
    else:
        avg_session_length = 0

    totals = {
        "all_time_minutes": total_time_all,
        "month_time_minutes": total_time_month,
        "today_time_minutes": today_logs,
        "plan_totals": plan_counts,
        "most_used_room": most_used_room,
        "avg_session_length": avg_session_length
    }

    return render_template(
        "timelog.html",
        logs=logs[:10],
        current_plan=membership,
        totals=totals,
        active_session=active_session,
        completed_sessions=completed_sessions_count
    )


@main_bp.route("/timein", methods=["POST"])
@login_required
def time_in():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    
    active = (
        TimeLog.query.filter_by(user_id=current_user.id)
        .filter(TimeLog.time_out.is_(None))
        .first()
    )
    if active:
        flash("You are already timed in. Time out first.", "warning")
        return redirect(url_for("main.timelog"))

    approved_plan = (
        SoloPlan.query.filter(
            SoloPlan.user_id == current_user.id,
            SoloPlan.status == "approved",
            SoloPlan.expiry_date > now_ph.replace(tzinfo=None),
        )
        .order_by(SoloPlan.created_at.desc())
        .first()
    )

    if not approved_plan:
        flash(
            "No active approved solo plan found. Please select, get approval, and check expiry.",
            "danger",
        )
        return redirect(url_for("main.solo_rates"))

    timelog = TimeLog(
        user_id=current_user.id,
        plan=approved_plan.plan_name,
        time_in=now_ph,
    )
    db.session.add(timelog)
    db.session.commit()
    flash(f"Timed in with {approved_plan.plan_name}!", "success")
    return redirect(url_for("main.timelog"))


@main_bp.route("/timeout", methods=["POST"])
@login_required
def time_out():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    active = (
        TimeLog.query.filter_by(user_id=current_user.id)
        .filter(TimeLog.time_out.is_(None))
        .first()
    )
    if not active:
        flash("No active time session found. Time in first.", "warning")
        return redirect(url_for("main.timelog"))

    # Synchronize active.time_in timezone if naive
    time_in_dt = active.time_in
    if time_in_dt and time_in_dt.tzinfo is None:
        time_in_dt = ph_tz.localize(time_in_dt)

    # Calculate exact duration in minutes based on PHT
    duration_seconds = (now_ph - time_in_dt).total_seconds()
    duration = max(int(duration_seconds / 60), 0)

    active.time_out = now_ph.replace(tzinfo=None)
    active.total_time = duration
    db.session.commit()

    flash(f"Timed out. Session duration: {duration} minutes", "info")
    return redirect(url_for("main.timelog"))

@main_bp.route("/reservations")
@login_required
def reservations():
    if current_user.role != "member":
        flash("Members only")
        return redirect(url_for("main.dashboard"))

    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    reservations = (
        db.session.query(Reservation)
        .join(Room)
        .filter(Reservation.user_id == current_user.id)
        .order_by(Reservation.start_time.desc())
        .all()
    )

    for res in reservations:
        end_time_dt = res.end_time
        if end_time_dt and end_time_dt.tzinfo is None:
            end_time_dt = ph_tz.localize(end_time_dt)
        
        # Attach dynamic property for template rendering if needed
        res.is_past = end_time_dt < now_ph if end_time_dt else False

    return render_template("reservations.html", reservations=reservations)


@main_bp.route("/get_time_inside")
@login_required
def get_time_inside():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    latest = (
        TimeLog.query.filter_by(user_id=current_user.id)
        .order_by(TimeLog.time_in.desc())
        .first()
    )

    if latest and latest.time_out is None:
        # Localize time_in if timezone-naive
        time_in_dt = latest.time_in
        if time_in_dt.tzinfo is None:
            time_in_dt = ph_tz.localize(time_in_dt)

        # Compute exact elapsed seconds based on PHT
        diff = int((now_ph - time_in_dt).total_seconds())
        diff = max(diff, 0)  # Prevent negative values

        return jsonify({"status": "inside", "seconds": diff})

    return jsonify({"status": "outside", "seconds": 0})


@main_bp.route("/solo_rates", methods=["GET", "POST"])
@login_required
def solo_rates():
    if current_user.role != "member":
        flash("Unauthorized. Members only.", "warning")
        return redirect(url_for("main.dashboard"))

    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    now_naive = now_ph.replace(tzinfo=None)

    plans = Plan.query.all() if 'Plan' in globals() else []

    # Check attendance / check-in flag sang membership
    membership_record = Membership.query.filter_by(user_id=current_user.id).first()
    
    open_log = None
    if membership_record:
        open_log = AttendanceLog.query.filter_by(
            membership_id=membership_record.id,
            check_out_time=None
        ).first()

    # User is only considered checked-in if flag is true or open log exists
    is_user_checked_in = (membership_record and membership_record.is_checked_in) or (open_log is not None)

    active_membership = None
    if is_user_checked_in:
        active_membership = (
            Membership.query.filter(
                Membership.user_id == current_user.id,
                Membership.status.ilike("active"),
                Membership.status.notin_(["checked_out", "checked-out", "completed"]),
                Membership.expiry_date > now_naive
            )
            .order_by(Membership.start_date.desc())
            .first()
        )

    active_plan = active_membership
    remaining_days = expiration = None
    session_start = None

    if active_plan and active_plan.expiry_date:
        expiration = active_plan.expiry_date
        if expiration.tzinfo is None:
            expiration = ph_tz.localize(expiration)

        diff = expiration - now_ph
        remaining_days = round(diff.total_seconds() / 86400, 1) if diff.total_seconds() > 0 else 0

    if open_log and open_log.check_in_time:
        session_start = open_log.check_in_time
        if session_start.tzinfo is None:
            session_start = ph_tz.localize(session_start)

    active_solo_plan = None
    if is_user_checked_in:
        active_solo_plan = (
            SoloPlan.query.filter(
                SoloPlan.user_id == current_user.id,
                SoloPlan.status.ilike("approved"),
                SoloPlan.expiry_date > now_naive,
                SoloPlan.status.notin_(["checked_out", "checked-out", "completed", "CHECKED_OUT"])
            )
            .order_by(SoloPlan.created_at.desc())
            .first()
        )

    plans = [
        {
            "title": "INDIVIDUAL RATE",
            "price": "P35/HR",
            "details": ["Hourly common area usage", "WiFi / Charging"],
        },
        {
            "title": "INDIVIDUAL RATE (4HRS)",
            "price": "P100",
            "details": ["4hrs common area usage", "WiFi & Charging"],
        },
        {
            "title": "DAY/NIGHT PASS",
            "price": "P200",
            "details": [
                "Choice of Day (7AM – 10PM) or Night (6PM – 9AM) common area usage",
                "WiFi & Charging",
            ],
        },
        {
            "title": "WEEKLY PASS (DAY/NIGHT)",
            "price": "P800",
            "details": [
                "1 Week (7DAYS) common area usage",
                "Choice of Day (7AM – 10PM) or Night (6PM – 9AM)",
                "WiFi & Charging",
                "Gold Card",
            ],
        },
        {
            "title": "WEEKLY PASS (24HRS)",
            "price": "P1000",
            "details": [
                "1 Week (7DAYS) common area usage",
                "24/7 Usage",
                "WiFi & Charging",
                "Platinum Card",
            ],
        },
        {
            "title": "MONTHLY PASS (DAY/NIGHT)",
            "price": "P1999",
            "details": [
                "1 Month (30 DAYS) unlimited common area usage",
                "Choice of Day (7AM – 10PM) or Night (6PM – 9AM)",
                "WiFi, Charging & Exclusive Locker",
                "Gold Card",
            ],
        },
        {
            "title": "MONTHLY PASS (24HRS)",
            "price": "P2500",
            "details": [
                "24/7 Access to All Branches in Iloilo",
                "1 Month (30 days) unlimited common area usage",
                "WiFi & Charging, Exclusive Locker",
                "1hr Sleeping pod & Shower Room use per day (City Proper Branch only)",
                "Platinum Card",
            ],
        },
        {
            "title": "WORKSTATION (24HRS)",
            "price": "P3000",
            "details": [
                "24/7 Access to dedicated Workstation (Lapaz)",
                "24/7 Common area access to all Branches",
                "1 Dedicated Workstation",
                "WiFi & Charging & Exclusive Locker",
                "1hr Sleeping pod & Shower Room use per day (City Proper Branch only)",
                "Platinum Card",
            ],
        },
    ]

    has_pending = (
        SoloPlan.query.filter_by(user_id=current_user.id, status="pending").first()
        is not None
    )

    message = None
    if request.method == "POST":
        selected_plan = request.form.get("plan_name")
        if selected_plan:
            if active_plan or active_solo_plan:
                flash(
                    "You currently have an active plan. Please wait for it to expire before purchasing a new one.",
                    "warning",
                )
            elif has_pending:
                flash(
                    "You already have a pending plan application. Please wait for admin approval.",
                    "warning",
                )
            else:
                try:
                    customer_id = generate_customer_id("monthly")
                except ValueError as e:
                    flash(str(e), "danger")
                    return redirect(url_for("main.solo_rates"))

                solo_plan = SoloPlan(
                    user_id=current_user.id,
                    customer_id=customer_id,
                    plan_name=selected_plan,
                    status="pending",
                    created_at=now_naive,
                )
                db.session.add(solo_plan)
                db.session.commit()

                message = (
                    f"Plan '{selected_plan}' selected! Waiting for admin approval. Your plan ID is: {customer_id}"
                )
                flash(message, "success")

    return render_template(
        "solo_rates.html",
        plans=plans,
        active_plan=active_plan,
        remaining_days=remaining_days,
        expiration=expiration,
        session_start=session_start,
        message=message,
        active_solo_plan=active_solo_plan,
        has_pending=has_pending,
    )

# API Blueprint
api_bp = Blueprint("api", __name__)


@api_bp.route('/payment-info')
def payment_info():
    payment_data = {
        info.method: {
            'account_name': info.account_name,
            'account_number': info.account_number,
            'qr_image': url_for('static', filename=f'uploads/payment/{info.qr_image}') if info.qr_image else None,
            'instructions': info.instructions,
        }
        for info in PaymentInfo.query.all()
    }
    return jsonify(payment_data)


@api_bp.route("/stats")
def stats():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    total_members = User.query.filter_by(role="member").count()
    active_plans = (
        db.session.query(TimeLog).filter(TimeLog.time_out.is_(None)).count()
    )

    today_start = ph_tz.localize(datetime(now_ph.year, now_ph.month, now_ph.day))
    today_end = today_start + timedelta(days=1)

    res_today = Reservation.query.filter(
        Reservation.start_time >= today_start,
        Reservation.start_time < today_end,
        Reservation.status == "Confirmed",
    ).count()

    revenue_today = (
        db.session.query(func.sum(Reservation.total_amount))
        .filter(
            Reservation.start_time >= today_start,
            Reservation.start_time < today_end,
            Reservation.status == "Confirmed",
        )
        .scalar()
        or 0
    )

    return jsonify(
        {
            "total_members": total_members,
            "active_timelogs": active_plans,
            "reservations_today": res_today,
            "revenue_today": float(revenue_today),
        }
    )


@api_bp.route("/submit-solo-payment", methods=["POST"])
@login_required
def submit_solo_payment():
    """Handle GCash/Maya Receipt Uploads for Solo Plans"""
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    plan_name = request.form.get('plan_name')
    payment_method = request.form.get('payment_method')
    receipt_file = request.files.get('receipt_image')

    if not receipt_file or not plan_name:
        return jsonify({'success': False, 'message': 'Missing data or receipt.'}), 400

    allowed_ext = ['.png', '.jpg', '.jpeg', '.jpe', '.webp', '.gif', '.pdf']
    original_name = receipt_file.filename or ''
    ext = os.path.splitext(original_name)[1].lower() or '.png'

    if ext not in allowed_ext:
        return jsonify({'success': False, 'message': 'Unsupported file type.'}), 400

    receipt_file.seek(0, os.SEEK_END)
    size = receipt_file.tell()
    receipt_file.seek(0)
    if size > 5 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'File too large (max 5MB).'}), 400

    mimetype = receipt_file.mimetype or ''
    if ext == '.pdf':
        if mimetype != 'application/pdf':
            return jsonify({'success': False, 'message': 'Uploaded file is not a valid PDF.'}), 400
    else:
        if not mimetype.startswith('image/'):
            return jsonify({'success': False, 'message': 'Uploaded file is not a valid image.'}), 400

    try:
        timestamp = int(now_ph.timestamp())
        filename = secure_filename(f"receipt_{current_user.id}_{timestamp}{ext}")
        upload_folder = os.path.join(current_app.root_path, 'static/uploads/receipts')
        
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        file_path = os.path.join(upload_folder, filename)
        receipt_file.save(file_path)

        # Generate Customer ID for the Solo Plan
        customer_id = generate_customer_id("monthly") 

        new_plan = SoloPlan(
            user_id=current_user.id,
            customer_id=customer_id,
            plan_name=plan_name,
            status="pending",
            receipt_image=filename, 
            payment_method=payment_method,
            created_at=now_ph
        )
        
        db.session.add(new_plan)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Payment submitted for verification.'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@api_bp.route("/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    from database_fixed import Config
    stripe.api_key = Config.STRIPE_SECRET_KEY
    
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    data = request.json or {}
    amount = int(data.get('amount', 0) * 100)
    plan_name = data.get('plan_name', 'Reservation')
    customer_email = current_user.email
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'php',
                    'product_data': {
                        'name': f"{plan_name} Payment"
                    },
                    'unit_amount': amount,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('main.solo_rates', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('main.solo_rates', _external=True),
            customer_email=customer_email,
            metadata={
                'user_id': current_user.id, 
                'plan': plan_name,
                'created_at_pht': now_ph.strftime('%Y-%m-%d %H:%M:%S'),
                'timestamp_pht': int(now_ph.timestamp())
            }
        )
        return jsonify({'id': session.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@main_bp.route("/checkout_solo_plan", methods=["POST"])
@login_required
def checkout_solo_plan():
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    now_naive = now_ph.replace(second=0, microsecond=0, tzinfo=None)

    # 1. Update Membership Check-in status
    membership = Membership.query.filter_by(user_id=current_user.id).first()
    if membership:
        
        membership.is_checked_in = False
        membership.is_checked_out = True

        if membership.status and membership.status.lower() in ["checked in", "checked_in", "paused", "session paused", "session_paused"]:
            membership.status = "active" if membership.hours_left > 0 else "expired"

        membership.updated_at = now_ph

        # Close open attendance log
        open_log = AttendanceLog.query.filter(
            AttendanceLog.membership_id == membership.id,
            AttendanceLog.check_out_time.is_(None)
        ).order_by(AttendanceLog.check_in_time.desc()).first()

        if open_log:
            open_log.check_out_time = now_naive
            c_in = open_log.check_in_time
            if c_in and c_in.tzinfo is None:
                c_in = ph_tz.localize(c_in)
            dur_hours = max((now_ph - c_in).total_seconds() / 3600, 0) if c_in else 0.0
            open_log.hours_deducted = round(dur_hours, 2)

    user_plans = SoloPlan.query.filter(
        SoloPlan.user_id == current_user.id,
        SoloPlan.status.in_(["Approved", "approved", "APPROVED", "Pending", "pending"])
    ).all()

    for plan in user_plans:
        plan.status = "checked_out"

    db.session.commit()
    flash("Successfully checked out!", "success")
    return redirect(url_for("main.solo_rates"))

@api_bp.route("/membership/status", methods=["GET"])
@login_required
def membership_status():
    """Get current user's membership status"""
    ph_tz = pytz.timezone("Asia/Manila")

    membership = Membership.query.filter(
        Membership.user_id == current_user.id,
        func.lower(Membership.status).in_(["active", "approved", "pending_checkin"]),
    ).order_by(Membership.updated_at.desc(), Membership.id.desc()).first()
    
    if not membership:
        return jsonify({"status": "error", "message": "No membership found"})

    _expire_membership_if_needed(membership)

    member_status = "PAUSED" if getattr(membership, "is_paused", False) else (
        "CHECKED_IN" if membership.is_checked_in else "NOT_CHECKED_IN"
    )
    remaining_seconds = max(0, int(float(membership.hours_left or 0) * 3600))
    elapsed_seconds = 0
    active_log = AttendanceLog.query.filter_by(
        membership_id=membership.id,
        check_out_time=None
    ).order_by(AttendanceLog.check_in_time.desc()).first()
    if active_log and active_log.check_in_time and membership.is_checked_in:
        check_in_time = active_log.check_in_time
        if check_in_time.tzinfo is None:
            check_in_time = ph_tz.localize(check_in_time)
        reference_time = datetime.now(ph_tz)
        is_paused = bool(getattr(membership, "is_paused", False) or getattr(active_log, "is_paused", False))
        paused_at = getattr(active_log, "paused_at", None) or getattr(membership, "paused_at", None)
        if is_paused and paused_at:
            if paused_at.tzinfo is None:
                paused_at = ph_tz.localize(paused_at)
            reference_time = paused_at
        accumulated_paused = (
            getattr(active_log, "accumulated_paused_seconds", 0)
            or getattr(membership, "accumulated_paused_seconds", 0)
            or 0
        )
        elapsed_seconds = max(0, int((reference_time - check_in_time).total_seconds() - accumulated_paused))
        remaining_seconds = max(0, int(float(membership.total_hours or 0) * 3600) - elapsed_seconds)
    
    expiry_iso = None
    if membership.expiry_date:
        expiry_dt = membership.expiry_date
        if expiry_dt.tzinfo is None:
            expiry_dt = ph_tz.localize(expiry_dt)
        expiry_iso = expiry_dt.isoformat()

    activities = []
    if active_log and active_log.check_in_time:
        activity_query = UserActivityLog.query.filter(
            UserActivityLog.user_id == membership.user_id,
            UserActivityLog.activity_type.like("attendance|%"),
            UserActivityLog.activity_time >= active_log.check_in_time,
        ).order_by(UserActivityLog.activity_time.desc())

        activity_descriptions = {
            "Check-In": "Session started",
            "Paused": "Session paused",
            "Resumed": "Session resumed",
        }
        for activity in activity_query.limit(50).all():
            action = activity.activity_type.split("|", 1)[-1]
            activities.append({
                "title": action,
                "description": activity_descriptions.get(action, "Session activity"),
                "timestamp": activity.activity_time.strftime("%b %d, %Y - %I:%M %p"),
            })

        if not activities:
            activities.append({
                "title": "Check-In",
                "description": "Session started",
                "timestamp": active_log.check_in_time.strftime("%b %d, %Y - %I:%M %p"),
            })

    return jsonify({
        "status": "success",
        "hours_left": membership.hours_left,
        "remaining_seconds": remaining_seconds,
        "elapsed_seconds": elapsed_seconds,
        "total_seconds": int(float(membership.total_hours or 0) * 3600),
        "is_countdown_active": bool(membership.is_checked_in and member_status == "CHECKED_IN"),
        "is_checked_in": membership.is_checked_in,
        "is_active": membership.is_active,
        "is_paused": bool(getattr(membership, 'is_paused', False)),
        "member_status": member_status,
        "plan_name": membership.plan_name,
        "expiry_date": expiry_iso,
        "accumulated_hours": 0.0,
        "activities": activities,
    })


@api_bp.route("/membership/current-session", methods=["GET"])
@login_required
def membership_current_session():
    """Get current user's active session (check-in time) - PAUSE FREEZE FIXED"""
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)

    membership = Membership.query.filter_by(user_id=current_user.id).first()
    
    if not membership:
        return jsonify({"status": "error", "message": "No membership found"})

    _expire_membership_if_needed(membership)
    
    if not membership.is_checked_in:
        return jsonify({"status": "error", "message": "No active session"})
    
    current_session = (
        AttendanceLog.query.filter(
            AttendanceLog.membership_id == membership.id,
            AttendanceLog.check_out_time.is_(None)
        )
        .order_by(AttendanceLog.check_in_time.desc())
        .first()
    )
    
    if not current_session:
        return jsonify({"status": "error", "message": "No active session found"})
    
    check_in_dt = current_session.check_in_time
    if check_in_dt and check_in_dt.tzinfo is None:
        check_in_dt = ph_tz.localize(check_in_dt)

    # 1. STRICT PAUSE CHECK (E-check ang AttendanceLog MISMU + Membership)
    session_is_paused = bool(getattr(current_session, 'is_paused', False))
    membership_is_paused = bool(getattr(membership, 'is_paused', False))
    is_paused = session_is_paused or membership_is_paused

    ref_time = now_ph

    # 2. FREEZE TIMESTAMP FALLBACK
    if is_paused:
        # Una, kuhaon sa AttendanceLog; kun wala, kuhaon sa Membership
        p_dt = getattr(current_session, 'paused_at', None) or getattr(membership, 'paused_at', None)
        if p_dt:
            if p_dt.tzinfo is None:
                p_dt = ph_tz.localize(p_dt)
            ref_time = p_dt

    # 3. ACCUMULATED PAUSED SECONDS FALLBACK
    accumulated_paused = (
        getattr(current_session, 'accumulated_paused_seconds', 0) or 
        getattr(membership, 'accumulated_paused_seconds', 0) or 
        0
    )

    # 4. EXACT NET ELAPSED CALCULATION
    raw_elapsed = (ref_time - check_in_dt).total_seconds()
    elapsed_seconds = max(0, int(raw_elapsed - accumulated_paused))

    total_hours = float(membership.total_hours or 0)
    total_seconds = int(total_hours * 3600)

    remaining_seconds = max(0, total_seconds - elapsed_seconds)
    
    return jsonify({
        "status": "success",
        "check_in_time": check_in_dt.isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "remaining_seconds": remaining_seconds,
        "is_paused": is_paused,
        "member_status": "PAUSED" if is_paused else "CHECKED_IN",
        "paused_at": (
            (getattr(current_session, 'paused_at', None) or getattr(membership, 'paused_at', None)).isoformat()
            if (getattr(current_session, 'paused_at', None) or getattr(membership, 'paused_at', None)) else None
        ),
        "accumulated_paused_seconds": accumulated_paused,
        "membership_id": membership.id,
        "hours_left": membership.hours_left
    })