#!/usr/bin/env python3
"""Clear test data while preserving admin accounts and system configuration."""

import os
import sys


PROJECT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "high_end_ws_lounge")
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

from database_fixed import (  # noqa: E402
    AttendanceLog,
    DailyReport,
    Membership,
    Reservation,
    ReservationAddOn,
    SoloPlan,
    TimeLog,
    User,
    UserActivityLog,
    WalkinAddOn,
    WalkinReservation,
    db,
)
from run import create_app  # noqa: E402
from sqlalchemy import func, or_  # noqa: E402


app = create_app()


TEST_DATA_MODELS = (
    ReservationAddOn,
    WalkinAddOn,
    AttendanceLog,
    WalkinReservation,
    TimeLog,
    UserActivityLog,
    DailyReport,
    SoloPlan,
    Membership,
    Reservation,
)


def reset_system_data():
    with app.app_context():
        print("Starting system data reset...")
        deleted = {}

        try:
            for model in TEST_DATA_MODELS:
                deleted[model.__tablename__] = db.session.query(model).delete(
                    synchronize_session=False
                )

            deleted["users"] = User.query.filter(
                or_(User.role.is_(None), func.lower(User.role) != "admin")
            ).delete(synchronize_session=False)

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        for table_name, count in deleted.items():
            print(f"Cleared {count} records from {table_name}.")

        print("System data reset complete.")
        print("Preserved: admin accounts, rooms, payment settings, and add-on configuration.")


if __name__ == "__main__":
    reset_system_data()
