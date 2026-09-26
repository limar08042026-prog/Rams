"""
admin.py
Contains the admin blueprint with all admin routes and daily report helpers.
"""
import os
from io import BytesIO
from datetime import datetime, timezone, timedelta
import pytz
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database_fixed import AdminReservationForm, AttendanceLog, DailyReport, Membership, PaymentInfo, Reservation, \
    Room, SoloPlan, TimeLog, User, UserActivityLog, WalkinForm, WalkinReservation, db, generate_customer_id, \
    get_common_area_count, mail
from flask_mail import Message
from werkzeug.utils import secure_filename
from flask_login import current_user, login_required
from sqlalchemy import and_, func, inspect, or_, text
from time_utils import format_checkin_time, format_checkout_time, format_date, decimal_hours_to_readable
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

def calculate_open_time_minutes_fee(minutes):
    """
    Helper function para sa Open Time minute-tier pricing:
    1-12 mins = ₱5
    13-24 mins = ₱10
    25-36 mins = ₱15
    37-47 mins = ₱20
    48-60 mins = ₱25
    """
    if minutes <= 0:
        return 0.0
    elif 1 <= minutes <= 12:
        return 5.0
    elif 13 <= minutes <= 24:
        return 10.0
    elif 25 <= minutes <= 36:
        return 15.0
    elif 37 <= minutes <= 47:
        return 20.0
    elif 48 <= minutes <= 60:
        return 25.0
    return 35.0  # Fallback for full hour rate


def calculate_admin_total_amount(
    room_rate=0.0,
    duration_hours=1.0,
    extra_fee=0.0,
    addon_subtotal=0.0,
    discount_rate=0.0,
    is_open_time=False,
    duration_minutes=None,  # Optional exact minutes parameter
):
    """Calculate an admin reservation/walk-in total using the shared billing formula."""
    rate = float(room_rate or 35.0)  # Default base rate if 0
    discount = float(discount_rate or 0.0)

    if is_open_time:
        # Kon may napasa nga duration_minutes, gamiton ini
        if duration_minutes is not None:
            total_mins = int(duration_minutes)
        else:
            # Kon duration_hours lang ang ginpasa, i-convert sa minutes
            total_mins = int(float(duration_hours or 0.0) * 60)

        if total_mins <= 0:
            room_cost = calculate_open_time_minutes_fee(1)  # Minimum fee (₱5)
        else:
            full_hours = total_mins // 60
            remaining_mins = total_mins % 60

            hourly_fee = full_hours * rate
            minute_fee = calculate_open_time_minutes_fee(remaining_mins)

            room_cost = hourly_fee + minute_fee
    else:
        duration = float(duration_hours or 1.0)
        room_cost = rate * duration

    # Apply discount sa room cost
    if discount > 0:
        room_cost = room_cost * (1 - (discount / 100.0) if discount > 1 else (1 - discount))

    # Add extra fees kag addons
    total = room_cost + float(extra_fee or 0.0) + float(addon_subtotal or 0.0)
    
    return round(total, 2)

def get_custom_tier_rate(room_name, pax_count, default_rate):
    """
    I-calculate lang ang dynamic rate para sa Lecture Room kag Event Room.
    Para sa iban nga rooms, ibalik lang ang ila standard default_rate.
    """
    name = room_name.strip().lower()
    pax = int(pax_count or 1)

    # Specific lang sa Lecture Room
    if "lecture room" in name:
        if pax <= 5:
            return 150.0
        elif pax <= 10:
            return 200.0
        else:
            return 250.0

    # Specific lang sa Event Room
    elif "event room" in name:
        if pax <= 15:
            return 300.0
        elif pax <= 30:
            return 400.0
        else:
            return 500.0

    # Para sa tanan nga iban nga rooms (Common Area, Small Meeting Rooms, etc.)
    return float(default_rate or 0.0)

def get_business_date(dt):
    """
    Kon ang oras mas sayo sa 7:00 AM,
    ipaisip kini nga parte pa sang kahapon nga Business Date.
    """
    if dt.hour < 7:
        return (dt - timedelta(days=1)).date()
    return dt.date()

def require_super_admin():
    if current_user.role != "admin":
        flash("Access Restricted: Super Admin Account Required", "danger")
        return redirect(url_for("main.dashboard"))


def require_admin_or_staff():
    if current_user.role not in ("admin", "staff"):
        flash("Access Restricted: Super Admin Account Required", "danger")
        return redirect(url_for("main.dashboard"))


def require_super_admin_json():
    if current_user.role != "admin":
        return jsonify({"status": "error", "message": "Admin access required"}), 403


def require_admin_or_staff_json():
    if current_user.role not in ("admin", "staff"):
        return jsonify({"status": "error", "message": "Access restricted"}), 403


def auto_start_due_reservations(now=None):
    """Start due confirmed reservations once using existing attendance records."""
    now = now or (datetime.utcnow() + timedelta(hours=8))
    due_reservations = Reservation.query.filter(
        Reservation.status.in_(["Confirmed", "APPROVED", "CONFIRMED"]),
        Reservation.start_time <= now,
    ).all()
    changed = False

    for reservation in due_reservations:
        if not reservation.user_id:
            continue

        active_plan = SoloPlan.query.filter(
            SoloPlan.user_id == reservation.user_id,
            func.lower(SoloPlan.status).in_(["approved", "active"]),
            or_(
                SoloPlan.expiry_date.is_(None),
                SoloPlan.expiry_date >= now,
            ),
        ).first()
        if not active_plan:
            reservation.status = "Checked-in"
            changed = True
            continue

        membership = Membership.query.filter_by(user_id=reservation.user_id).first()
        if not membership:
            continue

        existing_session = AttendanceLog.query.filter(
            AttendanceLog.membership_id == membership.id,
            AttendanceLog.check_out_time.is_(None),
        ).first()
        if existing_session:
            reservation.status = "Checked-in"
            changed = True
            continue

        end_time = reservation.end_time or (reservation.start_time + timedelta(hours=1))
        duration_hours = max(0.0, (end_time - reservation.start_time).total_seconds() / 3600)
        db.session.add(AttendanceLog(
            membership_id=membership.id,
            check_in_time=now,
            accumulated_paused_seconds=0,
        ))
        membership.is_checked_in = True
        membership.is_checked_out = False
        membership.status = "active"
        membership.start_date = now
        membership.expiry_date = end_time
        membership.total_hours = duration_hours
        membership.hours_left = duration_hours
        reservation.status = "Checked-in"
        changed = True

    if changed:
        db.session.commit()


def get_common_area_dashboard_counts(now):
    active_member_user_ids = db.session.query(SoloPlan.user_id).filter(
        func.lower(SoloPlan.status).in_(["approved", "active"]),
        or_(
            SoloPlan.expiry_date.is_(None),
            SoloPlan.expiry_date >= now,
        ),
    )
    active_walkins_count = Reservation.query.join(Room).filter(
        Room.name.ilike("common area"),
        Reservation.status.in_(["Confirmed", "IN_PROGRESS", "Checked-in", "Walk-in"]),
        or_(
            Reservation.user_id.is_(None),
            ~Reservation.user_id.in_(active_member_user_ids),
        ),
        Reservation.start_time <= now,
        or_(Reservation.is_open_time.is_(True), Reservation.end_time >= now),
    ).count()

    active_members_count = db.session.query(AttendanceLog.id).join(Membership).filter(
        Membership.status == "active",
        Membership.is_checked_in == True,
        Membership.is_paused == False,
        AttendanceLog.is_paused == False,
        AttendanceLog.check_out_time.is_(None),
    ).count()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    confirmed_waiting_count = Reservation.query.join(Room).filter(
        Room.name.ilike("common area"),
        func.lower(Reservation.status).in_([
            "confirmed",
            "approved",
            "waiting",
            "pending",
            "pending confirmation",
        ]),
        Reservation.start_time >= today_start,
        Reservation.start_time < today_end,
    ).count()

    occupied_count = active_walkins_count + active_members_count + confirmed_waiting_count
    return active_walkins_count, active_members_count, occupied_count


def _solo_plan_credit_hours(plan_name):
    plan_key = (plan_name or "").strip().upper()
    hour_mapping = {
        "INDIVIDUAL RATE": 1.0,
        "INDIVIDUAL RATE (4HRS)": 4.0,
        "DAY/NIGHT PASS": 24.0,
        "WEEKLY PASS (DAY/NIGHT)": 168.0,
        "WEEKLY PASS (24HRS)": 168.0,
        "MONTHLY PASS (DAY/NIGHT)": 720.0,
        "MONTHLY PASS (24HRS)": 720.0,
        "WORKSTATION (24HRS)": 720.0,
        "ACTIVE PLAN": 720.0,
    }
    return hour_mapping.get(plan_key, 24.0)


def _ensure_approved_solo_plan_membership(member, approved_plan=None):
    ph_tz = pytz.timezone("Asia/Manila")
    now_naive = datetime.now(ph_tz).replace(tzinfo=None)

    if approved_plan:
        latest_approved_plan = approved_plan
    else:
        latest_approved_plan = (
            SoloPlan.query.filter(
                SoloPlan.user_id == member.id,
                SoloPlan.status.ilike("approved"),
                or_(
                    SoloPlan.expiry_date.is_(None),
                    SoloPlan.expiry_date > now_naive
                )
            )
            .order_by(SoloPlan.created_at.desc())
            .first()
        )

    if not latest_approved_plan:
        return False

    membership = Membership.query.filter_by(user_id=member.id).first()

    if not membership:
        membership = Membership(
            user_id=member.id,
            plan_name=latest_approved_plan.plan_name,
            status="active",
            start_date=latest_approved_plan.created_at or now_naive,
            expiry_date=latest_approved_plan.expiry_date,

        )
        db.session.add(membership)
    else:
        membership.plan_name = latest_approved_plan.plan_name
        membership.status = "active"
        membership.start_date = latest_approved_plan.created_at or now_naive
        membership.expiry_date = latest_approved_plan.expiry_date

    return True


def _expire_membership_if_needed(membership):
    if not membership or membership.status != "active" or not membership.expiry_date:
        return

    # Philippine Standard Time (+8 Hours)
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz).replace(tzinfo=None)

    if now_ph >= membership.expiry_date:
        membership.status = "expired"
        membership.hours_left = 0.0
        membership.is_checked_in = False

        # Auto check-out kon nag-expire ang plan samtang naka-check in
        active_log = membership.attendance_logs.filter(AttendanceLog.check_out_time.is_(None)).first()
        if active_log:
            active_log.check_out_time = membership.expiry_date
            active_log.hours_deducted = round(
                (active_log.check_out_time - active_log.check_in_time).total_seconds() / 3600,
                2,
            )

        db.session.commit()

# Daily Report Helpers

@admin_bp.route("/api/rooms")
@login_required
def admin_rooms_api():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Access Restricted: Executive Admin Account Required",
                }
            ),
            403,
        )

    rooms = Room.query.all()

    room_data = [
        {
            "id": room.id,
            "name": room.name,
            "base_rate": room.base_rate,
            "status": room.status,
            "is_common_area": room.name.strip().lower() == "common area",
        }
        for room in rooms
    ]

    room_data = sorted(
        room_data, key=lambda r: 0 if r["is_common_area"] else 1
    )
    return jsonify(room_data)

def get_or_create_daily_report(report_date):
    report = DailyReport.query.filter_by(report_date=report_date).first()
    if not report:
        report = DailyReport(
            report_date=report_date,
            total_check_ins=0,
            total_logins=0,
            total_timelogged=0,
        )
        db.session.add(report)
        db.session.commit()
    return report


def ensure_address_column():
    try:
        inspector = inspect(db.engine)
        if inspector.has_table("reservations"):
            columns = [
                column["name"]
                for column in inspector.get_columns("reservations")
            ]
            if "address" not in columns:
                db.session.execute(
                    text(
                        "ALTER TABLE reservations ADD COLUMN address VARCHAR(128)"
                    )
                )
                db.session.commit()
    except Exception:
        pass


def refresh_daily_report(report_date):
    report = get_or_create_daily_report(report_date)

    start = datetime.combine(report_date, datetime.min.time()) + timedelta(hours=7)
    end = start + timedelta(days=1)

    report.total_check_ins = Reservation.query.filter(
        Reservation.end_time >= start,
        Reservation.end_time <= end,
        Reservation.status == "Checked-Out",
        Reservation.paid == True,
    ).count()

    report.total_logins = TimeLog.query.filter(
        TimeLog.time_in >= start, TimeLog.time_in <= end
    ).count()

    total_revenue = (
        db.session.query(func.coalesce(func.sum(Reservation.total_amount), 0))
        .filter(
            Reservation.end_time >= start,
            Reservation.end_time <= end,
            Reservation.status == "Checked-Out",
            Reservation.paid == True,
        )
        .scalar()
        or 0
    )

    report.total_timelogged = total_revenue
    ph_tz = ZoneInfo("Asia/Manila")
    report.generated_at = datetime.now(ph_tz)

    db.session.add(report)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return report


