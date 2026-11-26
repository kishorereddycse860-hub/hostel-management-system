"""
Database helper module for the Hostel Management System.
Handles SQLite connections, table creation with foreign keys, and initial sample data.
"""

import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "hostel.db")


def get_db_connection(db_path=None):
    """Create and return a SQLite connection with dictionary-like row access."""
    path = db_path or os.environ.get("HOSTEL_DB_PATH") or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Ensure SQLite enforces FOREIGN KEY constraints on every connection.
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=None, seed=True):
    """Create all database tables if they do not exist, and optionally seed sample data."""
    conn = get_db_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_number TEXT UNIQUE NOT NULL,
                room_type TEXT NOT NULL CHECK(room_type IN ('Single', 'Double', 'Triple', 'Dormitory')),
                capacity INTEGER NOT NULL CHECK(capacity > 0),
                monthly_fee REAL NOT NULL CHECK(monthly_fee >= 0),
                description TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                roll_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                course TEXT NOT NULL,
                room_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS fees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                payment_month TEXT NOT NULL,
                payment_date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                remarks TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending'
                    CHECK(status IN ('Pending', 'In Progress', 'Resolved')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()

        if seed:
            seed_sample_data(conn)
    finally:
        conn.close()


def seed_sample_data(conn):
    """Populate initial demo data only when the database has no admin accounts yet."""
    existing_admin = conn.execute("SELECT COUNT(*) AS count FROM admins").fetchone()["count"]
    if existing_admin > 0:
        return

    # 1. Default Admin Account (password is securely hashed)
    conn.execute(
        "INSERT INTO admins (username, password_hash, full_name) VALUES (?, ?, ?)",
        ("admin", generate_password_hash("admin123"), "Hostel Warden"),
    )

    # 2. Sample Rooms
    sample_rooms = [
        ("101", "Single", 1, 6500.0, "Ground floor single room with attached study desk"),
        ("102", "Double", 2, 5000.0, "Ground floor two-sharing ventilated room"),
        ("201", "Triple", 3, 4000.0, "First floor three-sharing room near balcony"),
        ("202", "Double", 2, 5000.0, "First floor two-sharing quiet corner room"),
        ("301", "Dormitory", 4, 3200.0, "Second floor four-bed student dormitory"),
    ]
    conn.executemany(
        """
        INSERT INTO rooms (room_number, room_type, capacity, monthly_fee, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_rooms,
    )

    # Fetch room IDs by room_number so student allocation links cleanly
    room_rows = conn.execute("SELECT id, room_number FROM rooms").fetchall()
    room_map = {row["room_number"]: row["id"] for row in room_rows}

    # 3. Sample Students (5 assigned to rooms, 1 unassigned for demo allocation)
    sample_students = [
        ("CS2024001", "Aarav Sharma", "aarav.sharma@college.edu", "9876543210", "B.Tech CSE", room_map["101"]),
        ("CS2024002", "Priya Nair", "priya.nair@college.edu", "9876543211", "B.Tech CSE", room_map["102"]),
        ("EC2024003", "Rohan Verma", "rohan.verma@college.edu", "9876543212", "B.Tech ECE", room_map["102"]),
        ("ME2024004", "Sneha Patel", "sneha.patel@college.edu", "9876543213", "B.Tech Mechanical", room_map["201"]),
        ("IT2024005", "Kabir Singh", "kabir.singh@college.edu", "9876543214", "B.Sc IT", room_map["201"]),
        ("BA2024006", "Ananya Gupta", "ananya.gupta@college.edu", "9876543215", "BBA", None),
    ]
    conn.executemany(
        """
        INSERT INTO students (roll_number, name, email, phone, course, room_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        sample_students,
    )

    student_rows = conn.execute("SELECT id, roll_number FROM students").fetchall()
    student_map = {row["roll_number"]: row["id"] for row in student_rows}

    # 4. Sample Fee Payments
    sample_fees = [
        (student_map["CS2024001"], 6500.0, "November 2026", "2026-11-03", "UPI", "Monthly hostel rent paid"),
        (student_map["CS2024002"], 5000.0, "November 2026", "2026-11-04", "Bank Transfer", "On-time payment"),
        (student_map["EC2024003"], 5000.0, "November 2026", "2026-11-05", "Cash", "Receipt #103"),
        (student_map["ME2024004"], 4000.0, "November 2026", "2026-11-07", "Card", "Monthly rent"),
    ]
    conn.executemany(
        """
        INSERT INTO fees (student_id, amount, payment_month, payment_date, payment_method, remarks)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        sample_fees,
    )

    # 5. Sample Complaints
    sample_complaints = [
        (
            student_map["CS2024002"],
            "Ceiling fan making noise",
            "Electricity",
            "The ceiling fan in Room 102 wobbles and makes noise at high speed.",
            "Pending",
        ),
        (
            student_map["ME2024004"],
            "Slow Wi-Fi signal near Room 201",
            "Wi-Fi",
            "Internet speed drops frequently in the evening hours.",
            "In Progress",
        ),
        (
            student_map["CS2024001"],
            "Tap leakage fixed",
            "Plumbing",
            "Washbasin tap was dripping; plumber inspected.",
            "Resolved",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO complaints (student_id, title, category, description, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        sample_complaints,
    )

    conn.commit()
