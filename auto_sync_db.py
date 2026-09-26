#!/usr/bin/env python3
"""Synchronize database tables and columns with the application's SQLAlchemy models."""

import os
import sys

from sqlalchemy import inspect, text


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_DIRECTORY = os.path.join(PROJECT_ROOT, "high_end_ws_lounge")

if APP_DIRECTORY not in sys.path:
    sys.path.insert(0, APP_DIRECTORY)

from run import app, db  # noqa: E402


def sync_database():
    """Create missing tables and add model columns absent from existing tables."""
    added_columns = 0
    failed_columns = 0

    with app.app_context():
        engine = db.engine

        try:
            db.create_all()
            print("Checked and created missing tables.")
        except Exception as error:
            print(f"ERROR: Could not create missing tables: {error}")

        inspector = inspect(engine)
        preparer = engine.dialect.identifier_preparer

        for model_table in db.metadata.sorted_tables:
            table_name = model_table.name

            try:
                if not inspector.has_table(table_name, schema=model_table.schema):
                    print(f"Skipping {table_name}: table is not available.")
                    continue

                existing_columns = {
                    column["name"]
                    for column in inspector.get_columns(table_name, schema=model_table.schema)
                }

                table_identifier = preparer.quote(table_name)
                for model_column in model_table.columns:
                    if model_column.name in existing_columns:
                        continue

                    try:
                        column_identifier = preparer.quote(model_column.name)
                        column_type = model_column.type.compile(dialect=engine.dialect)
                        statement = text(
                            f"ALTER TABLE {table_identifier} "
                            f"ADD COLUMN {column_identifier} {column_type}"
                        )
                        with engine.begin() as connection:
                            connection.execute(statement)
                        added_columns += 1
                        print(
                            f"Added column {table_name}.{model_column.name} "
                            f"({column_type})."
                        )
                    except Exception as error:
                        failed_columns += 1
                        print(
                            f"ERROR: Could not add {table_name}.{model_column.name}: "
                            f"{error}"
                        )

                inspector = inspect(engine)
            except Exception as error:
                print(f"ERROR: Could not inspect table {table_name}: {error}")

    print(
        f"Database synchronization complete. Added {added_columns} column(s); "
        f"{failed_columns} column operation(s) failed."
    )


if __name__ == "__main__":
    sync_database()