def get_active_room_reservations(rooms):
    room_ids = [room.id for room in rooms]

    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz).replace(tzinfo=None)

    query = Reservation.query.filter(
        Reservation.room_id.in_(room_ids),
        func.lower(Reservation.status).in_(["confirmed", "in_progress", "checked-in", "walk-in"]),
        or_(
            Reservation.is_open_time == True,
            Reservation.end_time.is_(None),
            Reservation.end_time > now,
        ),
    )
    if hasattr(Reservation, "deleted_at"):
        query = query.filter(Reservation.deleted_at.is_(None))

    reservations = query.order_by(Reservation.start_time.asc()).all()

    def is_current(reservation):
        if not reservation.start_time:
            return False

        if reservation.is_open_time or reservation.end_time is None:
            return reservation.start_time <= now

        if reservation.end_time:
            return reservation.start_time <= now <= reservation.end_time

        return False

    room_reservations = {}
    for res in reservations:
        # Future reservations belong to the Reservation/Waiting List, not the
        # Live Room Status grid. Only current sessions can occupy a room card.
        if not is_current(res):
            continue

        existing = room_reservations.get(res.room_id)
        if existing is None:
            room_reservations[res.room_id] = res
            continue

        existing_current = is_current(existing)
        res_current = is_current(res)

        if res_current and not existing_current:
            room_reservations[res.room_id] = res
            continue
        if existing_current and not res_current:
            continue

        if res.start_time and existing.start_time:
            if res.start_time < existing.start_time:
                room_reservations[res.room_id] = res
    return room_reservations


@admin_bp.route("/check_availability")
@login_required
def check_availability():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return jsonify({"status": "error", "message": "Access Restricted: Executive Admin Account Required"}), 403

    room_id = request.args.get("room_id", type=int)
    date_str = request.args.get("date", "")
    start_str = request.args.get("start", "")
    end_str = request.args.get("end", "")
    open_time = request.args.get("open_time", "false").lower() in ["1", "true", "yes"]

    try:
        room = Room.query.get(room_id) if room_id else None
        is_common_area = room and room.name.strip().lower() == "common area"

        if start_str and "T" in start_str:
            start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
        else:
            start_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now().date()
            if start_str:
                start_time = datetime.strptime(start_str, "%H:%M").time()
                start_dt = datetime.combine(start_date, start_time)
            else:
                start_dt = datetime.now()

        if open_time:
            end_dt = start_dt + timedelta(hours=8)
        elif end_str:
            if "T" in end_str:
                end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M")
            else:
                end_time = datetime.strptime(end_str, "%H:%M").time()
                end_dt = datetime.combine(start_dt.date(), end_time)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        if not is_common_area:
            conflict = Reservation.query.filter(
                Reservation.room_id == room_id,
                Reservation.status.in_(["Confirmed", "APPROVED", "Pending", "Walk-in", "Checked-in"]),
                Reservation.start_time < end_dt,
                Reservation.end_time.isnot(None),
                Reservation.end_time > start_dt,
            ).first()
            if conflict:
                return jsonify({
                    "status": "conflict",
                    "message": f"Time Conflict: Reserved until {conflict.end_time.strftime('%I:%M %p')}",
                })

            active_session = db.session.query(AttendanceLog).join(Membership).join(
                Reservation,
                Reservation.user_id == Membership.user_id,
            ).filter(
                Reservation.room_id == room_id,
                Reservation.status.in_(["Confirmed", "Checked-in", "Walk-in"]),
                AttendanceLog.check_out_time.is_(None),
                Membership.is_checked_in == True,
                Membership.status == "active",
                AttendanceLog.check_in_time < end_dt,
                Membership.expiry_date.isnot(None),
                Membership.expiry_date > start_dt,
            ).first()
            if active_session:
                return jsonify({
                    "status": "conflict",
                    "message": "Time Conflict: Room is occupied by an active session.",
                })

    except Exception as error:
        return jsonify(
            {"status": "error", "message": f"Invalid availability check data: {error}"}
        ), 400

    return jsonify({"status": "ok"})


# Admin Routes

@admin_bp.route("/dashboard")
@login_required
def dashboard():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    due_reservations = Reservation.query.filter(
        Reservation.start_time >= today_start,
        Reservation.start_time <= now,
        func.lower(Reservation.status) == "confirmed",
        or_(
            Reservation.end_time > now,
            Reservation.is_open_time == True,
            Reservation.end_time.is_(None),
        ),
    ).all()
    if due_reservations:
        for reservation in due_reservations:
            reservation.status = "IN_PROGRESS"
        db.session.commit()

    form = WalkinForm()
    rooms = Room.query.filter(~Room.name.ilike('Test Room%')).all()
    unique_rooms = []
    seen_room_names = set()
    for room in rooms:
        room_name = room.name.strip().lower()
        if room_name in seen_room_names:
            continue
        seen_room_names.add(room_name)
        unique_rooms.append(room)

    form.room_id.choices = [
        (room.id, f"{room.name} (₱{room.base_rate}/hr)") for room in rooms
    ]

    room_reservations = get_active_room_reservations(unique_rooms)
    recent_members = (
        User.query.filter_by(role="member")
        .order_by(User.created_at.desc())
        .limit(8)
        .all()
    )
    incomplete_count = (
        User.query.filter(
            User.role == "member",
            or_(
                User.phone.is_(None),
                User.phone == "",
                User.email.is_(None),
                User.email == "",
            ),
        )
        .count()
    )

    active_member_user_ids = db.session.query(SoloPlan.user_id).filter(
        func.lower(SoloPlan.status).in_(["approved", "active"]),
        or_(
            SoloPlan.expiry_date.is_(None),
            SoloPlan.expiry_date >= now,
        ),
    )
    total_members = User.query.filter(User.id.in_(active_member_user_ids)).count()
    active_plans = (
        SoloPlan.query.filter_by(status="approved")
        .filter(SoloPlan.expiry_date >= now)
        .count()
    )

    revenue_today = (
        db.session.query(func.coalesce(func.sum(Reservation.total_amount), 0))
        .filter(
            Reservation.end_time >= today_start,
            Reservation.end_time < today_end,
            Reservation.paid == True,
            Reservation.status == "Checked-Out",
        )
        .scalar()
        or 0
    )

    updated = False

    due_reservations = Reservation.query.filter(
        Reservation.start_time <= now,
        func.lower(Reservation.status).in_(["confirmed", "waiting"]),
    ).all()
    for res in due_reservations:
        if res.start_time and res.start_time <= now:
            res.status = "IN_PROGRESS"
            check_in_val = getattr(res, 'check_in_time', None) or getattr(res, 'start_time', None) or getattr(res, 'created_at', None)
            if not check_in_val:
                pass
            db.session.add(res)
            updated = True

    expired_sessions = Reservation.query.filter(
        Reservation.end_time <= now,
        Reservation.status.in_(["Confirmed", "Walk-in"]),
        Reservation.is_open_time == False,
        Reservation.is_paused == False
    ).all()
    for res in expired_sessions:
        res.status = "Ended"
        db.session.add(res)
        updated = True

    if updated:
        db.session.commit()

    reservations_today = Reservation.query.filter(
        func.lower(Reservation.status).in_(
            ["pending", "confirmed", "in_progress", "checked-in"]
        ),
    ).count()

    all_res = Reservation.query.filter(
        Reservation.start_time <= now,
        or_(
            Reservation.end_time >= today_start,
            Reservation.is_open_time == True
        ),
        Reservation.status.in_(["Confirmed", "IN_PROGRESS", "Checked-in", "Walk-in", "Ended"]),
    ).all()

    active_reservations = sorted(all_res, key=lambda x: (x.status != "Ended", x.end_time if x.end_time else datetime.max))

    today = now.date()
    pending_query = Reservation.query.filter(
        func.date(Reservation.start_time) == today,
        func.lower(Reservation.status).in_(
            ["pending", "confirmed", "waiting"]
        ),
        Reservation.start_time > now,
    )
    if hasattr(Reservation, "deleted_at"):
        pending_query = pending_query.filter(Reservation.deleted_at.is_(None))

    pending_reservations = pending_query.order_by(Reservation.start_time.asc()).all()

    waiting_list_today = [
        r
        for r in pending_reservations
        if r.start_time
        and r.start_time.date() == today
        and str(r.status or "").strip().lower() in ("confirmed", "waiting", "pending")
        and r.start_time > now
    ]

    live_occupied_reservations = [
        r
        for r in active_reservations
        if str(r.status or "").strip().lower() == "in_progress"
        and r.start_time is not None
        and r.start_time <= now
    ]

    active_walkins = [
        r
        for r in active_reservations
        if r.status in ("Walk-in", "Ended") and r.room is not None
    ]

    common_area_reservations = [
        r
        for r in active_reservations
        if r.room and r.room.name.strip().lower() == "common area"
        and str(r.status or "").strip().lower() in ("in_progress", "checked-in", "walk-in")
    ]

    # Fetch active AttendanceLog entries for checked-in members to bind real-time check-in stamp
    for res in common_area_reservations:
        if hasattr(res, 'user_id') and res.user_id:
            active_log = AttendanceLog.query.join(Membership).filter(
                Membership.user_id == res.user_id,
                AttendanceLog.check_out_time.is_(None)
            ).first()
            
            if active_log and active_log.check_in_time:
                # Direct overwrite sang display start_time gamit ang actual AttendanceLog check-in time
                res.actual_check_in = active_log.check_in_time

    common_area_reservations = sorted(
        common_area_reservations,
        key=lambda r: r.end_time if r.end_time is not None else datetime.max
    )

    _, _, common_area_occupancy = get_common_area_dashboard_counts(now)
    common_area_available_slots = max(0, 70 - common_area_occupancy)

    return render_template(
        "admin/admin_dashboard.html",
        form=form,
        total_members=total_members,
        active_plans=active_plans,
        reservations_today=reservations_today,
        revenue_today=revenue_today,
        rooms=unique_rooms,
        room_reservations=room_reservations,
        recent_members=recent_members,
        incomplete_count=incomplete_count,
        active_reservations=active_reservations,
        pending_reservations=pending_reservations,
        active_walkins=active_walkins,
        common_area_reservations=common_area_reservations,
        common_area_occupancy=common_area_occupancy,
        common_area_available_slots=common_area_available_slots,
        now=now,
    )


@admin_bp.route("/api/dashboard/room-status", methods=["GET"])
@login_required
def dashboard_room_status():
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz).replace(tzinfo=None)
    active_walkins_count, active_members_count, occupied_count = get_common_area_dashboard_counts(now)
    rooms = Room.query.filter(~Room.name.ilike('Test Room%')).all()
    active_reservations = get_active_room_reservations(rooms)
    room_statuses = []
    for room in rooms:
        reservation = active_reservations.get(room.id)
        room_statuses.append({
            "id": room.id,
            "name": room.name,
            "status": "OCCUPIED" if reservation else "AVAILABLE",
            "occupant_name": reservation.customer_name if reservation else None,
            "start_time": reservation.start_time.isoformat() if reservation else None,
            "end_time": reservation.end_time.isoformat() if reservation and reservation.end_time else None,
            "reservation_id": reservation.id if reservation else None,
            "is_paused": bool(reservation.is_paused) if reservation else False,
            "is_open_time": bool(reservation.is_open_time) if reservation else False,
            "room_rate": float(reservation.room.base_rate or 0) if reservation and reservation.room else 0,
            "total_amount": float(reservation.total_amount or 0) if reservation else 0,
            "extra_fee": float(reservation.extra_fee or 0) if reservation else 0,
        })

    return jsonify({
        "status": "success",
        "success": True,
        "capacity": 70,
        "occupied": occupied_count,
        "available": max(0, 70 - occupied_count),
        "walkins_count": active_walkins_count,
        "members_count": active_members_count,
        "common_area": {
            "capacity": 70,
            "occupied": occupied_count,
            "available": max(0, 70 - occupied_count),
        },
        "rooms": room_statuses,
    })

