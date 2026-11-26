"""
Hostel Management System - Main Flask Application
College Mini Project built with Python, Flask, SQLite, Bootstrap 5, and JavaScript.
"""

import os
import re
from datetime import date
from functools import wraps
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database import get_db_connection, init_db


def _is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _is_valid_phone(phone):
    digits = re.sub(r"[\s+\-]", "", phone)
    return digits.isdigit() and 7 <= len(digits) <= 15


def _get_rooms_with_occupancy(conn, include_room_id=None, only_available=True):
    """Return rooms along with current occupant counts."""
    rows = conn.execute(
        """
        SELECT r.*, COUNT(s.id) AS occupied
        FROM rooms r
        LEFT JOIN students s ON s.room_id = r.id
        GROUP BY r.id
        ORDER BY r.room_number
        """
    ).fetchall()
    if not only_available:
        return rows
    return [
        r for r in rows
        if r["occupied"] < r["capacity"] or (include_room_id is not None and r["id"] == include_room_id)
    ]


def _check_room_capacity(conn, room_id, exclude_student_id=None):
    """Return (is_valid, error_message) for allocating a student to room_id."""
    room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if not room:
        return False, "Selected room does not exist."

    if exclude_student_id is not None:
        occupied = conn.execute(
            "SELECT COUNT(*) AS c FROM students WHERE room_id = ? AND id != ?",
            (room_id, exclude_student_id),
        ).fetchone()["c"]
    else:
        occupied = conn.execute(
            "SELECT COUNT(*) AS c FROM students WHERE room_id = ?", (room_id,)
        ).fetchone()["c"]

    if occupied >= room["capacity"]:
        return False, f"Room {room['room_number']} is already at full capacity ({room['capacity']} beds)."
    return True, None


