import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    app = create_app(path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    if os.path.exists(path):
        os.remove(path)


def login(client):
    return client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)


def test_login_required(client):
    assert client.get("/").status_code == 302


def test_login_and_dashboard(client):
    assert b"Dashboard" in login(client).data


def test_all_pages_load(client):
    login(client)
    for url in ["/", "/students", "/students/add", "/rooms", "/rooms/add", "/rooms/allocate", "/fees", "/complaints"]:
        assert client.get(url).status_code == 200, url


def test_add_student(client):
    login(client)
    r = client.post("/students/add", data={"roll_number": "x1", "name": "Test", "email": "t@x.com",
                                           "phone": "9999999999", "course": "BCA", "room_id": ""}, follow_redirects=True)
    assert b"added successfully" in r.data


def test_room_capacity_blocked(client):
    login(client)
    r = client.post("/rooms/allocate", data={"student_id": "6", "room_id": "1"}, follow_redirects=True)
    assert b"full capacity" in r.data


def test_fee_and_complaint(client):
    login(client)
    r = client.post("/fees", data={"student_id": "1", "amount": "100", "payment_month": "Nov 2026",
                                   "payment_date": "2026-11-01", "payment_method": "UPI"}, follow_redirects=True)
    assert b"Recorded" in r.data
    r = client.post("/complaints", data={"student_id": "1", "title": "T", "category": "Other",
                                         "description": "d"}, follow_redirects=True)
    assert b"registered" in r.data