@admin_bp.route("/api/dashboard/today-waiting-list", methods=["GET"])
@login_required
def dashboard_today_waiting_list():
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    now = datetime.now(pytz.timezone("Asia/Manila")).replace(tzinfo=None)
    today = now.date()
    waiting_query = Reservation.query.filter(
        func.date(Reservation.start_time) == today,
        Reservation.start_time > now,
        func.lower(Reservation.status).in_(["confirmed", "waiting", "pending"]),
    )
    if hasattr(Reservation, "deleted_at"):
        waiting_query = waiting_query.filter(Reservation.deleted_at.is_(None))

    reservations = waiting_query.order_by(Reservation.start_time.asc()).all()

    waiting_list = [{
        "id": reservation.id,
        "customer_name": reservation.customer_name or "Guest",
        "room_name": reservation.room.name if reservation.room else "Common Area",
        "start_time": reservation.start_time.strftime("%I:%M %p"),
        "end_time": reservation.end_time.strftime("%I:%M %p") if reservation.end_time else "Open",
        "status": reservation.status,
    } for reservation in reservations]

    return jsonify({
        "status": "success",
        "count": len(waiting_list),
        "waiting_list": waiting_list,
    })


@admin_bp.route("/toggle_pause_reservation/<int:reservation_id>", methods=["POST"])
@login_required
def toggle_pause_reservation(reservation_id):
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    reservation = Reservation.query.get_or_404(reservation_id)
    
    # Dynamic Philippine Time Alignment (+8 Hours)
    ph_tz = pytz.timezone("Asia/Manila")
    now = datetime.now(ph_tz).replace(tzinfo=None)

    if not reservation.is_paused:
        # --- PAUSE LOGIC ---
        reservation.is_paused = True
        reservation.paused_at = now
        
    else:
        # --- RESUME LOGIC ---
        if reservation.paused_at:
            # Pila ka segundo nga naka-freeze/pause ang kwarto
            paused_seconds = (now - reservation.paused_at).total_seconds()
            
            current_accumulated = reservation.accumulated_paused_seconds or 0
            reservation.accumulated_paused_seconds = current_accumulated + int(paused_seconds)

            # Extend fixed-duration sessions by the full paused interval.
            if not reservation.is_open_time and reservation.end_time:
                reservation.end_time = reservation.end_time + timedelta(seconds=paused_seconds)

        # Reset state
        reservation.is_paused = False
        reservation.paused_at = None

    db.session.commit()
    return redirect(url_for("admin.dashboard"))


@admin_bp.route('/resume_reservation/<int:id>', methods=['POST'])
@login_required
def resume_reservation(id):
    res = Reservation.query.get_or_404(id)
    
    if res.is_paused and res.paused_at:
        now = datetime.now()
        paused_duration = int((now - res.paused_at).total_seconds())
        
        # 1. KON OPEN TIME ONLY:
        # I-save ang paused duration sa accumulated_paused_seconds
        # para indi mag-jump ang Live Timer pag-resume.
        if res.is_open_time:
            res.accumulated_paused_seconds = (res.accumulated_paused_seconds or 0) + paused_duration

        # 2. KON FIXED TIME ONLY:
        # I-extend ang end_time sang nagligad nga pause duration 
        # para matagaan ang customer sang eksakto nga oras.
        else:
            if res.end_time:
                res.end_time = res.end_time + timedelta(seconds=paused_duration)

        # I-reset ang pause status
        res.is_paused = False
        res.paused_at = None
        db.session.commit()
        
    return redirect(url_for('dashboard'))

# (Global Notification Context Processor)

def _admin_notification_counts():
    requests_seen_at = session.get("admin_requests_seen_at")
    members_seen_at = session.get("admin_members_seen_at")
    try:
        requests_seen_at = datetime.fromisoformat(requests_seen_at) if requests_seen_at else None
    except (TypeError, ValueError):
        requests_seen_at = None
    try:
        members_seen_at = datetime.fromisoformat(members_seen_at) if members_seen_at else None
    except (TypeError, ValueError):
        members_seen_at = None

    pending_plans_query = SoloPlan.query.filter_by(status="pending")
    if requests_seen_at:
        pending_plans_query = pending_plans_query.filter(SoloPlan.created_at > requests_seen_at)

    new_members_query = Membership.query.filter_by(
        status="active",
        member_list_notification_seen=False
    )
    if members_seen_at:
        new_members_query = new_members_query.filter(Membership.updated_at > members_seen_at)

    return (
        Reservation.query.filter_by(status="Pending").count(),
        pending_plans_query.count(),
        new_members_query.count(),
    )

@admin_bp.app_context_processor
def inject_sidebar_notifications():
    if current_user.is_authenticated and getattr(current_user, 'role', '') in ['admin', 'staff']:
        p_res, p_plans, p_new_members = _admin_notification_counts()

        return dict(
            pending_reservations_count=p_res,
            pending_solo_plans_count=p_plans,
            new_members_count=p_new_members
        )

    return dict(
        pending_reservations_count=0,
        pending_solo_plans_count=0,
        new_members_count=0
    )

# API Endpoint para sa JS Polling
@admin_bp.route('/api/admin/notifications-count')
@login_required
def get_admin_notifications_count():
    if current_user.role not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized'}), 403

    p_res, p_plans, p_new_members = _admin_notification_counts()

    return jsonify({
        'pending_reservations': p_res,
        'pending_memberships': p_plans,
        'new_members_count': p_new_members,
        'members_notifications': p_plans + p_new_members,
        'dashboard_notifications': p_res,
        'total_notifications': p_res + p_plans + p_new_members
    })


@admin_bp.route('/api/admin/notifications/clear-nav', methods=['POST'])
@login_required
def clear_admin_members_navigation_notifications():
    if current_user.role not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized'}), 403

    now = datetime.utcnow()
    session['admin_requests_seen_at'] = now.isoformat()
    session['admin_members_seen_at'] = now.isoformat()
    session.modified = True
    return jsonify({'success': True})


@admin_bp.route('/api/admin/notifications/clear-tab', methods=['POST'])
@login_required
def clear_admin_members_tab_notifications():
    if current_user.role not in ['admin', 'staff']:
        return jsonify({'error': 'Unauthorized'}), 403

    tab = request.args.get('tab')
    if tab == 'requests':
        session['admin_requests_seen_at'] = datetime.utcnow().isoformat()
    elif tab in ['members', 'list']:
        session['admin_members_seen_at'] = datetime.utcnow().isoformat()
    else:
        return jsonify({'success': False, 'message': 'Unknown notification tab.'}), 400

    session.modified = True
    return jsonify({'success': True})


@admin_bp.route('/payment_settings', methods=['GET', 'POST'])
@login_required
def payment_settings():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    payment_infos = {info.method: info for info in PaymentInfo.query.all()}

    if request.method == 'POST':
        method = request.form.get('method')
        account_name = request.form.get('account_name', '').strip()
        account_number = request.form.get('account_number', '').strip()
        instructions = request.form.get('instructions', '').strip()
        qr_file = request.files.get('qr_image')

        if method not in ['GCash', 'Maya']:
            flash('Invalid payment method.', 'danger')
            return redirect(url_for('admin.payment_settings'))

        payment_info = PaymentInfo.query.filter_by(method=method).first()
        if not payment_info:
            payment_info = PaymentInfo(method=method)

        payment_info.account_name = account_name
        payment_info.account_number = account_number
        payment_info.instructions = instructions

        if qr_file and qr_file.filename:
            filename = secure_filename(f"{method.lower()}_{int(datetime.now().timestamp())}_{qr_file.filename}")
            upload_folder = os.path.join(current_app.root_path, 'static/uploads/payment')
            os.makedirs(upload_folder, exist_ok=True)
            qr_path = os.path.join(upload_folder, filename)
            qr_file.save(qr_path)
            payment_info.qr_image = filename

        db.session.add(payment_info)
        db.session.commit()
        flash(f'{method} payment settings updated.', 'success')
        return redirect(url_for('admin.payment_settings'))

    payment_infos = {info.method: info for info in PaymentInfo.query.all()}
    return render_template('admin/payment_settings.html', payment_infos=payment_infos)


@admin_bp.route("/manage_staff", methods=["GET", "POST"])
@login_required
def manage_staff():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    try:
        inspector = inspect(db.engine)
        if inspector.has_table("users"):
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "created_via_manage_staff" not in columns:
                db.session.execute(text("ALTER TABLE users ADD COLUMN created_via_manage_staff BOOLEAN NOT NULL DEFAULT 0"))
                db.session.commit()
    except Exception:
        pass

    message = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "staff")

        # Strict Alphanumeric Regex (At least 1 letter, 1 number, and ONLY letters & numbers)
        alphanumeric_regex = r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+$'

        if not name or not email or not password or role not in ["admin", "staff"]:
            message = "Please fill in all fields and select a valid role."
        elif User.query.filter(func.lower(User.email) == email).first():
            message = "A staff account with that email already exists."
        else:
            new_user = User(
                name=name,
                email=email,
                phone=phone,
                role=role,
                is_active=True,
                created_via_manage_staff=True,
            )
            new_user.set_password(password)
            db.session.add(new_user)
            try:
                db.session.commit()
                flash(f"{role.title()} account created for {name}.", "success")
                return redirect(url_for("admin.manage_staff"))
            except Exception as err:
                db.session.rollback()
                message = "Failed to create staff account. Check server logs for details."
                flash(message, "danger")

    staff_users = User.query.filter(User.role == "staff").all()
    managed_admin_users = User.query.filter(
        User.role == "admin",
        User.created_via_manage_staff.is_(True),
    ).all()

    staff_users.extend(managed_admin_users)
    staff_users = sorted(staff_users, key=lambda user: (user.role, user.name))

    return render_template(
        "admin/manage_staff.html",
        staff_users=staff_users,
        message=message,
    )


