import os
import sys
import uuid
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database_fixed import User, db

from run import create_app
from admin import normalize_common_area_session_window


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        db.create_all()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_login_redirects_on_success(app, client):
    with app.app_context():
        email = f"test-{uuid.uuid4().hex[:8]}@example.com"
        user = User(name="test", email=email, role="member")
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()

        response = client.post("/auth/login", data={"email": email, "password": "testpass"})
        assert response.status_code == 302


def test_common_area_default_is_eight_hour_open_timer():
    start = datetime(2026, 9, 8, 10, 0)
    normalized = normalize_common_area_session_window("common area", start)

    assert normalized["is_open_time"] is True
    assert normalized["start_time"] == start
    assert normalized["end_time"] == start + timedelta(hours=8)