def create_app(db_path=None):
    """Application factory that configures Flask, initializes SQLite, and registers routes."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "hostel-mini-project-secret-key-2026")
    app.config["DATABASE"] = db_path or os.environ.get("HOSTEL_DB_PATH")

    # Initialize database tables and seed demo data on startup
    init_db(app.config["DATABASE"])

    def get_conn():
        return get_db_connection(app.config["DATABASE"])

    @app.context_processor
    def inject_helpers():
        def has_endpoint(endpoint_name):
            return endpoint_name in app.view_functions

        return {"has_endpoint": has_endpoint}

    def login_required(view_func):
        """Protect admin routes by ensuring an admin user is logged into the session."""

        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if "admin_id" not in session:
                flash("Please log in as admin to access that page.", "warning")
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)

        return wrapped_view

    # ------------------------------------------------------------------
    # MODULE 1: ADMIN LOGIN & LOGOUT
    # ------------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "admin_id" in session:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Both username and password are required.", "danger")
                return render_template("login.html")

            conn = get_conn()
            try:
                admin = conn.execute(
                    "SELECT * FROM admins WHERE username = ?", (username,)
                ).fetchone()
            finally:
                conn.close()

            if admin and check_password_hash(admin["password_hash"], password):
                session.clear()
                session["admin_id"] = admin["id"]
                session["admin_username"] = admin["username"]
                session["admin_name"] = admin["full_name"]
                flash(f"Welcome back, {admin['full_name']}!", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid username or password.", "danger")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out successfully.", "info")
        return redirect(url_for("login"))

    # ------------------------------------------------------------------
    # MODULE 2: DASHBOARD
    # ------------------------------------------------------------------
    @app.route("/")
    @login_required
    def dashboard():
        conn = get_conn()
        try:
            total_students = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
            total_rooms = conn.execute("SELECT COUNT(*) AS c FROM rooms").fetchone()["c"]
            total_capacity = conn.execute(
                "SELECT COALESCE(SUM(capacity), 0) AS c FROM rooms"
            ).fetchone()["c"]
            occupied_beds = conn.execute(
                "SELECT COUNT(*) AS c FROM students WHERE room_id IS NOT NULL"
            ).fetchone()["c"]
            available_beds = max(0, total_capacity - occupied_beds)
            pending_complaints = conn.execute(
                "SELECT COUNT(*) AS c FROM complaints WHERE status = 'Pending'"
            ).fetchone()["c"]
            fees_collected = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM fees"
            ).fetchone()["total"]

            recent_fees = conn.execute(
                """
                SELECT f.amount, f.payment_month, f.payment_date,
                       s.name AS student_name, s.roll_number
                FROM fees f
                JOIN students s ON f.student_id = s.id
                ORDER BY f.payment_date DESC, f.id DESC
                LIMIT 5
                """
            ).fetchall()

            recent_complaints = conn.execute(
                """
                SELECT c.title, c.category, c.status, s.name AS student_name
                FROM complaints c
                JOIN students s ON c.student_id = s.id
                ORDER BY c.id DESC
                LIMIT 5
                """
            ).fetchall()
        finally:
            conn.close()

        stats = {
            "total_students": total_students,
            "total_rooms": total_rooms,
            "occupied_beds": occupied_beds,
            "available_beds": available_beds,
            "pending_complaints": pending_complaints,
            "fees_collected": fees_collected,
        }

        return render_template(
            "dashboard.html",
            active_page="dashboard",
            stats=stats,
            recent_fees=recent_fees,
            recent_complaints=recent_complaints,
        )

    # ------------------------------------------------------------------
    # MODULE 3: STUDENT MANAGEMENT (VIEW, SEARCH, ADD, EDIT, DELETE)
    # ------------------------------------------------------------------
    def _validate_student_form(conn, form, exclude_student_id=None):
        """Validate student form fields and return (cleaned_data, errors)."""
        roll_number = form.get("roll_number", "").strip().upper()
        name = form.get("name", "").strip()
        email = form.get("email", "").strip()
        phone = form.get("phone", "").strip()
        course = form.get("course", "").strip()
        room_raw = form.get("room_id", "").strip()

        errors = []
        if not roll_number:
            errors.append("Roll number is required.")
        if not name:
            errors.append("Full name is required.")
        if not email or not _is_valid_email(email):
            errors.append("Please enter a valid email address.")
        if not phone or not _is_valid_phone(phone):
            errors.append("Please enter a valid phone number (7–15 digits).")
        if not course:
            errors.append("Course / department is required.")

        # Unique roll number check
        if roll_number:
            if exclude_student_id is not None:
                dup = conn.execute(
                    "SELECT id FROM students WHERE roll_number = ? AND id != ?",
                    (roll_number, exclude_student_id),
                ).fetchone()
            else:
                dup = conn.execute(
                    "SELECT id FROM students WHERE roll_number = ?", (roll_number,)
                ).fetchone()
            if dup:
                errors.append(f"Roll number '{roll_number}' is already registered.")

        room_id = None
        if room_raw:
            if not room_raw.isdigit():
                errors.append("Invalid room selection.")
            else:
                room_id = int(room_raw)
                ok, room_err = _check_room_capacity(conn, room_id, exclude_student_id)
                if not ok:
                    errors.append(room_err)

        cleaned = {
            "roll_number": roll_number,
            "name": name,
            "email": email,
            "phone": phone,
            "course": course,
            "room_id": room_id,
        }
        return cleaned, errors

    @app.route("/students")
    @login_required
    def students():
        search_query = request.args.get("q", "").strip()
        conn = get_conn()
        try:
            if search_query:
                like_term = f"%{search_query}%"
                student_list = conn.execute(
                    """
                    SELECT s.*, r.room_number
                    FROM students s
                    LEFT JOIN rooms r ON s.room_id = r.id
                    WHERE s.roll_number LIKE ?
                       OR s.name LIKE ?
                       OR s.phone LIKE ?
                       OR s.course LIKE ?
                       OR s.email LIKE ?
                    ORDER BY s.id DESC
                    """,
                    (like_term, like_term, like_term, like_term, like_term),
                ).fetchall()
            else:
                student_list = conn.execute(
                    """
                    SELECT s.*, r.room_number
                    FROM students s
                    LEFT JOIN rooms r ON s.room_id = r.id
                    ORDER BY s.id DESC
                    """
                ).fetchall()
        finally:
            conn.close()

        return render_template(
            "students.html",
            active_page="students",
            students=student_list,
            search_query=search_query,
        )

    @app.route("/students/add", methods=["GET", "POST"])
    @login_required
    def add_student():
        conn = get_conn()
        try:
            if request.method == "POST":
                cleaned, errors = _validate_student_form(conn, request.form)
                if errors:
                    for err in errors:
                        flash(err, "danger")
                    available_rooms = _get_rooms_with_occupancy(conn)
                    return render_template(
                        "student_form.html",
                        active_page="students",
                        student=None,
                        available_rooms=available_rooms,
                        form_data=request.form,
                    )

                conn.execute(
                    """
                    INSERT INTO students (roll_number, name, email, phone, course, room_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cleaned["roll_number"],
                        cleaned["name"],
                        cleaned["email"],
                        cleaned["phone"],
                        cleaned["course"],
                        cleaned["room_id"],
                    ),
                )
                conn.commit()
                flash(f"Student '{cleaned['name']}' added successfully.", "success")
                return redirect(url_for("students"))

            available_rooms = _get_rooms_with_occupancy(conn)
        finally:
            conn.close()

        return render_template(
            "student_form.html",
            active_page="students",
            student=None,
            available_rooms=available_rooms,
            form_data={},
        )

    @app.route("/students/edit/<int:student_id>", methods=["GET", "POST"])
    @login_required
    def edit_student(student_id):
        conn = get_conn()
        try:
            student = conn.execute(
                "SELECT * FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            if not student:
                flash("Student not found.", "danger")
                return redirect(url_for("students"))

            if request.method == "POST":
                cleaned, errors = _validate_student_form(
                    conn, request.form, exclude_student_id=student_id
                )
                if errors:
                    for err in errors:
                        flash(err, "danger")
                    available_rooms = _get_rooms_with_occupancy(
                        conn, include_room_id=student["room_id"]
                    )
                    return render_template(
                        "student_form.html",
                        active_page="students",
                        student=student,
                        available_rooms=available_rooms,
                        form_data=request.form,
                    )

                conn.execute(
                    """
                    UPDATE students
                    SET roll_number = ?, name = ?, email = ?, phone = ?, course = ?, room_id = ?
                    WHERE id = ?
                    """,
                    (
                        cleaned["roll_number"],
                        cleaned["name"],
                        cleaned["email"],
                        cleaned["phone"],
                        cleaned["course"],
                        cleaned["room_id"],
                        student_id,
                    ),
                )
                conn.commit()
                flash(f"Student '{cleaned['name']}' updated successfully.", "success")
                return redirect(url_for("students"))

            available_rooms = _get_rooms_with_occupancy(
                conn, include_room_id=student["room_id"]
            )
        finally:
            conn.close()

        return render_template(
            "student_form.html",
            active_page="students",
            student=student,
            available_rooms=available_rooms,
            form_data={},
        )

    @app.route("/students/delete/<int:student_id>", methods=["POST"])
    @login_required
    def delete_student(student_id):
        conn = get_conn()
        try:
            student = conn.execute(
                "SELECT id, name FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            if not student:
                flash("Student not found.", "danger")
            else:
                conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
                conn.commit()
                flash(f"Student '{student['name']}' deleted successfully.", "success")
        finally:
            conn.close()
        return redirect(url_for("students"))

    # ------------------------------------------------------------------
    # MODULE 4: ROOM MANAGEMENT & ALLOCATION
    # ------------------------------------------------------------------
    VALID_ROOM_TYPES = ("Single", "Double", "Triple", "Dormitory")

    def _validate_room_form(conn, form, exclude_room_id=None, current_occupied=0):
        """Validate room form fields and capacity constraints."""
        room_number = form.get("room_number", "").strip()
        room_type = form.get("room_type", "").strip()
        capacity_raw = form.get("capacity", "").strip()
        fee_raw = form.get("monthly_fee", "").strip()
        description = form.get("description", "").strip()

        errors = []
        if not room_number:
            errors.append("Room number is required.")
        if room_type not in VALID_ROOM_TYPES:
            errors.append("Please select a valid room type.")

        capacity = None
        try:
            capacity = int(capacity_raw)
            if capacity < 1:
                errors.append("Bed capacity must be at least 1.")
            elif capacity < current_occupied:
                errors.append(
                    f"Capacity cannot be less than current occupied beds ({current_occupied})."
                )
        except ValueError:
            errors.append("Bed capacity must be a whole number.")

        monthly_fee = None
        try:
            monthly_fee = float(fee_raw)
            if monthly_fee < 0:
                errors.append("Monthly fee cannot be negative.")
        except ValueError:
            errors.append("Monthly fee must be a valid number.")

        if room_number:
            if exclude_room_id is not None:
                dup = conn.execute(
                    "SELECT id FROM rooms WHERE room_number = ? AND id != ?",
                    (room_number, exclude_room_id),
                ).fetchone()
            else:
                dup = conn.execute(
                    "SELECT id FROM rooms WHERE room_number = ?", (room_number,)
                ).fetchone()
            if dup:
                errors.append(f"Room '{room_number}' already exists.")

        cleaned = {
            "room_number": room_number,
            "room_type": room_type,
            "capacity": capacity,
            "monthly_fee": monthly_fee,
            "description": description,
        }
        return cleaned, errors

    @app.route("/rooms")
    @login_required
    def rooms():
        conn = get_conn()
        try:
            room_list = _get_rooms_with_occupancy(conn, only_available=False)
        finally:
            conn.close()
        return render_template("rooms.html", active_page="rooms", rooms=room_list)

    @app.route("/rooms/add", methods=["GET", "POST"])
    @login_required
    def add_room():
        if request.method == "POST":
            conn = get_conn()
            try:
                cleaned, errors = _validate_room_form(conn, request.form)
                if errors:
                    for err in errors:
                        flash(err, "danger")
                    return render_template(
                        "room_form.html",
                        active_page="rooms",
                        room=None,
                        form_data=request.form,
                    )

                conn.execute(
                    """
                    INSERT INTO rooms (room_number, room_type, capacity, monthly_fee, description)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        cleaned["room_number"],
                        cleaned["room_type"],
                        cleaned["capacity"],
                        cleaned["monthly_fee"],
                        cleaned["description"],
                    ),
                )
                conn.commit()
                flash(f"Room {cleaned['room_number']} added successfully.", "success")
                return redirect(url_for("rooms"))
            finally:
                conn.close()

        return render_template("room_form.html", active_page="rooms", room=None, form_data={})

    @app.route("/rooms/edit/<int:room_id>", methods=["GET", "POST"])
    @login_required
    def edit_room(room_id):
        conn = get_conn()
        try:
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if not room:
                flash("Room not found.", "danger")
                return redirect(url_for("rooms"))

            current_occupied = conn.execute(
                "SELECT COUNT(*) AS c FROM students WHERE room_id = ?", (room_id,)
            ).fetchone()["c"]

            if request.method == "POST":
                cleaned, errors = _validate_room_form(
                    conn,
                    request.form,
                    exclude_room_id=room_id,
                    current_occupied=current_occupied,
                )
                if errors:
                    for err in errors:
                        flash(err, "danger")
                    return render_template(
                        "room_form.html",
                        active_page="rooms",
                        room=room,
                        form_data=request.form,
                    )

                conn.execute(
                    """
                    UPDATE rooms
                    SET room_number = ?, room_type = ?, capacity = ?, monthly_fee = ?, description = ?
                    WHERE id = ?
                    """,
                    (
                        cleaned["room_number"],
                        cleaned["room_type"],
                        cleaned["capacity"],
                        cleaned["monthly_fee"],
                        cleaned["description"],
                        room_id,
                    ),
                )
                conn.commit()
                flash(f"Room {cleaned['room_number']} updated successfully.", "success")
                return redirect(url_for("rooms"))
        finally:
            conn.close()

        return render_template("room_form.html", active_page="rooms", room=room, form_data={})

    @app.route("/rooms/delete/<int:room_id>", methods=["POST"])
    @login_required
    def delete_room(room_id):
        conn = get_conn()
        try:
            room = conn.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
            if not room:
                flash("Room not found.", "danger")
            else:
                occupied = conn.execute(
                    "SELECT COUNT(*) AS c FROM students WHERE room_id = ?", (room_id,)
                ).fetchone()["c"]
                if occupied > 0:
                    flash(
                        f"Cannot delete Room {room['room_number']} because {occupied} student(s) are currently assigned to it.",
                        "danger",
                    )
                else:
                    conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
                    conn.commit()
                    flash(f"Room {room['room_number']} deleted successfully.", "success")
        finally:
            conn.close()
        return redirect(url_for("rooms"))

    @app.route("/rooms/allocate", methods=["GET", "POST"])
    @login_required
    def allocate_room():
        conn = get_conn()
        try:
            if request.method == "POST":
                student_raw = request.form.get("student_id", "").strip()
                room_raw = request.form.get("room_id", "").strip()

                if not student_raw.isdigit() or not room_raw.isdigit():
                    flash("Please select both a valid student and a valid room.", "danger")
                    return redirect(url_for("allocate_room"))

                student_id = int(student_raw)
                room_id = int(room_raw)

                student = conn.execute(
                    "SELECT * FROM students WHERE id = ?", (student_id,)
                ).fetchone()
                if not student:
                    flash("Selected student does not exist.", "danger")
                    return redirect(url_for("allocate_room"))

                ok, err = _check_room_capacity(conn, room_id, exclude_student_id=student_id)
                if not ok:
                    flash(err, "danger")
                    return redirect(url_for("allocate_room"))

                room = conn.execute(
                    "SELECT room_number FROM rooms WHERE id = ?", (room_id,)
                ).fetchone()
                conn.execute(
                    "UPDATE students SET room_id = ? WHERE id = ?", (room_id, student_id)
                )
                conn.commit()
                flash(
                    f"Allocated {student['name']} to Room {room['room_number']}.", "success"
                )
                return redirect(url_for("allocate_room"))

            room_list = _get_rooms_with_occupancy(conn, only_available=False)
            student_list = conn.execute(
                """
                SELECT s.id, s.name, s.roll_number, s.room_id, r.room_number
                FROM students s
                LEFT JOIN rooms r ON s.room_id = r.id
                ORDER BY s.name
                """
            ).fetchall()

            room_occupants = {}
            for s in student_list:
                if s["room_id"] is not None:
                    room_occupants.setdefault(s["room_id"], []).append(s)
        finally:
            conn.close()

        return render_template(
            "allocate_room.html",
            active_page="allocate",
            rooms=room_list,
            students=student_list,
            room_occupants=room_occupants,
        )

    @app.route("/rooms/vacate/<int:student_id>", methods=["POST"])
    @login_required
    def vacate_room(student_id):
        conn = get_conn()
        try:
            student = conn.execute(
                "SELECT id, name FROM students WHERE id = ?", (student_id,)
            ).fetchone()
            if not student:
                flash("Student not found.", "danger")
            else:
                conn.execute(
                    "UPDATE students SET room_id = NULL WHERE id = ?", (student_id,)
                )
                conn.commit()
                flash(f"{student['name']} has been vacated from their room.", "info")
        finally:
            conn.close()
        return redirect(url_for("allocate_room"))

    # ------------------------------------------------------------------
    # MODULE 5: FEE MANAGEMENT
    # ------------------------------------------------------------------
    VALID_PAYMENT_METHODS = ("UPI", "Cash", "Card", "Bank Transfer")

    @app.route("/fees", methods=["GET", "POST"])
    @login_required
    def fees():
        conn = get_conn()
        try:
            if request.method == "POST":
                student_raw = request.form.get("student_id", "").strip()
                amount_raw = request.form.get("amount", "").strip()
                payment_month = request.form.get("payment_month", "").strip()
                payment_date = request.form.get("payment_date", "").strip()
                payment_method = request.form.get("payment_method", "").strip()
                remarks = request.form.get("remarks", "").strip()

                errors = []
                student = None
                if not student_raw.isdigit():
                    errors.append("Please select a valid student.")
                else:
                    student = conn.execute(
                        "SELECT id, name FROM students WHERE id = ?", (int(student_raw),)
                    ).fetchone()
                    if not student:
                        errors.append("Selected student does not exist.")

                amount = None
                try:
                    amount = float(amount_raw)
                    if amount <= 0:
                        errors.append("Payment amount must be greater than zero.")
                except ValueError:
                    errors.append("Please enter a valid numeric payment amount.")

                if not payment_month:
                    errors.append("Payment month is required.")
                if not payment_date:
                    errors.append("Payment date is required.")
                if payment_method not in VALID_PAYMENT_METHODS:
                    errors.append("Please select a valid payment method.")

                if errors:
                    for err in errors:
                        flash(err, "danger")
                else:
                    conn.execute(
                        """
                        INSERT INTO fees (student_id, amount, payment_month, payment_date, payment_method, remarks)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            student["id"],
                            amount,
                            payment_month,
                            payment_date,
                            payment_method,
                            remarks,
                        ),
                    )
                    conn.commit()
                    flash(
                        f"Recorded ₹{amount:.2f} fee payment for {student['name']}.",
                        "success",
                    )
                    return redirect(url_for("fees"))

            search_query = request.args.get("q", "").strip()
            students_list = conn.execute(
                """
                SELECT s.id, s.name, s.roll_number, r.room_number, r.monthly_fee
                FROM students s
                LEFT JOIN rooms r ON s.room_id = r.id
                ORDER BY s.name
                """
            ).fetchall()

            if search_query:
                like_term = f"%{search_query}%"
                fee_records = conn.execute(
                    """
                    SELECT f.*, s.name AS student_name, s.roll_number, r.room_number
                    FROM fees f
                    JOIN students s ON f.student_id = s.id
                    LEFT JOIN rooms r ON s.room_id = r.id
                    WHERE s.name LIKE ? OR s.roll_number LIKE ? OR f.payment_month LIKE ?
                    ORDER BY f.payment_date DESC, f.id DESC
                    """,
                    (like_term, like_term, like_term),
                ).fetchall()
            else:
                fee_records = conn.execute(
                    """
                    SELECT f.*, s.name AS student_name, s.roll_number, r.room_number
                    FROM fees f
                    JOIN students s ON f.student_id = s.id
                    LEFT JOIN rooms r ON s.room_id = r.id
                    ORDER BY f.payment_date DESC, f.id DESC
                    """
                ).fetchall()

            total_shown = sum(row["amount"] for row in fee_records)
        finally:
            conn.close()

        today = date.today()
        return render_template(
            "fees.html",
            active_page="fees",
            students=students_list,
            fee_records=fee_records,
            total_shown=total_shown,
            search_query=search_query,
            default_date=today.strftime("%Y-%m-%d"),
            default_month=today.strftime("%B %Y"),
        )

    # ------------------------------------------------------------------
    # MODULE 6: COMPLAINT MANAGEMENT
    # ------------------------------------------------------------------
    VALID_COMPLAINT_CATEGORIES = (
        "Electricity",
        "Plumbing",
        "Wi-Fi",
        "Cleaning",
        "Furniture",
        "Other",
    )
    VALID_COMPLAINT_STATUSES = ("Pending", "In Progress", "Resolved")

    @app.route("/complaints", methods=["GET", "POST"])
    @login_required
    def complaints():
        conn = get_conn()
        try:
            if request.method == "POST":
                student_raw = request.form.get("student_id", "").strip()
                title = request.form.get("title", "").strip()
                category = request.form.get("category", "").strip()
                description = request.form.get("description", "").strip()

                errors = []
                student = None
                if not student_raw.isdigit():
                    errors.append("Please select a valid student.")
                else:
                    student = conn.execute(
                        "SELECT id, name FROM students WHERE id = ?", (int(student_raw),)
                    ).fetchone()
                    if not student:
                        errors.append("Selected student does not exist.")

                if not title:
                    errors.append("Complaint title is required.")
                if category not in VALID_COMPLAINT_CATEGORIES:
                    errors.append("Please select a valid complaint category.")
                if not description:
                    errors.append("Complaint description is required.")

                if errors:
                    for err in errors:
                        flash(err, "danger")
                else:
                    conn.execute(
                        """
                        INSERT INTO complaints (student_id, title, category, description, status)
                        VALUES (?, ?, ?, ?, 'Pending')
                        """,
                        (student["id"], title, category, description),
                    )
                    conn.commit()
                    flash("Complaint registered successfully.", "success")
                    return redirect(url_for("complaints"))

            status_filter = request.args.get("status", "All").strip()
            if status_filter not in ("All",) + VALID_COMPLAINT_STATUSES:
                status_filter = "All"

            students_list = conn.execute(
                """
                SELECT s.id, s.name, s.roll_number, r.room_number
                FROM students s
                LEFT JOIN rooms r ON s.room_id = r.id
                ORDER BY s.name
                """
            ).fetchall()

            base_query = """
                SELECT c.*, s.name AS student_name, s.roll_number, r.room_number
                FROM complaints c
                JOIN students s ON c.student_id = s.id
                LEFT JOIN rooms r ON s.room_id = r.id
            """
            if status_filter != "All":
                complaint_list = conn.execute(
                    base_query + " WHERE c.status = ? ORDER BY c.id DESC",
                    (status_filter,),
                ).fetchall()
            else:
                complaint_list = conn.execute(
                    base_query + " ORDER BY c.id DESC"
                ).fetchall()
        finally:
            conn.close()

        return render_template(
            "complaints.html",
            active_page="complaints",
            students=students_list,
            complaint_list=complaint_list,
            status_filter=status_filter,
        )

    @app.route("/complaints/update/<int:complaint_id>", methods=["POST"])
    @login_required
    def update_complaint_status(complaint_id):
        new_status = request.form.get("status", "").strip()
        if new_status not in VALID_COMPLAINT_STATUSES:
            flash("Invalid complaint status selected.", "danger")
            return redirect(url_for("complaints"))

        conn = get_conn()
        try:
            complaint = conn.execute(
                "SELECT id FROM complaints WHERE id = ?", (complaint_id,)
            ).fetchone()
            if not complaint:
                flash("Complaint not found.", "danger")
            else:
                conn.execute(
                    """
                    UPDATE complaints
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_status, complaint_id),
                )
                conn.commit()
                flash(f"Complaint status updated to '{new_status}'.", "success")
        finally:
            conn.close()
        return redirect(url_for("complaints"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