@admin_bp.route("/toggle_staff_status/<int:user_id>", methods=["POST"])
@login_required
def toggle_staff_status(user_id):
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    user = User.query.get_or_404(user_id)
    # 1. Validation checks gamit ang flash messages kag redirect
    if user.role not in ["admin", "staff"]:
        flash("Unsupported user type.", "danger")
        return redirect(url_for("admin.manage_staff"))
        
    if user.id == current_user.id:
        flash("You cannot change your own status.", "warning")
        return redirect(url_for("admin.manage_staff"))

    # 2. Toggle Status & Activity Log
    user.is_active = not user.is_active
    action = "reactivated" if user.is_active else "deactivated"
    log_message = f"{action} by {current_user.name}"
    
    log = UserActivityLog(
        user_id=user.id,
        activity_type=log_message,
        ip_address=request.remote_addr or "unknown",
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Staff account {action} successfully.", "success")
    return redirect(url_for("admin.manage_staff"))


@admin_bp.route("/walkin_checkin", methods=["POST"])
@login_required
def walkin_checkin_modal():
    form = WalkinForm()
    rooms = Room.query.filter(~Room.name.ilike('Test Room%')).all()
    form.room_id.choices = [(room.id, room.name) for room in rooms]

    current_app.logger.debug("walkin_checkin request.form at entry: %s", request.form.to_dict())
    current_app.logger.debug("csrf_token present: %s", 'csrf_token' in request.form)

    if form.validate_on_submit():
        room = Room.query.get(form.room_id.data)
        if not room:
            flash("Please select a valid room.")
            return redirect(url_for("admin.dashboard"))

        now = datetime.now()
        is_open_time = form.open_time.data

        if is_open_time:
            start_time = now
        else:
            if form.start_time.data:
                if isinstance(form.start_time.data, str):
                    try:
                        start_time = datetime.strptime(form.start_time.data, "%Y-%m-%dT%H:%M")
                    except ValueError:
                        start_time = now
                else:
                    start_time = form.start_time.data
            else:
                start_time = now

        if is_open_time:
            end_time = start_time  # UPDATED CODE
        else:
            if form.end_time.data:
                if isinstance(form.end_time.data, str):
                    try:
                        end_time = datetime.strptime(form.end_time.data, "%Y-%m-%dT%H:%M")
                    except ValueError:
                        end_time = start_time + timedelta(hours=1)
                else:
                    end_time = form.end_time.data
                if end_time <= start_time:
                    end_time += timedelta(days=1)
            else:
                end_time = start_time + timedelta(hours=1)

        if room.name.strip().lower() != "common area":
            reservation_query = Reservation.query.filter(
                Reservation.room_id == room.id,
                func.lower(Reservation.status).in_(
                    ["confirmed", "approved", "in_progress", "checked-in", "walk-in", "pending"]
                ),
            )
            conflict = None
            for reservation in reservation_query.all():
                reservation_end = reservation.end_time
                if reservation.is_open_time or reservation_end is None:
                    overlaps = start_time >= reservation.start_time
                else:
                    overlaps = start_time < reservation_end and end_time > reservation.start_time

                if overlaps:
                    conflict = reservation
                    break

            if conflict:
                conflict_start = conflict.start_time.strftime('%I:%M %p')
                conflict_end = (
                    conflict.end_time.strftime('%I:%M %p')
                    if conflict.end_time else "open time"
                )
                conflict_message = (
                    f"⚠️ Time Conflict: Room has an upcoming reservation from "
                    f"{conflict_start} to {conflict_end}."
                )
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": False, "message": conflict_message}), 400
                flash(conflict_message, "danger")
                return redirect(url_for("admin.dashboard"))
        else:
            #UPDATED CODE
            if get_common_area_count() >= 70:
                flash("Common Area has reached maximum capacity of 70 people.")
                return redirect(url_for("admin.dashboard"))

        # Generate customer_id based on room type
        room_type = "common area" if room.name.strip().lower() == "common area" else "other"
        try:
            customer_id = generate_customer_id(room_type)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("admin.dashboard"))

        total_from_js = request.form.get("total_price")
        extra_fee = float(form.extra_fee.data) if form.extra_fee.data else 0.0
        addon_subtotal = float(form.addon_subtotal.data) if form.addon_subtotal.data else 0.0
        pax_count = form.pax_count.data if getattr(form, "pax_count", None) and form.pax_count.data else 1
        room_rate = get_custom_tier_rate(room.name, pax_count, room.base_rate)
        total_amount = calculate_admin_total_amount(
            room_rate=room_rate,
            duration_hours=1.0,
            extra_fee=extra_fee,
            addon_subtotal=addon_subtotal,
            discount_rate=float(form.discount.data) if getattr(form, "discount", None) else 0.0,
            is_open_time=is_open_time,
        )

        new_walkin = Reservation(
            user_id=current_user.id,
            customer_id=customer_id,
            room_id=form.room_id.data,
            customer_name=form.customer_name.data,
            contact_number=form.contact_number.data or "N/A",
            pax_count=form.pax_count.data,
            extra_notes=form.extra_notes.data,
            extra_fee=extra_fee,
            addon_subtotal=addon_subtotal,
            start_time=start_time,
            end_time=end_time,
            is_open_time=is_open_time,
            status="Walk-in",
            added_by=current_user.name,
            total_amount=round(total_amount, 2),
            paid=False,
        )

        if room and room.name.strip().lower() != "common area" and start_time <= now:
            room.status = "unavailable"

        db.session.add(new_walkin)
        db.session.commit()

        walkin_entry = WalkinReservation(
            reservation_id=new_walkin.id,
            user_id=new_walkin.user_id,
            room_id=new_walkin.room_id,
            customer_name=new_walkin.customer_name,
            contact_number=new_walkin.contact_number,
            pax_count=new_walkin.pax_count,
            start_time=new_walkin.start_time,
            end_time=new_walkin.end_time,
            status="Walk-in",
            total_amount=new_walkin.total_amount,
            extra_fee=new_walkin.extra_fee,
            addon_subtotal=new_walkin.addon_subtotal,
            paid=False,
            added_by=new_walkin.added_by,
        )
        db.session.add(walkin_entry)
        db.session.commit()

        current_app.logger.debug("Walk-in created: %s", new_walkin.customer_name)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": True,
                "message": "Walk-in checked in successfully.",
            })
        flash(f"Walk-in {new_walkin.customer_name} added successfully!")
        return redirect(url_for("admin.dashboard"))

    current_app.logger.debug("WalkinForm validation failed: %s", form.errors)
    current_app.logger.debug("walkin_checkin request.form at failure: %s", request.form.to_dict())
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/walkin_checkout/<int:res_id>", methods=["GET", "POST"])
@login_required
def walkin_checkout(res_id):
    res = Reservation.query.get_or_404(res_id)
    now = datetime.now()

    final_bill_arg = request.args.get("final_bill") or request.form.get("final_bill")
    final_bill = None
    if final_bill_arg:
        try:
            final_bill = float(final_bill_arg)
        except (TypeError, ValueError):
            final_bill = None

    if final_bill is not None and final_bill > 0:
        res.total_amount = round(final_bill, 2)
        res.end_time = now
    elif res.is_open_time:
        duration_seconds = (now - res.start_time).total_seconds()
        duration_minutes = max(1, int(duration_seconds / 60))
        res.total_amount = calculate_admin_total_amount(
            room_rate=res.room.base_rate or 0,
            duration_hours=duration_minutes / 60,
            extra_fee=res.extra_fee or 0,
            addon_subtotal=res.addon_subtotal or 0,
            discount_rate=getattr(res, "discount_rate", 0) or 0,
            is_open_time=True,
        )
        res.end_time = now
    else:
        if not res.total_amount or res.total_amount == 0:
            try:
                if res.end_time and res.start_time:
                    diff_hours = (res.end_time - res.start_time).total_seconds() / 3600
                    diff_hours = max(diff_hours, 0)
                    res.total_amount = calculate_admin_total_amount(
                        room_rate=res.room.base_rate or 0,
                        duration_hours=diff_hours,
                        extra_fee=res.extra_fee or 0,
                        addon_subtotal=res.addon_subtotal or 0,
                        discount_rate=getattr(res, "discount_rate", 0) or 0,
                        is_open_time=False,
                    )
            except Exception:
                pass
        res.end_time = now

    report_date = res.end_time.date()

    res.status = "Checked-Out"
    res.paid = True

    if res.room and res.room.name.strip().lower() != "common area":
        res.room.status = "available"

    walkin_entry = WalkinReservation.query.filter_by(reservation_id=res.id).first()
    if walkin_entry:
        walkin_entry.status = "Checked-Out"
        walkin_entry.paid = True
        walkin_entry.total_amount = res.total_amount
        walkin_entry.end_time = res.end_time

    db.session.commit()
    refresh_daily_report(report_date)

    if (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
    ):
        return jsonify(
            {
                "status": "success",
                "message": f"Payment of ₱{res.total_amount:.2f} received from {res.customer_name}.",
            }
        )

    flash(f"Payment of ₱{res.total_amount:.2f} received from {res.customer_name}.")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/process_payment/<int:reservation_id>", methods=["GET", "POST"])
@login_required
def process_payment(reservation_id):
    res = Reservation.query.get_or_404(reservation_id)
    now = datetime.now()

    amount_passed = request.form.get("total_bill") or request.args.get("total_bill")

    if amount_passed and float(amount_passed) > 0:
        res.total_amount = round(float(amount_passed), 2)
        if res.is_open_time or not res.end_time:
            res.end_time = now
    elif res.is_open_time:
        # Calculate actual minutes spent from start_time until now
        duration_minutes = max(
            1, int((now - res.start_time).total_seconds() / 60)
        )
        res.total_amount = calculate_admin_total_amount(
            room_rate=res.room.base_rate or 0,
            duration_hours=duration_minutes / 60,
            duration_minutes=duration_minutes,  # Direkta nga i-pasa ang exact minutes!
            extra_fee=res.extra_fee or 0,
            addon_subtotal=res.addon_subtotal or 0,
            discount_rate=getattr(res, "discount_rate", 0) or 0,
            is_open_time=True,
        )
        res.end_time = now

    if not res.is_open_time and (not res.total_amount or res.total_amount == 0):
        try:
            if res.end_time and res.start_time:
                diff_hours = (res.end_time - res.start_time).total_seconds() / 3600
                diff_hours = max(diff_hours, 0)
                res.total_amount = calculate_admin_total_amount(
                    room_rate=res.room.base_rate or 0,
                    duration_hours=diff_hours,
                    extra_fee=res.extra_fee or 0,
                    addon_subtotal=res.addon_subtotal or 0,
                    discount_rate=getattr(res, "discount_rate", 0) or 0,
                    is_open_time=False,
                )
        except Exception:
            pass

    report_date = get_business_date(res.end_time)

    res.status = "Checked-Out"
    res.paid = True

    if res.room and res.room.name.strip().lower() != "common area":
        res.room.status = "available"

    walkin_entry = WalkinReservation.query.filter_by(reservation_id=res.id).first()
    if walkin_entry:
        walkin_entry.status = "Checked-Out"
        walkin_entry.paid = True
        walkin_entry.total_amount = res.total_amount
        walkin_entry.end_time = res.end_time

    db.session.commit()
    refresh_daily_report(report_date)

    flash(
        f"Payment of ₱{res.total_amount:.2f} received from {res.customer_name}. Dashboard updated!"
    )

    return redirect(url_for("admin.dashboard"))


@admin_bp.route('/extend_time/<int:res_id>', methods=['POST'])
@login_required
def extend_time(res_id):
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    res = Reservation.query.get_or_404(res_id)
    data = request.get_json(silent=True) or {}
    try:
        added_hours = int(data.get('added_hours', 0))
    except (TypeError, ValueError):
        added_hours = 0

    if added_hours <= 0:
        return jsonify({"status": "error", "message": "Please add at least 1 hour."}), 400

    if not res.end_time:
        return jsonify({"status": "error", "message": "Reservation end time is missing."}), 400

    if res.status == 'Ended':
        res.status = 'Walk-in'

    room_rate = res.room.base_rate or 0
    added_cost = round(room_rate * added_hours, 2)

    if res.is_open_time:
        res.extra_fee = (res.extra_fee or 0.0) + added_cost
        res.total_amount = round((res.total_amount or 0.0) + added_cost, 2)
    else:
        previous_end = res.end_time
        current_total = res.total_amount or 0.0
        if current_total == 0 and res.start_time and previous_end:
            original_duration = max(0, (previous_end - res.start_time).total_seconds() / 3600)
            current_total = round(original_duration * room_rate + (res.extra_fee or 0), 2)

        new_end = previous_end + timedelta(hours=added_hours)
        res.end_time = new_end
        res.total_amount = round(current_total + added_cost, 2)

    if res.room and res.room.name.strip().lower() != 'common area':
        res.room.status = 'unavailable'

    walkin_entry = WalkinReservation.query.filter_by(reservation_id=res.id).first()
    if walkin_entry:
        walkin_entry.end_time = res.end_time
        walkin_entry.total_amount = res.total_amount
        walkin_entry.status = 'Walk-in'

    db.session.commit()

    return jsonify(
        {
            "status": "success",
            "message": f"Extended {added_hours} hour(s) for {res.customer_name}. New total is ₱{res.total_amount:.2f}.",
            "new_total": res.total_amount,
            "new_end_time": res.end_time.isoformat(),
            "new_extra_fee": res.extra_fee or 0.0,
        }
    )


