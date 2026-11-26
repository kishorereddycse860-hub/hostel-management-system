# Hostel Management System (College Mini Project)

A complete, beginner-friendly **Hostel Management System** web application built with **Python, Flask, SQLite, HTML, CSS, Bootstrap 5, and JavaScript**. Designed with a clean, responsive admin dashboard and well-structured code that is easy to explain during a college viva.

---

## Features & Modules

1. **Admin Authentication (`/login`, `/logout`)**
   - Secure password hashing using `werkzeug.security` (`generate_password_hash` and `check_password_hash`).
   - Session-based authentication with a custom `@login_required` decorator protecting all admin routes.
2. **Live Dashboard (`/`)**
   - Real-time SQLite queries displaying **Total Students**, **Total Rooms**, **Occupied Beds**, **Available Beds**, **Pending Complaints**, and **Total Fees Collected**.
   - Shows recent fee payments and recent complaints at a glance.
3. **Student Management (`/students`)**
   - Add, View, Edit, Delete, and Search students by name, roll number, phone, email, or course.
   - Server-side validation for unique roll numbers, email format, and phone numbers.
4. **Room Management & Allocation (`/rooms`, `/rooms/allocate`)**
   - Add, View, Edit, and Delete rooms with room types (`Single`, `Double`, `Triple`, `Dormitory`), capacity, and monthly fee.
   - Allocate and vacate students with strict **bed-capacity validation** (prevents over-allocating full rooms, shrinking capacity below current occupants, or deleting occupied rooms).
5. **Fee Management (`/fees`)**
   - Record fee payments with student selection, auto-suggested room rent via JavaScript, payment month, date, method, and remarks.
   - View and search payment history with live total calculation.
6. **Complaint Management (`/complaints`)**
   - Register student complaints by category (`Electricity`, `Plumbing`, `Wi-Fi`, `Cleaning`, `Furniture`, `Other`).
   - Filter complaints by status and update status between `Pending`, `In Progress`, and `Resolved`.

---

## Project Structure

```text
Hostel/
├── app.py                  # Flask application, auth decorator, and all module routes
├── database.py             # SQLite connection, table schema (with Foreign Keys), and sample data
├── requirements.txt        # Python dependencies (Flask, pytest)
├── README.md               # Setup, usage, and viva explanation guide
├── hostel.db               # SQLite database (auto-created on first run)
├── static/
│   ├── css/
│   │   └── style.css       # Custom dashboard theme, sidebar, and responsive layout
│   └── js/
│       └── main.js         # Sidebar toggle, delete confirmations, form validation, fee auto-fill
├── templates/
│   ├── base.html           # Shared admin layout with sidebar navigation and flash alerts
│   ├── login.html          # Admin login page
│   ├── dashboard.html      # Dashboard summary cards and recent activity tables
│   ├── students.html       # Student directory and search
│   ├── student_form.html   # Add / Edit student form
│   ├── rooms.html          # Room inventory and occupancy status
│   ├── room_form.html      # Add / Edit room form
│   ├── allocate_room.html  # Student-to-room allocation and vacate controls
│   ├── fees.html           # Record payments and view payment history
│   └── complaints.html     # Register and manage student complaints
└── tests/
    └── test_app.py         # Automated pytest suite for all 6 modules
```

---

## Database Schema & Relationships

`PRAGMA foreign_keys = ON` is enabled on every SQLite connection in `database.py`:

- **`admins`**: `id`, `username` (UNIQUE), `password_hash`, `full_name`, `created_at`
- **`rooms`**: `id`, `room_number` (UNIQUE), `room_type`, `capacity`, `monthly_fee`, `description`, `created_at`
- **`students`**: `id`, `roll_number` (UNIQUE), `name`, `email`, `phone`, `course`, `room_id` (`FOREIGN KEY -> rooms(id) ON DELETE SET NULL`), `created_at`
- **`fees`**: `id`, `student_id` (`FOREIGN KEY -> students(id) ON DELETE CASCADE`), `amount`, `payment_month`, `payment_date`, `payment_method`, `remarks`, `created_at`
- **`complaints`**: `id`, `student_id` (`FOREIGN KEY -> students(id) ON DELETE CASCADE`), `title`, `category`, `description`, `status`, `created_at`, `updated_at`

---

## Setup & Running Instructions

### 1. Activate Virtual Environment (or create one)

On Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

*(If you already have the `.venv` folder in this workspace, just activate it or run `.\.venv\Scripts\python.exe` directly.)*

### 2. Run the Application

```powershell
.\.venv\Scripts\python.exe app.py
```

Open your browser and visit: **http://127.0.0.1:5000**

### 3. Default Demo Login Credentials

- **Username:** `admin`
- **Password:** `admin123`

*(Sample rooms, students, fee payments, and complaints are seeded automatically the first time `hostel.db` is created.)*

### 4. Run Automated Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## Quick Viva Notes

- **Why use `werkzeug.security` for passwords?** Never store plain-text passwords in the database. `generate_password_hash()` hashes passwords with a salt, and `check_password_hash()` verifies them safely during login.
- **How are admin pages protected?** The `@login_required` decorator in `app.py` checks whether `admin_id` exists in Flask's `session` before running any protected route; otherwise it redirects to `/login`.
- **How is room over-allocation prevented?** Before assigning a student to a room, `_check_room_capacity()` counts existing students in that room (`SELECT COUNT(*) FROM students WHERE room_id = ?`) and blocks the assignment if `occupied >= capacity`.