@admin_bp.route("/reservations", methods=["GET", "POST"])
@login_required
def admin_reservations():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    rooms = Room.query.filter(~Room.name.ilike('Test Room%')).all()
    form = AdminReservationForm()
    form.room_id.choices = [
        (r.id, f"{r.name} (₱{r.base_rate}/hr)") for r in rooms
    ]

    ensure_address_column()

    if request.method == "POST":
        selected_room_id = request.form.get("room_id")
        if selected_room_id:
            try:
                selected_room_id = int(selected_room_id)
            except (TypeError, ValueError):
                selected_room_id = None
        if selected_room_id and selected_room_id not in [choice[0] for choice in form.room_id.choices]:
            selected_room = Room.query.get(selected_room_id)
            if selected_room:
                form.room_id.choices.append(
                    (selected_room.id, f"{selected_room.name} (₱{selected_room.base_rate}/hr)")
                )

        total_from_js = request.form.get("total_price")
        is_open_time = form.open_time.data

        if form.validate_on_submit():
            room = Room.query.get(form.room_id.data)
            if not room:
                flash("Please select a valid room.")
                return render_template(
                    "admin/admin_reservations.html", form=form, rooms=rooms
                )

            # === 1. BACKEND PAX LIMIT VALIDATION ===
            pax_val = form.pax_count.data or 1
            room_name_lower = room.name.strip().lower()

            if "lecture room" in room_name_lower and pax_val > 15:
                flash("Error: Lecture Room capacity is strictly limited to a maximum of 15 pax.")
                return render_template(
                    "admin/admin_reservations.html", form=form, rooms=rooms
                )

            # === 2. DATE & TIME PARSING ===
            try:
                if form.start_time.data:
                    if isinstance(form.start_time.data, str):
                        full_start = datetime.strptime(form.start_time.data, "%Y-%m-%dT%H:%M")
                    else:
                        full_start = form.start_time.data
                else:
                    full_start = datetime.now()

                if is_open_time:
                    full_end = full_start + timedelta(hours=12)
                else:
                    if form.end_time.data:
                        if isinstance(form.end_time.data, str):
                            full_end = datetime.strptime(form.end_time.data, "%Y-%m-%dT%H:%M")
                        else:
                            full_end = form.end_time.data
                        if full_end <= full_start:
                            full_end += timedelta(days=1)
                    else:
                        full_end = full_start + timedelta(hours=1)

                if room_name_lower != "common area":
                    reservation_conflict = Reservation.query.filter(
                        Reservation.room_id == room.id,
                        Reservation.status.in_(["Confirmed", "APPROVED", "Pending", "Walk-in", "Checked-in"]),
                        Reservation.start_time < full_end,
                        Reservation.end_time.isnot(None),
                        Reservation.end_time > full_start,
                    ).first()
                    if reservation_conflict:
                        flash(
                            f"Time Conflict: Reserved until {reservation_conflict.end_time.strftime('%I:%M %p')}",
                            "danger",
                        )
                        return render_template("admin/admin_reservations.html", form=form, rooms=rooms)

                    conflict = Reservation.query.filter(
                        Reservation.room_id == room.id,
                        Reservation.status.in_(["Confirmed", "Walk-in", "Pending"]),
                        Reservation.start_time < full_end,
                        Reservation.end_time > full_start,
                    ).first()

                    if conflict:
                        flash(
                            f"Cannot book: {room.name} is already reserved by {conflict.customer_name} from {conflict.start_time.strftime('%I:%M %p')} to {conflict.end_time.strftime('%I:%M %p')}."
                        )
                        return render_template(
                            "admin/admin_reservations.html", form=form, rooms=rooms
                        )

            except Exception as e:
                flash(f"Time Format Error: {str(e)}")
                return render_template(
                    "admin/admin_reservations.html", form=form, rooms=rooms
                )

            # Generate customer_id based on room type
            room_type = "common area" if room_name_lower == "common area" else "other"
            try:
                customer_id = generate_customer_id(room_type)
            except ValueError as e:
                flash(str(e))
                return render_template(
                    "admin/admin_reservations.html", form=form, rooms=rooms
                )

            reservation = Reservation(
                user_id=current_user.id,
                customer_id=customer_id,
                room_id=form.room_id.data,
                customer_name=form.customer_name.data,
                contact_number=request.form.get("contact_number", "N/A"),
                pax_count=pax_val,
                start_time=full_start,
                end_time=full_end,
                is_open_time=is_open_time,
                # Admin-created reservations are already approved; pending is
                # reserved for customer-submitted requests awaiting review.
                status="Confirmed",
                added_by=current_user.name,
                extra_notes=form.extra_notes.data,
                extra_fee=float(form.extra_fee.data) if form.extra_fee.data else 0.0,
                addon_subtotal=float(form.addon_subtotal.data) if form.addon_subtotal.data else 0.0,
                total_amount=round(float(total_from_js or 0), 2),
                discount_rate=(
                    float(form.discount.data)
                    if getattr(form, "discount", None)
                    else 0.0
                ),
                paid=False,
            )

            # Keep same-day reservations in the waiting/confirmed state until an
            # explicit check-in or admin action starts them. Do not auto-activate
            # reservations merely because their start time is current or already in progress.
            reservation.status = "Confirmed"

            if (
                room
                and room_name_lower != "common area"
                and full_start <= datetime.now()
            ):
                room.status = "unavailable"

            db.session.add(reservation)

            # === 3. SERVER-SIDE TIER PRICING FALLBACK CALCULATION ===
            if not is_open_time and (not reservation.total_amount or reservation.total_amount == 0):
                try:
                    diff_hours = (reservation.end_time - reservation.start_time).total_seconds() / 3600
                    diff_hours = max(diff_hours, 0)
                    discount = reservation.discount_rate or 0.0

                    # Tier Rate Engine
                    if "lecture room" in room_name_lower:
                        if pax_val <= 5:
                            base_rate = 150.0
                        elif pax_val <= 10:
                            base_rate = 200.0
                        else:
                            base_rate = 250.0
                    elif "event room" in room_name_lower:
                        if pax_val <= 15:
                            base_rate = 300.0
                        elif pax_val <= 30:
                            base_rate = 400.0
                        else:
                            base_rate = 500.0
                    else:
                        base_rate = float(room.base_rate or 0)

                    room_cost = base_rate * diff_hours * (1 - discount)
                    reservation.total_amount = round(
                        room_cost + (reservation.extra_fee or 0) + (reservation.addon_subtotal or 0), 2
                    )
                except Exception:
                    reservation.total_amount = round(float(total_from_js or 0), 2)

            db.session.commit()

            flash("Reservation added to the Reservation List.", "success")
            return redirect(url_for("admin.admin_reservations_list"))

    return render_template("admin/admin_reservations.html", form=form, rooms=rooms)


@admin_bp.route("/reservations_list")
@login_required
def admin_reservations_list():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response
    search = request.args.get("search", "")
    tomorrow_start = datetime.combine(
        datetime.now(pytz.timezone("Asia/Manila")).date() + timedelta(days=1),
        datetime.min.time(),
    )
    query = Reservation.query.filter(
        func.lower(Reservation.status).in_(["confirmed", "pending"]),
        or_(
            Reservation.start_time >= tomorrow_start,
            and_(
                func.lower(Reservation.status) == "pending",
                Reservation.user_id.is_(None),
            ),
        ),
    )

    if search:
        query = query.filter(
            or_(
                Reservation.customer_name.ilike(f"%{search}%"),
                Reservation.added_by.ilike(f"%{search}%"),
                Reservation.status.ilike(f"%{search}%"),
            )
        )

    reservations = query.order_by(Reservation.start_time.asc()).all()
    return render_template(
        "admin/admin_reservations_list.html",
        reservations=reservations,
        search=search,
    )


@admin_bp.route("/confirm_reservations")
@login_required
def admin_confirm_reservations():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    pending_reservations = (
        Reservation.query.filter_by(status="Pending")
        .order_by(Reservation.created_at.desc(), Reservation.start_time.desc())
        .all()
    )
    return render_template(
        "admin/confirm_reservations.html",
        reservations=pending_reservations,
    )


@admin_bp.route("/solo_applications")
@login_required
def solo_applications():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    pending_plans = (
        SoloPlan.query.filter_by(status="pending")
        .order_by(SoloPlan.created_at.desc())
        .all()
    )
    return render_template(
        "admin/solo_applications.html", pending_plans=pending_plans
    )


@admin_bp.route("/approve_membership/<int:req_id>", methods=["POST"])
@login_required
def approve_membership(req_id):
    if current_user.role not in ["admin", "staff"]:
        flash("You do not have permission to approve memberships.", "danger")
        return redirect(url_for("admin.members", tab="list"))

    plan = SoloPlan.query.get_or_404(req_id)
    plan.approved_by_id = current_user.id
    plan.status = "approved"
    plan.approved_at = datetime.utcnow() + timedelta(hours=8)
    plan.member_notification_seen = False
    plan.renewal_notification_seen = True

    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    plan.set_expiry_date(now_ph)

    if not plan.customer_id:
        plan.customer_id = generate_customer_id("other")

    _ensure_approved_solo_plan_membership(plan.user, plan)

    membership = Membership.query.filter_by(user_id=plan.user.id).first()

    if membership:
        membership.is_checked_in = False
        membership.is_checked_out = False
        membership.is_paused = False
        membership.status = "active"
        membership.member_list_notification_seen = False

    db.session.commit()

    flash(f"Membership approved for {plan.user.name}", "success")
    return redirect(url_for("admin.members", tab="list"))


@admin_bp.route("/reject_membership/<int:req_id>", methods=["POST"])
@login_required
def reject_membership(req_id):
    if current_user.role not in ["admin", "staff"]: 
        flash("You do not have permission to reject memberships.", "danger")
        return redirect(url_for("admin.members", tab="requests"))

    plan = SoloPlan.query.get_or_404(req_id)
    plan.status = "rejected"
    db.session.commit()
    flash(f"Membership rejected for {plan.user.name}")
    return redirect(url_for("admin.members", tab="requests"))


@admin_bp.route("/renew_member", methods=["POST"])
@admin_bp.route("/admin/renew_member", methods=["POST"])
@login_required
def renew_member():
    try:
        data = request.get_json(silent=True) or request.form or {}
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({
                "status": "error",
                "message": "Missing user ID."
            }), 400

        user = User.query.get(int(user_id))
        if not user:
            return jsonify({
                "status": "error",
                "message": "Member not found."
            }), 404

        membership = Membership.query.filter_by(user_id=user.id).first()

        if not membership:
            return jsonify({
                "status": "error",
                "message": "No membership record found."
            }), 404

        if membership.is_checked_in:
            return jsonify({
                "status": "error",
                "message": "Cannot renew while customer is checked in. Please check out first."
            }), 400

        latest_plan = (
            SoloPlan.query
            .filter_by(user_id=user.id)
            .order_by(SoloPlan.id.desc())
            .first()
        )

        now_ph = datetime.utcnow() + timedelta(hours=8)

        plan_hours_map = {
            "INDIVIDUAL RATE": 1.0,
            "INDIVIDUAL RATE (4HRS)": 4.0,
            "DAY/NIGHT PASS": 24.0,
            "WEEKLY PASS (DAY/NIGHT)": 168.0,
            "WEEKLY PASS (24HRS)": 168.0,
            "MONTHLY PASS (DAY/NIGHT)": 720.0,
            "MONTHLY PASS (24HRS)": 720.0,
            "WORKSTATION (24HRS)": 720.0,
            "ACTIVE PLAN": 720.0
        }

        plan_name = membership.plan_name or "INDIVIDUAL RATE"
        fresh_hours = plan_hours_map.get(plan_name.strip().upper(), 1.0)

        if latest_plan:
            plan_name = latest_plan.plan_name or plan_name

            extracted = (
                getattr(latest_plan, "hours", None)
                or getattr(latest_plan, "duration_hours", None)
                or getattr(latest_plan, "hours_left", None)
                or getattr(latest_plan, "duration", None)
            )

            if extracted is not None:
                try:
                    fresh_hours = float(extracted)
                except (ValueError, TypeError):
                    fresh_hours = plan_hours_map.get(
                        plan_name.strip().upper(),
                        1.0
                    )
            else:
                fresh_hours = plan_hours_map.get(
                    plan_name.strip().upper(),
                    1.0
                )

        # Renew = prepare for a fresh session.
        # Dates must remain valid because expiry_date is NOT NULL.
        membership.plan_name = plan_name
        membership.status = "active"
        membership.is_checked_in = False
        membership.is_checked_out = False
        membership.is_paused = False
        membership.paused_at = None
        membership.accumulated_paused_seconds = 0
        membership.total_hours = fresh_hours
        membership.hours_left = fresh_hours
        membership.start_date = now_ph
        membership.expiry_date = now_ph + timedelta(hours=fresh_hours)
        membership.updated_at = now_ph

        if latest_plan:
            latest_plan.status = "approved"
            latest_plan.is_paused = False
            latest_plan.paused_at = None
            latest_plan.accumulated_paused_seconds = 0
            latest_plan.start_date = now_ph
            latest_plan.expiry_date = now_ph + timedelta(hours=fresh_hours)
            latest_plan.renewed_at = now_ph
            latest_plan.renewal_notification_seen = False
            latest_plan.updated_at = now_ph

        if membership:
            AttendanceLog.query.filter_by(
                membership_id=membership.id,
                check_out_time=None
            ).update({
                "check_out_time": now_ph
            })

        db.session.commit()
        db.session.expire_all()

        return jsonify({
            "status": "success",
            "message": "Membership renewed successfully! Please click Check In to start.",
            "hours_left": fresh_hours
        }), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Renew membership failed")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    

@admin_bp.route("/deactivate_member", methods=["POST"])
@login_required
def deactivate_member():
    redirect_response = require_super_admin_json()
    if redirect_response:
        return redirect_response

    data = request.get_json(silent=True) or request.form
    user_id = data.get("user_id") or request.form.get("user_id")

    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"status": "error", "message": "Member not found."}), 404

    # Soft-deactivate the user
    user.is_active = False
    # Gamiton ang local server time para sakto ang adlaw
    user.last_deactivated_at = datetime.now()

    # I-update ang membership status kon may ara
    membership = Membership.query.filter_by(user_id=user.id).order_by(Membership.id.desc()).first()
    if membership:
        membership.status = 'deactivated'

    log = UserActivityLog(
        user_id=user.id,
        activity_type=f"deactivated|Account deactivated by {current_user.name}",
        ip_address=request.remote_addr or "unknown",
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({"status": "success", "message": "Member account deactivated successfully."})


@admin_bp.route("/reactivate_member", methods=["POST"])
@login_required
def reactivate_member():
    redirect_response = require_super_admin_json()
    if redirect_response:
        return redirect_response

    data = request.get_json(silent=True) or request.form
    user_id = data.get("user_id") or request.form.get("user_id")

    if not user_id:
        return jsonify({"status": "error", "message": "Missing user ID."}), 400

    user = User.query.get(int(user_id))
    if not user:
        return jsonify({"status": "error", "message": "Member not found."}), 404

    # 1. Clear soft-deactivation flags sa User
    user.is_active = True
    user.last_deactivated_at = None

    # 2. Re-activate associated membership (status lang ang bag-ohon)
    membership = Membership.query.filter_by(user_id=user.id).order_by(Membership.id.desc()).first()
    if membership:
        membership.status = 'active'

    # 3. Log activity
    log = UserActivityLog(
        user_id=user.id,
        activity_type=f"reactivated|Account reactivated by {current_user.name}",
        ip_address=request.remote_addr or "unknown",
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({"status": "success", "message": "Member account reactivated successfully."})


@admin_bp.route("/approve_solo_plan/<int:plan_id>", methods=["POST"])
@login_required
def approve_solo_plan(plan_id):
    if current_user.role not in ["admin", "staff"]:
        flash("You do not have permission to approve memberships.", "danger")
        return redirect(url_for("admin.solo_applications"))

    plan = SoloPlan.query.get_or_404(plan_id)
    plan.status = "approved"
    plan.approved_at = datetime.utcnow() + timedelta(hours=8)
    plan.member_notification_seen = False
    plan.renewal_notification_seen = True
    plan.approved_by_id = current_user.id
    plan.set_expiry_date()  # Set expiry date on SoloPlan

    # Siguraduhon nga nakakabit ang membership record
    _ensure_approved_solo_plan_membership(plan.user, plan)

    # Reset checkout & checkin flags
    membership = Membership.query.filter_by(user_id=plan.user.id).first()
    if membership:
        membership.is_checked_in = False
        membership.is_checked_out = False
        membership.is_paused = False
        membership.status = "active"
        membership.member_list_notification_seen = False

    db.session.commit()
    flash(f"Plan approved for {plan.user.name}", "success")
    return redirect(url_for("admin.solo_applications"))


@admin_bp.route("/reject_solo_plan/<int:plan_id>", methods=["POST"])
@login_required
def reject_solo_plan(plan_id):
    if current_user.role not in ["admin", "staff"]:
        flash("You do not have permission to reject memberships.", "danger")
        return redirect(url_for("admin.solo_applications"))

    plan = SoloPlan.query.get_or_404(plan_id)
    plan.status = "rejected"
    db.session.commit()
    flash(f"Plan rejected for {plan.user.name}", "info")
    return redirect(url_for("admin.solo_applications"))

@admin_bp.route("/checkout_user/<int:user_id>", methods=["POST"])
@login_required
def admin_checkout_user(user_id):
    if current_user.role != "admin":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.dashboard"))

    ph_tz = pytz.timezone("Asia/Manila")
    now_naive = datetime.now(ph_tz).replace(second=0, microsecond=0, tzinfo=None)

    # 1. Papatyon ang active SoloPlan sang user
    active_plan = SoloPlan.query.filter(
        SoloPlan.user_id == user_id,
        SoloPlan.status.ilike("approved"),
        SoloPlan.expiry_date > now_naive
    ).first()

    if active_plan:
        active_plan.expiry_date = now_naive
        active_plan.status = "completed"

    # 2. Papatyon man ang Membership status sang user
    membership = Membership.query.filter_by(user_id=user_id).first()
    if membership:
        membership.expiry_date = now_naive
        membership.status = "expired"

    db.session.commit()
    flash("Customer has been successfully checked out by Admin.", "success")
    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/confirm_reservation/<int:res_id>", methods=["POST"])
@login_required
def confirm_reservation(res_id):
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    res = Reservation.query.get_or_404(res_id)
    now = datetime.now()

    # Confirming a reservation secures the slot without creating a live
    # checked-in session unless the scheduled time has actually arrived.
    res.status = "CONFIRMED"
    res.check_in_time = None

    if res.start_time:
        if (
            res.start_time.date() > now.date()
            or (res.start_time.date() == now.date() and res.start_time.time() > now.time())
        ):
            res.status = "CONFIRMED"
        elif res.start_time.date() == now.date() and res.start_time.time() <= now.time():
            res.status = "IN_PROGRESS"
            if not res.check_in_time:
                res.check_in_time = now

    res.confirmation_notification_seen = False
    res.approved_by_id = current_user.id
    if res.room and res.room.name.strip().lower() != "common area":
        if res.start_time and res.start_time <= now <= (res.end_time or now):
            res.room.status = "unavailable"
    db.session.commit()
    flash(f"Reservation confirmed for {res.customer_name}")
    return redirect(url_for("admin.admin_reservations_list"))


@admin_bp.route("/hold_reservation/<int:res_id>", methods=["POST"])
@login_required
def hold_reservation(res_id):
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    res = Reservation.query.get_or_404(res_id)
    if res.status not in ["Pending", "Confirmed"]:
        flash("Reservation cannot be held in its current state.")
        return redirect(url_for("admin.admin_reservations_list"))

    res.status = "On Hold"
    if res.room and res.room.name.strip().lower() != "common area":
        res.room.status = "available"
    db.session.commit()
    flash(f"Reservation for {res.customer_name} has been placed on hold.")
    return redirect(url_for("admin.admin_reservations_list"))


@admin_bp.route("/cancel_reservation/<int:res_id>", methods=["POST"])
@login_required
def cancel_reservation(res_id):
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    res = Reservation.query.get_or_404(res_id)
    if res.status == "Confirmed":
        res.room.status = "available"
    res.status = "Cancelled"
    db.session.commit()
    flash(f"Reservation cancelled for {res.customer_name}")
    return redirect(url_for("admin.admin_reservations_list"))


@admin_bp.route("/delete_reservation/<int:res_id>", methods=["POST"])
@login_required
def delete_reservation(res_id):
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    res = Reservation.query.get_or_404(res_id)
    # If reservation has associated walkin entries, delete them first to avoid FK constraint errors
    try:
        walkin_entries = WalkinReservation.query.filter_by(reservation_id=res.id).all()
        for w in walkin_entries:
            db.session.delete(w)
    except Exception:
        # ignore if table or relation unavailable; will surface on commit if real problem
        pass

    if res.status in ["Pending", "Confirmed", "Walk-in", "Ended"]:
        if res.room and res.room.name.strip().lower() != "common area":
            res.room.status = "available"

    next_url = request.form.get("next") or request.args.get("next") or request.referrer
    db.session.delete(res)
    db.session.commit()
    flash(f"Reservation for {res.customer_name} has been permanently deleted.")
    return redirect(next_url or url_for("admin.dashboard"))


@admin_bp.route("/reports", methods=["GET", "POST"])
@login_required
def reports():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    start_date = datetime.utcnow().date()
    end_date = datetime.utcnow().date()
    room_id = ""

    # Get all rooms for dropdown options
    rooms = Room.query.all()

    if request.method == "POST":
        room_id = request.form.get("room_id", "")
        start_date_str = request.form.get("start_date")
        end_date_str = request.form.get("end_date")
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if end_date_str:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format.")

    query = DailyReport.query.filter(
        DailyReport.report_date >= start_date, DailyReport.report_date <= end_date
    )
    daily_reports = query.order_by(DailyReport.report_date.desc()).all()

    reports_with_member = []
    for report in daily_reports:
        member_log = (
            TimeLog.query.join(User)
            .filter(
                TimeLog.time_in >= datetime.combine(
                    report.report_date, datetime.min.time()
                ),
                TimeLog.time_in <= datetime.combine(
                    report.report_date, datetime.max.time()
                ),
                User.role == "member",
            )
            .first()
        )
        reports_with_member.append(
            {
                "report_date": report.report_date,
                "total_logins": report.total_logins,
                "total_check_ins": report.total_check_ins,
                "total_revenue": report.total_timelogged,
                "generated_at": report.generated_at,
                "member_name": member_log.user.name if member_log else "N/A",
            }
        )

    sessions_query = Reservation.query.filter(
        func.date(Reservation.end_time) >= start_date,
        func.date(Reservation.end_time) <= end_date,
        Reservation.status.in_(["Checked-Out", "Cancelled"]),
    )

    if room_id:
        sessions_query = sessions_query.filter(Reservation.room_id == room_id)

    customer_sessions = sessions_query.order_by(Reservation.end_time.desc()).all()

    grand_total = sum(
        (session.total_amount or 0) for session in customer_sessions
    )

    return render_template(
        "admin/reports.html",
        daily_reports=reports_with_member,
        customer_sessions=customer_sessions,
        grand_total=grand_total,
        start_date=start_date,
        end_date=end_date,
        rooms=rooms,
        selected_room_id=room_id,
    )


@admin_bp.route("/generate_pdf")
@login_required
def generate_pdf():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    flash("PDF Generation feature is being initialized.")
    return redirect(url_for("admin.reports"))


@admin_bp.route("/generate_completed_sessions_pdf")
@login_required
def generate_completed_sessions_pdf():
    redirect_response = require_super_admin()
    if redirect_response:
        return redirect_response

    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    room_id = request.args.get("room_id", "")

    parsed_start_date = None
    parsed_end_date = None

    if start_date:
        try:
            parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_start_date = None

    if end_date:
        try:
            parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            parsed_end_date = None

    query = Reservation.query.filter(
        Reservation.status.in_(["Checked-Out", "Cancelled"])
    )

    if parsed_start_date:
        query = query.filter(func.date(Reservation.end_time) >= parsed_start_date)
    if parsed_end_date:
        query = query.filter(func.date(Reservation.end_time) <= parsed_end_date)
    if room_id:
        query = query.filter(Reservation.room_id == room_id)

    sessions = query.order_by(Reservation.end_time.desc()).all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        spaceAfter=8,
        textColor=colors.HexColor("#1f4e79"),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        textColor=colors.grey,
        spaceAfter=10,
    )
    body_style = styles["BodyText"]

    ph_tz = timezone(timedelta(hours=8))
    now_ph = datetime.now(ph_tz)

    room_filter_text = "All Rooms"
    if room_id:
        selected_room = Room.query.get(room_id)
        if selected_room:
            room_filter_text = selected_room.name

    elements = [
        Paragraph("Completed Sessions Report", title_style),
        Paragraph(
            f"Generated: {now_ph.strftime('%Y-%m-%d %I:%M %p')}",
            subtitle_style,
        ),
        Paragraph(
            f"Date range: {parsed_start_date or 'Beginning'} to {parsed_end_date or 'Today'} | Room: {room_filter_text}",
            subtitle_style,
        ),
        Spacer(1, 8),
    ]

    if not sessions:
        elements.append(Paragraph("No completed sessions found for the selected date range.", body_style))
    else:
        table_data = [[
            "Customer",
            "Contact",
            "Room",
            "Status",
            "Staff",
            "Start",
            "End",
            "Total Bill",
        ]]

        grand_total = 0.0

        for session in sessions:
            amount = session.total_amount if session.total_amount is not None else 0.0
            grand_total += amount

            table_data.append([
                session.customer_name or "N/A",
                session.contact_number or "N/A",
                session.room.name if session.room else "Unknown",
                session.status or "N/A",
                (session.approved_by.name if session.approved_by else (session.user.name if session.user else session.added_by or "Unknown")),
                session.start_time.strftime("%b %d, %Y %I:%M %p") if session.start_time else "N/A",
                session.end_time.strftime("%b %d, %Y %I:%M %p") if session.end_time else "N/A",
                f"PHP{amount:,.2f}",
            ])

        table_data.append([
            "GRAND TOTAL",
            "",
            "",
            "",
            "",
            "",
            "",
            f"PHP{grand_total:,.2f}",
        ])

        table = Table(table_data, repeatRows=1)

        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),

            ("SPAN", (0, -1), (6, -1)),                          
            ("ALIGN", (0, -1), (0, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 9),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaefb5")),
            ("TEXTCOLOR", (-1, -1), (-1, -1), colors.HexColor("#1f4e79")),
        ]

        table.setStyle(TableStyle(t_style))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="completed_sessions_report.pdf",
    )


@admin_bp.route("/members")
@login_required
def members():
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    ph_tz = pytz.timezone("Asia/Manila")
    now_naive = datetime.now(ph_tz).replace(tzinfo=None)

    active_tab = request.args.get("tab", "requests")
    search = request.args.get("search", "")

    approved_solo_users = db.session.query(SoloPlan.user_id).filter(
        SoloPlan.status.ilike('approved'),
        or_(SoloPlan.expiry_date.is_(None), SoloPlan.expiry_date > now_naive)
    )

    query = User.query.filter(
        or_(User.role == "member", User.id.in_(approved_solo_users))
    )

    if search:
        search_pattern = f"%{search}%"
        filters = [
            User.name.ilike(search_pattern),
            User.email.ilike(search_pattern),
            User.phone.ilike(search_pattern),
        ]
        if search.isdigit():
            filters.append(User.id == int(search))
        query = query.filter(or_(*filters))

    approved_solo_user_ids = [r[0] for r in approved_solo_users.distinct().all()]
    approved_solo_user_ids_set = set(approved_solo_user_ids)

    all_members = query.order_by(User.created_at.desc()).all()

    # Siguraduhon nga ma-sync ang membership status sa bag-o nga SoloPlan
    created_membership = False
    for member in all_members:
        if member.id in approved_solo_user_ids_set:
            created_membership = _ensure_approved_solo_plan_membership(member) or created_membership

    if created_membership:
        db.session.commit()
        all_members = query.order_by(User.created_at.desc()).all()

    membership_requests = (
        SoloPlan.query.filter_by(status="pending")
        .order_by(SoloPlan.created_at.desc())
        .all()
    )

    return render_template(
        "admin/members.html",
        members=all_members,
        search=search,
        membership_requests=membership_requests,
        active_tab=active_tab,
        approved_solo_user_ids=approved_solo_user_ids,
    )


def _record_member_activity(user_id, activity_type):
    db.session.add(UserActivityLog(
        user_id=user_id,
        activity_type=f"attendance|{activity_type}",
        ip_address=request.remote_addr or "unknown",
    ))

# PERMANENT DELETE ROUTE
@admin_bp.route("/delete_member/<int:user_id>", methods=["POST"])
@login_required
def delete_member(user_id):
    redirect_response = require_super_admin_json()
    if redirect_response:
        return redirect_response

    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        return jsonify({"status": "error", "message": "Cannot delete admin account."}), 400

    try:
        # 1. Clear attendance_logs nga nakakabit sa memberships sang user
        db.session.execute(
            text("""
                DELETE FROM attendance_logs 
                WHERE membership_id IN (
                    SELECT id FROM memberships WHERE user_id = :uid
                )
            """), 
            {"uid": user.id}
        )

        # 2. Clear attendance_logs kon may direct user_id column man ini
        try:
            db.session.execute(text("DELETE FROM attendance_logs WHERE user_id = :uid"), {"uid": user.id})
        except Exception:
            pass  # Sagap lang kon wala sang direct user_id column

        # 3. Clear child tables sang user
        db.session.execute(text("DELETE FROM solo_plans WHERE user_id = :uid"), {"uid": user.id})
        db.session.execute(text("DELETE FROM user_activity_logs WHERE user_id = :uid"), {"uid": user.id})
        db.session.execute(text("DELETE FROM memberships WHERE user_id = :uid"), {"uid": user.id})

        # 4. Permanent Delete sa User
        db.session.delete(user)
        db.session.commit()

        return jsonify({"status": "success", "message": "Member account permanently deleted."})

    except Exception as e:
        db.session.rollback()
        print(f"Permanent Delete Error: {str(e)}")
        return jsonify({"status": "error", "message": f"Failed to delete: {str(e)}"}), 500


# Membership Management Routes
@admin_bp.route("/official_members")
@login_required
def official_members():
    """Display all members with active/expired memberships in card layout."""
    redirect_response = require_admin_or_staff()
    if redirect_response:
        return redirect_response

    search = request.args.get("search", "")
    active_tab = request.args.get("tab", "member_list")
    
    # Get all memberships with their user info
    query = Membership.query.join(User).order_by(Membership.status.desc(), User.name.asc())
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(or_(
            User.name.ilike(search_pattern),
            User.email.ilike(search_pattern),
            User.phone.ilike(search_pattern)
        ))
    
    memberships = query.all()
    
    # Separate active, pending, and expired
    active_memberships = [m for m in memberships if m.is_active]
    pending_memberships = [m for m in memberships if m.status == "pending"]
    expired_memberships = [m for m in memberships if m.status == "expired"]
    
    return render_template(
        "admin/official_members.html",
        active_memberships=active_memberships,
        pending_memberships=pending_memberships,
        expired_memberships=expired_memberships,
        search=search,
        active_tab=active_tab
    )


@admin_bp.route("/api/member/<int:user_or_membership_id>/check-in", methods=["POST"])
@login_required
def membership_check_in(user_or_membership_id):
    """Check in a member with 100% clean timer reset."""
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    membership = Membership.query.filter_by(id=user_or_membership_id).first()
    if membership:
        user = membership.user
    else:
        user = User.query.get_or_404(user_or_membership_id)
        membership = Membership.query.filter_by(user_id=user.id).first()

    now_ph = datetime.utcnow() + timedelta(hours=8)

    latest_plan = SoloPlan.query.filter(
        SoloPlan.user_id == user.id
    ).order_by(SoloPlan.id.desc()).first()

    # Determine hours
    allocated_hours = 1.0
    actual_plan_name = "INDIVIDUAL RATE"

    plan_hours_map = {
        "INDIVIDUAL RATE": 1.0,
        "INDIVIDUAL RATE (4HRS)": 4.0,
        "DAY/NIGHT PASS": 24.0,
        "WEEKLY PASS (DAY/NIGHT)": 168.0,
        "WEEKLY PASS (24HRS)": 168.0,
        "MONTHLY PASS (DAY/NIGHT)": 720.0,
        "MONTHLY PASS (24HRS)": 720.0,
        "WORKSTATION (24HRS)": 720.0,
        "ACTIVE PLAN": 720.0
    }
    
    if latest_plan:
        actual_plan_name = latest_plan.plan_name or "Custom Plan"
        extracted_hours = (
            getattr(latest_plan, 'hours', None) or 
            getattr(latest_plan, 'duration_hours', None) or 
            getattr(latest_plan, 'hours_left', None) or 
            getattr(latest_plan, 'duration', None)
        )
        if extracted_hours is not None:
            try:
                allocated_hours = float(extracted_hours)
            except (ValueError, TypeError):
                clean_name = actual_plan_name.strip().upper()
                allocated_hours = plan_hours_map.get(clean_name, 1.0)
        else:
            clean_name = actual_plan_name.strip().upper()
            allocated_hours = plan_hours_map.get(clean_name, 1.0)
    else:
        actual_plan_name = getattr(membership, 'plan_name', 'Standard Plan') if membership else 'Standard Plan'
        allocated_hours = getattr(membership, 'total_hours', 1.0) if membership else 1.0

    # CRITICAL: COMPUTATION DIRI GID SANG EXACT EXPIRY
    calculated_expiry = now_ph + timedelta(hours=allocated_hours)

    if membership:
        membership.plan_name = actual_plan_name
        membership.start_date = now_ph
        membership.expiry_date = calculated_expiry
        membership.total_hours = float(allocated_hours)
        membership.hours_left = float(allocated_hours)
        membership.is_checked_in = True
        membership.is_checked_out = False
        membership.is_paused = False
        membership.status = "active"
        membership.updated_at = now_ph
        membership.member_list_notification_seen = True


        # FORCE RESET PAUSE ON CHECK IN
        if hasattr(membership, 'total_paused_duration'):
            membership.total_paused_duration = 0
        if hasattr(membership, 'accumulated_paused_seconds'):
            membership.accumulated_paused_seconds = 0
        if hasattr(membership, 'paused_at'):
            membership.paused_at = None

    if latest_plan:
        latest_plan.status = "approved"
        latest_plan.is_paused = False
        latest_plan.start_date = now_ph
        latest_plan.expiry_date = calculated_expiry
        latest_plan.updated_at = now_ph
        if hasattr(latest_plan, 'total_paused_duration'):
            latest_plan.total_paused_duration = 0
        if hasattr(latest_plan, 'accumulated_paused_seconds'):
            latest_plan.accumulated_paused_seconds = 0
        if hasattr(latest_plan, 'paused_at'):
            latest_plan.paused_at = None

    # Close any old open logs
    AttendanceLog.query.filter_by(membership_id=membership.id, check_out_time=None).update({"check_out_time": now_ph})

    # =========================================================
    # CREATE FRESH ATTENDANCE LOG WITH EXACT 0 PAUSED SECONDS
    # =========================================================
    log = AttendanceLog(
        membership_id=membership.id,
        check_in_time=now_ph,
        is_paused=False,
        accumulated_paused_seconds=0  # FORCE 0 HERE FOR MEMBER DASHBOARD
    )
    db.session.add(log)
    _record_member_activity(user.id, "Check-In")
    db.session.commit()
    db.session.expire_all()

    return jsonify({
        "status": "success",
        "message": f"{user.name} checked in successfully!",
        "check_in_time": now_ph.isoformat(),
        "expires_on": calculated_expiry.isoformat(),
        "new_plan_duration": f"{int(allocated_hours):02d}h 00m 00s",
        "new_log": {
            "action": "Check-In",
            "description": "Session started",
            "timestamp": now_ph.strftime("%b %d, %Y - %I:%M %p")
        }
    })

@admin_bp.route("/api/member/<int:user_or_membership_id>/toggle-pause", methods=["POST"])
@login_required
def membership_toggle_pause(user_or_membership_id):
    """Toggle Pause / Resume state sang active session sang member/solo plan."""
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    # 1. Pangitaon ang Membership by ID or by User ID
    membership = Membership.query.filter_by(id=user_or_membership_id).first()
    if not membership:
        membership = Membership.query.filter_by(user_id=user_or_membership_id).order_by(Membership.id.desc()).first()

    if not membership or not membership.is_checked_in:
        return jsonify({
            "status": "error", 
            "message": "No active checked-in session found for this user."
        }), 400

    now_ph = datetime.utcnow() + timedelta(hours=8)
    
    # 2. Pangitaon ang active AttendanceLog nga wala pa sing check_out_time
    current_log = AttendanceLog.query.filter_by(
        membership_id=membership.id,
        check_out_time=None
    ).order_by(AttendanceLog.id.desc()).first()

    # 3. Pangitaon ang Active / Approved SoloPlan sang User
    active_solo = SoloPlan.query.filter(
        SoloPlan.user_id == membership.user_id,
        SoloPlan.status.ilike("approved")
    ).order_by(SoloPlan.id.desc()).first()

    # Determine current status kag i-toggle
    is_currently_paused = getattr(membership, 'is_paused', False)
    target_pause_state = not is_currently_paused
    paused_seconds = 0

    if target_pause_state is False and is_currently_paused:
        _, _, occupied_count = get_common_area_dashboard_counts(now_ph.replace(tzinfo=None))
        if occupied_count >= 70:
            return jsonify({
                "status": "error",
                "message": "Cannot resume session: Common Area is currently at maximum capacity.",
            }), 400

    # ==========================================
    # A. UPDATE MEMBERSHIP STATE & STATUS STRING
    # ==========================================
    membership.is_paused = target_pause_state
    
    # IMPORTANTE: I-update ang status column sang Membership!
    if hasattr(membership, 'status'):
        membership.status = "active"

    # ==========================================
    # B. TOGGLE ATTENDANCE LOG PAUSE STATE
    # ==========================================
    if current_log:
        current_log.is_paused = target_pause_state
        if hasattr(current_log, 'status'):
            current_log.status = "Paused" if target_pause_state else "Checked In"

        if target_pause_state:
            current_log.paused_at = now_ph
        else:
            if current_log.paused_at:
                paused_seconds = int((now_ph - current_log.paused_at).total_seconds())
                current_log.accumulated_paused_seconds = (current_log.accumulated_paused_seconds or 0) + paused_seconds
            current_log.paused_at = None

    # ==========================================
    # C. TOGGLE SOLOPLAN PAUSE STATE
    # ==========================================
    if active_solo:
        active_solo.is_paused = target_pause_state
        if target_pause_state:
            active_solo.paused_at = now_ph
        else:
            if active_solo.paused_at:
                paused_seconds = max(
                    paused_seconds,
                    int((now_ph - active_solo.paused_at).total_seconds()),
                )
            active_solo.paused_at = None

    if not target_pause_state and paused_seconds > 0:
        pause_delta = timedelta(seconds=paused_seconds)
        if membership.expiry_date:
            membership.expiry_date = membership.expiry_date + pause_delta
        if active_solo and active_solo.expiry_date:
            active_solo.expiry_date = active_solo.expiry_date + pause_delta

    # Save sa Database
    _record_member_activity(membership.user_id, "Paused" if target_pause_state else "Resumed")
    db.session.commit()

    user_name = membership.user.name if (membership and membership.user) else "Member"
    action_str = "PAUSED" if target_pause_state else "RESUMED"
    new_status_str = "Paused" if target_pause_state else "Checked In"
    remaining_seconds = 0
    if current_log and current_log.check_in_time:
        reference_time = now_ph if not target_pause_state else (current_log.paused_at or now_ph)
        accumulated_paused = current_log.accumulated_paused_seconds or 0
        elapsed_seconds = max(0, int((reference_time - current_log.check_in_time).total_seconds() - accumulated_paused))
        remaining_seconds = max(0, int(float(membership.total_hours or 0) * 3600) - elapsed_seconds)
    hours = remaining_seconds // 3600
    minutes = (remaining_seconds % 3600) // 60
    seconds = remaining_seconds % 60
    
    return jsonify({
        "status": "success",
        "message": f"Session for {user_name} is now {action_str.lower()}.",
        "is_paused": target_pause_state,
        "member_status": new_status_str,
        "user_name": user_name
        ,"paused_seconds": paused_seconds
        ,"new_end_time": membership.expiry_date.isoformat() if membership.expiry_date else None
        ,"formatted_end_time": membership.expiry_date.strftime("%I:%M %p") if membership.expiry_date else None
        ,"remaining_seconds": remaining_seconds
        ,"remaining_time_str": f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
        ,"log_entry": {
            "action": "Paused" if target_pause_state else "Resumed",
            "description": "Session paused" if target_pause_state else "Session resumed",
            "timestamp": now_ph.strftime("%b %d, %Y - %I:%M %p")
        }
    })


@admin_bp.route("/api/member/<int:user_or_membership_id>/check-out", methods=["POST"])
@login_required
def membership_check_out(user_or_membership_id):
    """Check out a member/solo user, end active session, and deduct hours dynamically."""
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    # Pangitaon ang Membership O ang User ID
    membership = Membership.query.filter_by(id=user_or_membership_id).first()
    if not membership:
        membership = Membership.query.filter_by(user_id=user_or_membership_id).first()

    target_user_id = membership.user_id if membership else user_or_membership_id

    # Pangitaon ang tanan nga active / approved SoloPlan sang user
    active_solos = SoloPlan.query.filter(
        SoloPlan.user_id == target_user_id,
        SoloPlan.status.ilike("approved")
    ).all()

    now_ph = datetime.utcnow() + timedelta(hours=8)

    # Close Attendance Log & Deduct Hours
    m_id = membership.id if membership else None
    if m_id:
        current_log = AttendanceLog.query.filter_by(
            membership_id=m_id,
            check_out_time=None
        ).first()

        if current_log:
            # FIX: Store the exact termination timestamp before committing the session close.
            session_end_time = now_ph
            for field_name in ("ended_at", "actual_end_time", "check_out_time"):
                if hasattr(current_log, field_name):
                    setattr(current_log, field_name, session_end_time)
                    break
            else:
                current_log.check_out_time = session_end_time

            # --- UPDATED DURATION COMPUTATION WITH PAUSE DEDUCTION ---
            total_elapsed_seconds = (now_ph - current_log.check_in_time).total_seconds()
            accumulated_pause = current_log.accumulated_paused_seconds or 0

            # Kon guin-check out samtang naga-pause, idagdag man ang unrecorded pause time
            if current_log.is_paused and current_log.paused_at:
                accumulated_pause += (now_ph - current_log.paused_at).total_seconds()

            active_seconds = max(0, total_elapsed_seconds - accumulated_pause)
            duration_hours = active_seconds / 3600
            hours_deducted = round(duration_hours, 2)

            if membership and membership.hours_left is not None:
                if hours_deducted > membership.hours_left:
                    hours_deducted = membership.hours_left
                membership.hours_left = round(max(0.0, membership.hours_left - hours_deducted), 2)
                if membership.hours_left <= 0:
                    membership.status = "expired"

            current_log.hours_deducted = hours_deducted
            current_log.is_paused = False
            current_log.paused_at = None
            _record_member_activity(target_user_id, "Checked-Out")

    # I-set ang status flags sa CHECKED OUT
    if membership:
        membership.is_checked_in = False
        membership.is_checked_out = True

        if membership.status and membership.status.lower() in ["checked in", "checked_in", "paused", "session paused", "session_paused"]:
            membership.status = "active" if membership.hours_left > 0 else "expired"



        membership.updated_at = now_ph

    for solo in active_solos:
        solo.status = "checked_out"
        solo.updated_at = now_ph

    db.session.commit()

    user_name = membership.user.name if (membership and membership.user) else "User"

    return jsonify({
        "status": "success",
        "message": f"{user_name} checked out successfully!",
        "hours_left": membership.hours_left if membership else 0.0
    })


@admin_bp.route("/api/member/<int:membership_id>/attendance", methods=["GET"])
@login_required
def member_attendance_history(membership_id):
    """Get attendance history using direct raw database formatting."""
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    membership = Membership.query.get_or_404(membership_id)
    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    
    logs = membership.attendance_logs.order_by(AttendanceLog.check_in_time.desc()).all()

    active_log = next((log for log in logs if log.check_out_time is None), None)
    remaining_seconds = max(0, int(round(float(membership.hours_left or 0) * 3600)))
    is_paused = bool(getattr(membership, "is_paused", False))
    if active_log and active_log.check_in_time and membership.is_checked_in:
        check_in_time = active_log.check_in_time
        if check_in_time.tzinfo is None:
            check_in_time = ph_tz.localize(check_in_time)

        is_paused = is_paused or bool(getattr(active_log, "is_paused", False))
        reference_time = now_ph
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
    
    attendance_data = []

    activity_query = UserActivityLog.query.filter(
        UserActivityLog.user_id == membership.user_id,
        UserActivityLog.activity_type.like("attendance|%")
    )
    if active_log and active_log.check_in_time:
        activity_query = activity_query.filter(
            UserActivityLog.activity_time >= active_log.check_in_time
        )
    else:
        activity_query = activity_query.filter(UserActivityLog.id == -1)
    activity_rows = activity_query.order_by(UserActivityLog.activity_time.desc()).limit(50).all()

    activity_data = []
    for activity in activity_rows:
        activity_name = activity.activity_type.split("|", 1)[-1]
        activity_time = activity.activity_time
        activity_details = {
            "Check-In": "Session started",
            "Paused": "Session paused",
            "Resumed": "Session resumed",
        }.get(activity_name, "Session ended")
        if activity_name == "Checked-Out":
            latest_completed_log = next((log for log in logs if log.check_out_time), None)
            if latest_completed_log and latest_completed_log.hours_deducted:
                activity_details = (
                    f"{decimal_hours_to_readable(latest_completed_log.hours_deducted)} used; "
                    f"{membership.hours_left:.2f} hrs remaining"
                )
        activity_data.append({
            "id": f"activity-{activity.id}",
            "event": activity_name,
            "timestamp": activity_time.strftime("%b %d, %Y - %I:%M %p") if activity_time else "-",
            "details": activity_details,
        })

    for log in logs:
        c_in = log.check_in_time
        c_out = getattr(log, "check_out_time", None) or getattr(log, "actual_end_time", None) or getattr(log, "ended_at", None)

        # Direct String Formatting (%b %d, %Y kag %I:%M %p)
        date_str = c_in.strftime("%b %d, %Y") if c_in else "-"
        check_in_str = c_in.strftime("%I:%M %p") if c_in else "-"
        check_out_str = c_out.strftime("%I:%M %p") if c_out else "-"

        attendance_data.append({
            "id": log.id,
            "date": date_str,
            "check_in": check_in_str,
            "check_out": check_out_str,
            "actual_end_time": c_out.isoformat() if c_out else None,
            "hours": decimal_hours_to_readable(log.hours_deducted) if (log.hours_deducted and log.hours_deducted > 0) else "-"
        })

    # Older sessions predate discrete activity rows, so retain useful history for them.
    if not activity_data:
        for log in logs[:25]:
            if log.check_in_time:
                activity_data.append({
                    "id": f"check-in-{log.id}",
                    "event": "Check-In",
                    "timestamp": log.check_in_time.strftime("%b %d, %Y - %I:%M %p"),
                    "details": "Session started",
                })
            if log.check_out_time:
                activity_data.append({
                    "id": f"check-out-{log.id}",
                    "event": "Checked-Out",
                    "timestamp": log.check_out_time.strftime("%b %d, %Y - %I:%M %p"),
                    "details": f"{decimal_hours_to_readable(log.hours_deducted) if log.hours_deducted else '-'} used",
                })
    
    return jsonify({
        "status": "success",
        "member_name": membership.user.name if membership.user else "Walk-in / Guest",
        "total_hours": membership.total_hours,
        "hours_left": membership.hours_left,
        "remaining_seconds": remaining_seconds,
        "check_in_time": active_log.check_in_time.isoformat() if active_log and active_log.check_in_time else None,
        "is_checked_in": bool(membership.is_checked_in),
        "is_paused": is_paused,
        "attendance": attendance_data,
        "activity_logs": activity_data,
    })


@admin_bp.route("/api/dashboard/common-area-occupants", methods=["GET"])
@login_required
def common_area_occupants():
    """Get list of members currently checked in (for Common Area display on dashboard)."""
    redirect_response = require_admin_or_staff_json()
    if redirect_response:
        return redirect_response

    ph_tz = pytz.timezone("Asia/Manila")
    now_ph = datetime.now(ph_tz)
    now_naive = now_ph.replace(tzinfo=None)
    auto_start_due_reservations(now_ph.replace(tzinfo=None))

    approved_active_plan_users = db.session.query(SoloPlan.user_id).filter(
        func.lower(SoloPlan.status).in_(["approved", "active"]),
        or_(
            SoloPlan.expiry_date.is_(None),
            SoloPlan.expiry_date >= now_naive,
        ),
    )
    active_logs = db.session.query(AttendanceLog).join(Membership).filter(
        Membership.status == "active",
        Membership.is_checked_in == True,
        Membership.is_paused == False,
        AttendanceLog.is_paused == False,
        AttendanceLog.check_out_time.is_(None),
        Membership.user_id.in_(approved_active_plan_users),
    ).all()

    occupants = []

    for active_log in active_logs:
        membership = active_log.membership
        _expire_membership_if_needed(membership)

        if membership.status != "active" or not membership.is_checked_in:
            continue

        if active_log and active_log.check_in_time:
            check_in_dt = active_log.check_in_time

            if check_in_dt.tzinfo is None:
                check_in_dt = ph_tz.localize(check_in_dt)

            # Check paused state from AttendanceLog and Membership
            session_is_paused = bool(
                getattr(active_log, "is_paused", False)
            )

            membership_is_paused = bool(
                getattr(membership, "is_paused", False)
            )

            is_paused = session_is_paused or membership_is_paused

            if is_paused:
                continue

            # Get pause timestamp
            paused_at = (
                getattr(active_log, "paused_at", None)
                or getattr(membership, "paused_at", None)
            )

            if paused_at and paused_at.tzinfo is None:
                paused_at = ph_tz.localize(paused_at)

            # Get previously accumulated paused seconds
            accumulated_paused = (
                getattr(active_log, "accumulated_paused_seconds", 0)
                or getattr(membership, "accumulated_paused_seconds", 0)
                or 0
            )

            # Calculate current pause duration if currently paused
            current_pause_seconds = 0

            if is_paused and paused_at:
                current_pause_seconds = max(
                    0,
                    int((now_ph - paused_at).total_seconds())
                )

            # Total pause duration including the current pause
            total_pause_seconds = (
                accumulated_paused + current_pause_seconds
            )

            # Freeze Time Used while paused
            if is_paused and paused_at:
                reference_time = paused_at
            else:
                reference_time = now_ph

            raw_elapsed = (
                reference_time - check_in_dt
            ).total_seconds()

            elapsed_seconds = max(
                0,
                int(raw_elapsed - accumulated_paused)
            )

            # Calculate adjusted end time
            adjusted_end_time = None

            if membership.expiry_date:
                expiry_dt = membership.expiry_date

                if expiry_dt.tzinfo is None:
                    expiry_dt = ph_tz.localize(expiry_dt)

                adjusted_end_time = (
                    expiry_dt +
                    timedelta(seconds=total_pause_seconds)
                )

            formatted_check_in = check_in_dt.strftime("%I:%M %p")

            epoch_time_ms = int(
                check_in_dt.timestamp() * 1000
            )

            active_reservation = Reservation.query.filter(
                Reservation.user_id == membership.user_id,
                Reservation.status.in_(["Checked-in", "IN_PROGRESS", "Walk-in"]),
                Reservation.start_time <= now_ph.replace(tzinfo=None),
                or_(
                    Reservation.end_time >= now_ph.replace(tzinfo=None),
                    Reservation.is_open_time.is_(True),
                    Reservation.end_time.is_(None),
                ),
            ).order_by(Reservation.start_time.desc()).first()
            display_name = (
                active_reservation.customer_name.strip()
                if active_reservation and active_reservation.customer_name
                else (membership.user.name if membership.user else "Walk-in / Guest")
            )

            occupants.append({
                "id": membership.id,
                "name": display_name,
                "check_in_time": check_in_dt.isoformat(),
                "check_in_ms": epoch_time_ms,
                "formatted_check_in": formatted_check_in,
                "elapsed_seconds": elapsed_seconds,
                "is_paused": is_paused,
                "hours_left": membership.hours_left,
                "end_time": (
                    adjusted_end_time.isoformat()
                    if adjusted_end_time
                    else None
                )
            })

    return jsonify({
        "status": "success",
        "count": len(occupants),
        "occupants": occupants
    })