#!/usr/bin/env python3
"""Local Careflow hospital management app server (Python standard library only)."""

from datetime import date, datetime, timedelta
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import csv
import hashlib
import io
import json
import secrets
import re
import sqlite3
import time
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "hospital.db"
HOST = "127.0.0.1"
PORT = 8000
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}", "127.0.0.1", "localhost"}
DEPARTMENTS = {
    "Cardiology", "Dermatology", "Neurology", "Orthopedics", "Pediatrics",
    "General Medicine", "Ophthalmology", "Oncology", "Other",
}
ROLES = {"administrator", "doctor", "receptionist", "billing"}
MODULE_ROLES = {
    "dashboard": {"administrator", "doctor", "receptionist", "billing"},
    "patients": {"administrator", "doctor", "receptionist", "billing"},
    "doctors": {"administrator", "doctor", "receptionist"},
    "appointments": {"administrator", "doctor", "receptionist"},
    "departments": {"administrator", "doctor", "receptionist", "billing"},
    "records": {"administrator", "doctor"},
    "admissions": {"administrator", "doctor", "receptionist"},
    "beds": {"administrator", "receptionist"},
    "billing": {"administrator", "billing"},
    "pharmacy": {"administrator", "doctor", "receptionist"},
    "laboratory": {"administrator", "doctor", "receptionist"},
    "staff": {"administrator"},
    "reports": {"administrator", "billing"},
    "notifications": {"administrator", "doctor", "receptionist", "billing"},
    "settings": {"administrator", "doctor", "receptionist", "billing"},
}
MODULE_WRITE_ROLES = {
    "patients": {"administrator","receptionist"},
    "doctors": {"administrator","receptionist"},
    "appointments": {"administrator","doctor","receptionist"},
    "departments": {"administrator"},
    "records": {"administrator","doctor"},
    "admissions": {"administrator","doctor","receptionist"},
    "beds": {"administrator","receptionist"},
    "billing": {"administrator","billing"},
    "pharmacy": {"administrator","receptionist"},
    "laboratory": {"administrator","doctor","receptionist"},
    "staff": {"administrator"},
    "notifications": {"administrator","doctor","receptionist","billing"},
    "settings": {"administrator","doctor","receptionist","billing"},
}
LOGIN_ATTEMPTS = {}


@contextmanager
def connect():
    connection = sqlite3.connect(DATABASE, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_code TEXT UNIQUE,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                phone TEXT NOT NULL,
                date_of_birth TEXT,
                gender TEXT,
                blood_group TEXT,
                address TEXT,
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                department TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                phone TEXT NOT NULL,
                experience INTEGER NOT NULL DEFAULT 0,
                bio TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                department TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK(status IN ('scheduled', 'completed', 'cancelled')),
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS appointment_date_idx ON appointments(date, time);
            CREATE INDEX IF NOT EXISTS patient_name_idx ON patients(name);
            CREATE INDEX IF NOT EXISTS doctor_name_idx ON doctors(name);
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('administrator','doctor','receptionist','billing')),
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                head TEXT NOT NULL DEFAULT '',
                extension TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS medical_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                doctor_id INTEGER REFERENCES doctors(id),
                visit_date TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                treatment TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS beds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bed_number TEXT NOT NULL COLLATE NOCASE UNIQUE,
                ward TEXT NOT NULL,
                bed_type TEXT NOT NULL DEFAULT 'General',
                status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available','occupied','maintenance')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                doctor_id INTEGER REFERENCES doctors(id),
                bed_id INTEGER REFERENCES beds(id),
                admitted_on TEXT NOT NULL,
                discharged_on TEXT,
                diagnosis TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'admitted' CHECK(status IN ('admitted','discharged')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                appointment_id INTEGER REFERENCES appointments(id),
                description TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
                currency TEXT NOT NULL DEFAULT 'USD',
                status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('draft','issued','paid','void')),
                issued_on TEXT NOT NULL,
                due_on TEXT NOT NULL,
                paid_on TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT NOT NULL COLLATE NOCASE UNIQUE,
                quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                reorder_level INTEGER NOT NULL DEFAULT 10 CHECK(reorder_level >= 0),
                unit TEXT NOT NULL DEFAULT 'units',
                expires_on TEXT,
                unit_price_cents INTEGER NOT NULL DEFAULT 0 CHECK(unit_price_cents >= 0),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lab_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                doctor_id INTEGER REFERENCES doctors(id),
                test_name TEXT NOT NULL,
                ordered_on TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ordered' CHECK(status IN ('ordered','in_progress','completed','cancelled')),
                result TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                message TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'system',
                created_at TEXT NOT NULL,
                read_at TEXT
            );
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                entity_id INTEGER,
                created_at TEXT NOT NULL
            );
        """)
        # Additive migrations preserve the original patient, doctor and appointment rows.
        appointment_columns = {row["name"] for row in db.execute("PRAGMA table_info(appointments)")}
        if "duration_minutes" not in appointment_columns:
            db.execute("ALTER TABLE appointments ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 30")
        appointment_sql=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='appointments'").fetchone()["sql"]
        if re.search(r"UNIQUE\s*\(\s*doctor_id\s*,\s*date\s*,\s*time\s*\)",appointment_sql,re.I):
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute("BEGIN IMMEDIATE")
            db.execute("DROP TABLE IF EXISTS appointments_migration")
            db.execute("""CREATE TABLE appointments_migration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id),
                doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                department TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK(status IN ('scheduled', 'completed', 'cancelled')),
                created_at TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 30
            )""")
            db.execute("""INSERT INTO appointments_migration
                (id,patient_id,doctor_id,date,time,department,reason,status,created_at,duration_minutes)
                SELECT id,patient_id,doctor_id,date,time,department,reason,status,created_at,duration_minutes
                FROM appointments""")
            db.execute("DROP TABLE appointments")
            db.execute("ALTER TABLE appointments_migration RENAME TO appointments")
            db.execute("CREATE INDEX IF NOT EXISTS appointment_date_idx ON appointments(date,time)")
            db.execute("PRAGMA foreign_keys=ON")
        doctor_columns = {row["name"] for row in db.execute("PRAGMA table_info(doctors)")}
        if "availability" not in doctor_columns:
            db.execute("ALTER TABLE doctors ADD COLUMN availability TEXT NOT NULL DEFAULT 'Weekdays, 9 AM – 5 PM'")
        invoice_columns={row["name"] for row in db.execute("PRAGMA table_info(invoices)")}
        if "paid_on" not in invoice_columns:
            db.execute("ALTER TABLE invoices ADD COLUMN paid_on TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS session_expiry_idx ON sessions(expires_at)")
        db.execute("CREATE INDEX IF NOT EXISTS records_patient_idx ON medical_records(patient_id, visit_date)")
        db.execute("CREATE INDEX IF NOT EXISTS admissions_status_idx ON admissions(status, admitted_on)")
        db.execute("CREATE INDEX IF NOT EXISTS invoices_status_idx ON invoices(status, due_on)")
        db.execute("CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications(user_id, created_at)")
        db.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('data_mode', 'demo')")
        for row in db.execute("SELECT DISTINCT department FROM doctors WHERE department != ''"):
            db.execute("INSERT OR IGNORE INTO departments (name, created_at) VALUES (?, ?)", (row["department"], date.today().isoformat()))
        if db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]:
            return
        today = date.today()
        patients = [
            ("Olivia Bennett", "olivia.bennett@example.test", "+1 415 555 0142", 34, "Female", "O+", "124 Pine Street"),
            ("Ethan Parker", "ethan.parker@example.test", "+1 415 555 0198", 52, "Male", "A+", "88 Market Avenue"),
            ("Sofia Ramirez", "sofia.ramirez@example.test", "+1 415 555 0126", 28, "Female", "B+", "17 Lakeview Road"),
            ("Noah Williams", "noah.williams@example.test", "+1 415 555 0173", 46, "Male", "AB+", "302 Cedar Lane"),
            ("Amara Johnson", "amara.johnson@example.test", "+1 415 555 0109", 39, "Female", "A-", "56 Hillcrest Drive"),
            ("Lucas Chen", "lucas.chen@example.test", "+1 415 555 0164", 61, "Male", "O-", "9 Willow Court"),
            ("Isabella Foster", "isabella.foster@example.test", "+1 415 555 0181", 23, "Female", "B-", "411 Spruce Way"),
        ]
        for index, (name, email, phone, age, gender, blood, address) in enumerate(patients, 1):
            birthday = today.replace(year=today.year - age).isoformat()
            db.execute(
                """INSERT INTO patients (patient_code, name, email, phone, date_of_birth,
                   gender, blood_group, address, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"PT-{1000 + index}", name, email, phone, birthday, gender, blood, address,
                 (today - timedelta(days=30 - index)).isoformat()),
            )
        doctors = [
            ("Dr. Maya Patel", "Cardiologist", "Cardiology", "maya.patel@example.test", "+1 415 555 0201", 12, "Heart health, prevention, and compassionate cardiac care."),
            ("Dr. James Wilson", "Dermatologist", "Dermatology", "james.wilson@example.test", "+1 415 555 0202", 9, "Personalized skin health and evidence-based treatment."),
            ("Dr. Elena Garcia", "Neurologist", "Neurology", "elena.garcia@example.test", "+1 415 555 0203", 15, "Focused on helping patients feel their best, every day."),
            ("Dr. Ryan Cooper", "Orthopedic surgeon", "Orthopedics", "ryan.cooper@example.test", "+1 415 555 0204", 11, "Helping patients move comfortably and confidently."),
            ("Dr. Aisha Khan", "Pediatrician", "Pediatrics", "aisha.khan@example.test", "+1 415 555 0205", 8, "Warm, family-centered care for growing patients."),
        ]
        for doctor in doctors:
            db.execute(
                """INSERT INTO doctors (name, specialty, department, email, phone, experience, bio)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                doctor,
            )
        appointment_seed = [
            (1, 1, today.isoformat(), "09:00", "Cardiology", "Annual heart check", "scheduled"),
            (2, 2, today.isoformat(), "10:30", "Dermatology", "Skin consultation", "scheduled"),
            (3, 5, today.isoformat(), "13:00", "Pediatrics", "Routine checkup", "scheduled"),
            (4, 3, (today - timedelta(days=1)).isoformat(), "11:00", "Neurology", "Follow-up visit", "completed"),
            (5, 4, (today - timedelta(days=2)).isoformat(), "14:30", "Orthopedics", "Joint pain consultation", "completed"),
            (6, 1, (today + timedelta(days=1)).isoformat(), "09:30", "Cardiology", "Follow-up visit", "scheduled"),
            (7, 3, (today + timedelta(days=2)).isoformat(), "15:00", "Neurology", "Headache consultation", "scheduled"),
            (2, 1, today.isoformat(), "15:30", "Cardiology", "Blood pressure review", "scheduled"),
        ]
        for item in appointment_seed:
            db.execute(
                """INSERT INTO appointments (patient_id, doctor_id, date, time, department, reason, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (*item, datetime.now().isoformat(timespec="seconds")),
            )


def as_dict(row):
    return dict(row) if row is not None else None


def clean_text(data, key, label, required=True, max_length=250):
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{label} is required.")
    if len(value) > max_length:
        raise ValueError(f"{label} must be {max_length} characters or fewer.")
    return value


def validate_email(email):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address.")


def validate_phone(phone):
    if not re.fullmatch(r"[+()\d.\-\s]{7,25}", phone):
        raise ValueError("Enter a valid phone number.")


def validate_date(value, label, allow_past=True):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Enter a valid {label.lower()}.")
    if not isinstance(value, str) or parsed.isoformat() != value:
        raise ValueError(f"Enter a valid {label.lower()}.")
    if allow_past is False and parsed < date.today():
        raise ValueError("Appointment date cannot be in the past.")
    return parsed.isoformat()


def validate_person(data):
    name = clean_text(data, "name", "Name", max_length=100)
    email = clean_text(data, "email", "Email", max_length=254)
    validate_email(email)
    phone = clean_text(data, "phone", "Phone", max_length=25)
    validate_phone(phone)
    return name, email.lower(), phone


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


class CareflowHandler(BaseHTTPRequestHandler):
    server_version = "Careflow/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def send_json(self, payload, status=200):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for name, value in getattr(self, "response_headers", []):
            self.send_header(name, value)
        self.response_headers = []
        self.end_headers()
        self.wfile.write(content)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def set_cookie(self, token, max_age):
        value = f"careflow_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
        if self.headers.get("X-Forwarded-Proto") == "https":
            value += "; Secure"
        self.response_headers = [("Set-Cookie", value)]

    def clear_cookie(self):
        self.response_headers = [("Set-Cookie", "careflow_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")]

    def cookie_token(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie["careflow_session"].value if "careflow_session" in cookie else ""
        except CookieError:
            return ""

    def current_user(self):
        token = self.cookie_token()
        if not token:
            return None
        token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
        with connect() as db:
            row = db.execute(
                """SELECT u.id, u.name, u.email, u.role FROM sessions s
                   JOIN users u ON u.id=s.user_id
                   WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
                (token_hash, datetime.utcnow().isoformat(timespec="seconds")),
            ).fetchone()
            return as_dict(row)

    def require_user(self):
        user = self.current_user()
        if not user:
            raise APIError("Please sign in to continue.", 401)
        return user

    @staticmethod
    def require_role(user, module):
        if user["role"] not in MODULE_ROLES.get(module, {"administrator"}):
            raise APIError("Your account does not have permission to access this module.", 403)

    def require_same_origin(self):
        host=self.headers.get("Host", "")
        server_port=getattr(self.server,"server_port",PORT)
        allowed=ALLOWED_HOSTS|{f"127.0.0.1:{server_port}",f"localhost:{server_port}"}
        if host not in allowed:
            raise APIError("This host is not permitted.", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise APIError("Cross-origin requests are not allowed.", 403)
        origin = self.headers.get("Origin")
        if origin:
            expected = f"http://{self.headers.get('Host', '')}"
            if origin.rstrip("/") not in {expected.rstrip("/"),f"https://{self.headers.get('Host','')}"}:
                raise APIError("Cross-origin requests are not allowed.", 403)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError("Invalid request body.")
        if length > 32_000:
            raise APIError("Request body is too large.", 413)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise APIError("Request body must be valid JSON.")
        if not isinstance(data, dict):
            raise APIError("Request body must be a JSON object.")
        return data

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            try:
                if parsed.path == "/api/health":
                    self.send_json({"status": "ok"})
                    return
                if parsed.path in {"/api/auth/status", "/api/auth/me"}:
                    self.handle_auth_get(parsed.path)
                    return
                user = self.require_user()
                if parsed.path.startswith("/api/modules/"):
                    self.handle_module_get(parsed.path, parse_qs(parsed.query), user)
                    return
                if parsed.path == "/api/reports/export.csv":
                    self.handle_report_export(parse_qs(parsed.query), user)
                    return
                module = ("dashboard" if parsed.path == "/api/dashboard" else
                          "patients" if parsed.path == "/api/patients" else
                          "doctors" if parsed.path == "/api/doctors" else
                          "appointments" if parsed.path == "/api/appointments" else "settings")
                self.require_role(user, module)
                patient_match = re.fullmatch(r"/api/patients/(\d+)", parsed.path)
                if patient_match:
                    if user["role"]=="billing":
                        raise APIError("Patient profiles are not available to the billing role.",403)
                    self.handle_patient_detail(int(patient_match.group(1)))
                    return
                self.handle_get(parsed.path, parse_qs(parsed.query),user)
            except APIError as error:
                self.send_json({"error": error.message}, error.status)
            except sqlite3.Error:
                self.send_json({"error": "The database request could not be completed."}, 500)
            return
        self.serve_static(parsed.path)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_error(405, "Method not allowed")
            return
        self.serve_static(parsed.path, head_only=True)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        self.dispatch_write("POST")

    def do_PUT(self):
        self.dispatch_write("PUT")

    def do_PATCH(self):
        self.dispatch_write("PATCH")

    def do_DELETE(self):
        self.dispatch_write("DELETE")

    def dispatch_write(self, method):
        try:
            if not self.path.startswith("/api/"):
                raise APIError("Not found.", 404)
            path = urlparse(self.path).path
            data = self.read_json()
            self.require_same_origin()
            if path in {"/api/auth/setup", "/api/auth/login", "/api/auth/logout"}:
                self.handle_auth_write(path, method, data)
                return
            user = self.require_user()
            if path.startswith("/api/modules/"):
                self.handle_module_write(path, method, data, user)
                return
            module = ("patients" if path.startswith("/api/patients") else
                      "doctors" if path.startswith("/api/doctors") else
                      "appointments" if path.startswith("/api/appointments") else "settings")
            self.require_role(user, module)
            if user["role"] not in MODULE_WRITE_ROLES.get(module,{"administrator"}):
                raise APIError("Your account is not permitted to change these records.",403)
            self.handle_write(path, method, data, user)
        except APIError as error:
            self.send_json({"error": error.message}, error.status)
        except ValueError as error:
            self.send_json({"error": str(error)}, 400)
        except sqlite3.IntegrityError as error:
            message = str(error)
            if "UNIQUE constraint failed: patients.email" in message or "UNIQUE constraint failed: doctors.email" in message:
                self.send_json({"error": "That email address is already in use."}, 409)
            elif "UNIQUE constraint failed: appointments.doctor_id" in message:
                self.send_json({"error": "That doctor already has an appointment at this time."}, 409)
            elif "FOREIGN KEY constraint failed" in message:
                self.send_json({"error": "Choose an active patient and doctor."}, 400)
            else:
                self.send_json({"error": "The record conflicts with existing data."}, 409)
        except sqlite3.Error:
            self.send_json({"error": "The database request could not be completed."}, 500)

    @staticmethod
    def hash_password(password, salt=None):
        salt_bytes = secrets.token_bytes(16) if salt is None else bytes.fromhex(salt)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt_bytes, n=2**14, r=8, p=1, dklen=32)
        return salt_bytes.hex(), digest.hex()

    @staticmethod
    def validate_password(data):
        password = data.get("password")
        if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
            raise APIError("Use a password between 12 and 256 characters.")
        return password

    @staticmethod
    def public_user(row):
        if not row:
            return None
        return {key: row[key] for key in ("id", "name", "email", "role")}

    def handle_auth_get(self, path):
        with connect() as db:
            user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if path == "/api/auth/status":
            user = self.current_user()
            self.send_json({"setup_required": user_count == 0, "authenticated": bool(user), "user": user})
        else:
            self.send_json({"user": self.current_user()})

    def handle_auth_write(self, path, method, data):
        if path == "/api/auth/logout":
            if method != "POST":
                raise APIError("Method not allowed.", 405)
            token = self.cookie_token()
            if token:
                token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
                with connect() as db:
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
            self.clear_cookie()
            self.send_json({"message": "Signed out."})
            return
        if method != "POST":
            raise APIError("Method not allowed.", 405)

        if path == "/api/auth/setup":
            name, email = clean_text(data, "name", "Name", max_length=100), clean_text(data, "email", "Email", max_length=254).lower()
            validate_email(email)
            password = self.validate_password(data)
            salt, digest = self.hash_password(password)
            try:
                with connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                        raise APIError("Initial administrator setup has already been completed.", 409)
                    cursor = db.execute(
                        "INSERT INTO users (name,email,role,password_salt,password_hash,created_at) VALUES (?,?,'administrator',?,?,?)",
                        (name, email, salt, digest, datetime.utcnow().isoformat(timespec="seconds")),
                    )
                    self.create_session(db, cursor.lastrowid)
            except sqlite3.IntegrityError:
                raise APIError("That email address is already registered.", 409)
            self.set_cookie(self.new_session_token, 60 * 60 * 12)
            self.send_json({"user": {"id": cursor.lastrowid, "name": name, "email": email, "role": "administrator"}}, 201)
            return

        if path == "/api/auth/login":
            email = clean_text(data, "email", "Email", max_length=254).lower()
            password = data.get("password")
            if not isinstance(password, str) or len(password) > 256:
                raise APIError("Email or password is incorrect.", 401)
            now = time.monotonic()
            client = self.client_address[0]
            failures, reset_at = LOGIN_ATTEMPTS.get(client, (0, now + 900))
            if now > reset_at:
                failures, reset_at = 0, now + 900
            if failures >= 8:
                raise APIError("Too many sign-in attempts. Try again in 15 minutes.", 429)
            with connect() as db:
                row = db.execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
                candidate_salt = row["password_salt"] if row else "00" * 16
                candidate = self.hash_password(password, candidate_salt)[1]
                if not row or not secrets.compare_digest(candidate, row["password_hash"]):
                    LOGIN_ATTEMPTS[client] = (failures + 1, reset_at)
                    raise APIError("Email or password is incorrect.", 401)
                LOGIN_ATTEMPTS.pop(client, None)
                db.execute("DELETE FROM sessions WHERE user_id=? OR expires_at<=?", (row["id"], datetime.utcnow().isoformat(timespec="seconds")))
                self.create_session(db, row["id"])
                public = self.public_user(row)
            self.set_cookie(self.new_session_token, 60 * 60 * 12)
            self.send_json({"user": public})

    def create_session(self, db, user_id):
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        db.execute(
            "INSERT INTO sessions (token_hash,user_id,expires_at,created_at) VALUES (?,?,?,?)",
            (hashlib.sha256(token.encode("ascii")).hexdigest(), user_id,
             (now + timedelta(hours=12)).isoformat(timespec="seconds"), now.isoformat(timespec="seconds")),
        )
        self.new_session_token = token

    def handle_module_get(self, path, query, user):
        parts = path.split("/")
        if len(parts) != 4:
            raise APIError("Not found.", 404)
        module = parts[3]
        if module not in MODULE_ROLES:
            raise APIError("Not found.", 404)
        self.require_role(user, module)
        search = query.get("q", [""])[0].strip()[:100]
        with connect() as db:
            if module == "departments":
                rows = db.execute("SELECT * FROM departments WHERE active=1 AND (name LIKE ? OR head LIKE ? OR description LIKE ?) ORDER BY name", (f"%{search}%",)*3).fetchall()
                result = [as_dict(row) for row in rows]
            elif module == "reports":
                start = validate_date(query.get("from", [date.today().replace(day=1).isoformat()])[0], "Start date")
                end = validate_date(query.get("to", [date.today().isoformat()])[0], "End date")
                if start > end:
                    raise APIError("Start date must be on or before end date.")
                department = query.get("department", ["all"])[0]
                args = [start, end]
                dept_sql = ""
                if department != "all":
                    dept_sql = " AND department=?"
                    args.append(department)
                appointments = db.execute(
                    """SELECT date,department,status,COUNT(*) AS count FROM appointments
                       WHERE date BETWEEN ? AND ?""" + dept_sql +
                    " GROUP BY date,department,status ORDER BY date,department", args).fetchall()
                revenue = db.execute(
                    """SELECT currency,status,COALESCE(SUM(amount_cents),0) AS total
                       FROM invoices WHERE COALESCE(paid_on,issued_on) BETWEEN ? AND ? GROUP BY currency,status""",
                    (start, end)).fetchall()
                result = {"from": start, "to": end,
                          "appointments": [as_dict(row) for row in appointments],
                          "revenue": [as_dict(row) for row in revenue],
                          "occupancy": db.execute("SELECT COUNT(*) AS beds, SUM(status='occupied') AS occupied FROM beds").fetchone()["occupied"] or 0}
            elif module == "records":
                sql = """SELECT r.id,r.patient_id,p.patient_code,p.name AS patient_name,r.doctor_id,
                         COALESCE(d.name,'Unassigned') AS doctor_name,r.visit_date,r.diagnosis,r.treatment,r.notes
                         FROM medical_records r JOIN patients p ON p.id=r.patient_id
                         LEFT JOIN doctors d ON d.id=r.doctor_id WHERE 1=1"""
                args = []
                if query.get("patient_id", [""])[0].isdigit():
                    sql += " AND r.patient_id=?"; args.append(int(query["patient_id"][0]))
                if search:
                    sql += " AND (p.name LIKE ? OR r.diagnosis LIKE ? OR r.treatment LIKE ?)"; args.extend([f"%{search}%"]*3)
                result = [as_dict(row) for row in db.execute(sql + " ORDER BY r.visit_date DESC,r.id DESC LIMIT 500", args).fetchall()]
            elif module == "admissions":
                result = [as_dict(row) for row in db.execute(
                    """SELECT a.id,a.patient_id,p.patient_code,p.name AS patient_name,a.doctor_id,
                       COALESCE(d.name,'Unassigned') AS doctor_name,a.bed_id,b.bed_number,b.ward,
                       a.admitted_on,a.discharged_on,a.diagnosis,a.status FROM admissions a
                       JOIN patients p ON p.id=a.patient_id LEFT JOIN doctors d ON d.id=a.doctor_id
                       LEFT JOIN beds b ON b.id=a.bed_id WHERE p.name LIKE ? OR a.diagnosis LIKE ?
                       ORDER BY a.admitted_on DESC LIMIT 500""", (f"%{search}%",)*2).fetchall()]
            elif module == "beds":
                result = [as_dict(row) for row in db.execute(
                    """SELECT b.*,p.name AS patient_name FROM beds b
                       LEFT JOIN admissions a ON a.bed_id=b.id AND a.status='admitted'
                       LEFT JOIN patients p ON p.id=a.patient_id WHERE b.bed_number LIKE ? OR b.ward LIKE ?
                       ORDER BY b.ward,b.bed_number LIMIT 500""", (f"%{search}%",)*2).fetchall()]
            elif module == "billing":
                result = [as_dict(row) for row in db.execute(
                    """SELECT i.id,i.invoice_number,i.patient_id,p.name AS patient_name,i.description,
                       i.amount_cents,i.currency,i.status,i.issued_on,i.due_on
                       FROM invoices i JOIN patients p ON p.id=i.patient_id
                       WHERE i.invoice_number LIKE ? OR p.name LIKE ? OR i.description LIKE ?
                       ORDER BY i.issued_on DESC LIMIT 500""", (f"%{search}%",)*3).fetchall()]
            elif module == "pharmacy":
                result = [as_dict(row) for row in db.execute(
                    """SELECT *,CASE WHEN quantity<=reorder_level THEN 1 ELSE 0 END AS low_stock
                       FROM medicines WHERE name LIKE ? OR sku LIKE ? ORDER BY name LIMIT 500""", (f"%{search}%",)*2).fetchall()]
            elif module == "laboratory":
                result = [as_dict(row) for row in db.execute(
                    """SELECT l.id,l.patient_id,p.name AS patient_name,l.doctor_id,
                       COALESCE(d.name,'Unassigned') AS doctor_name,l.test_name,l.ordered_on,l.status,l.result,l.notes
                       FROM lab_orders l JOIN patients p ON p.id=l.patient_id
                       LEFT JOIN doctors d ON d.id=l.doctor_id WHERE p.name LIKE ? OR l.test_name LIKE ?
                       ORDER BY l.ordered_on DESC LIMIT 500""", (f"%{search}%",)*2).fetchall()]
            elif module == "staff":
                result = [self.public_user(row) | {"active": row["active"], "created_at": row["created_at"]} for row in db.execute(
                    "SELECT id,name,email,role,active,created_at FROM users WHERE name LIKE ? OR email LIKE ? ORDER BY name LIMIT 500",
                    (f"%{search}%",)*2).fetchall()]
            elif module == "notifications":
                result = [as_dict(row) for row in db.execute(
                    "SELECT id,message,category,created_at,read_at FROM notifications WHERE user_id IS NULL OR user_id=? ORDER BY created_at DESC LIMIT 100",
                    (user["id"],)).fetchall()]
            elif module == "settings":
                result = {"user": self.public_user(db.execute("SELECT id,name,email,role FROM users WHERE id=?", (user["id"],)).fetchone())}
            else:
                raise APIError("Not found.", 404)
        if module in {"settings","reports"}:
            self.send_json(result)
        else:
            self.send_json({"items": result, "count": len(result)})

    def handle_module_write(self, path, method, data, user):
        match = re.fullmatch(r"/api/modules/([a-z]+)(?:/(\d+))?", path)
        if not match:
            raise APIError("Not found.", 404)
        module, raw_id = match.groups()
        if module not in MODULE_ROLES:
            raise APIError("Not found.", 404)
        self.require_role(user, module)
        if user["role"] not in MODULE_WRITE_ROLES.get(module,{"administrator"}):
            raise APIError("Your account is not permitted to change this module.",403)
        record_id = int(raw_id) if raw_id else None
        if module == "settings":
            self.handle_profile_write(method, data, user)
            return
        if module == "notifications":
            if method not in {"PATCH", "POST"} or not record_id:
                raise APIError("Invalid notification action.", 400)
            with connect() as db:
                cursor = db.execute("UPDATE notifications SET read_at=? WHERE id=? AND (user_id IS NULL OR user_id=?)", (datetime.utcnow().isoformat(timespec="seconds"), record_id, user["id"]))
                if not cursor.rowcount:
                    raise APIError("Notification not found.", 404)
            self.send_json({"message": "Notification marked as read."})
            return
        if method == "DELETE":
            if module not in {"departments", "beds", "staff"}:
                raise APIError("This record cannot be deleted.", 405)
            if module == "staff" and record_id == user["id"]:
                raise APIError("You cannot deactivate your own account.", 400)
            table = {"departments": "departments", "beds": "beds", "staff": "users"}[module]
            with connect() as db:
                cursor = db.execute(f"UPDATE {table} SET active=0 WHERE id=?", (record_id,))
                if not cursor.rowcount:
                    raise APIError("Record not found.", 404)
                self.record_activity(db,user["id"],f"{module.title()} record deactivated",module,record_id)
            self.send_json({"message": "Record deactivated."})
            return
        if module=="beds" and method=="PATCH":
            status=clean_text(data,"status","Status",max_length=20)
            if status not in {"available","maintenance"}: raise APIError("Occupied beds can only be released by discharging the patient.")
            with connect() as db:
                row=db.execute("SELECT status FROM beds WHERE id=?",(record_id,)).fetchone()
                if not row: raise APIError("Bed not found.",404)
                if row["status"]=="occupied": raise APIError("Discharge the patient before changing bed status.",409)
                db.execute("UPDATE beds SET status=? WHERE id=?",(status,record_id))
                self.record_activity(db,user["id"],f"Bed marked {status}","beds",record_id)
            self.send_json({"message":"Bed status updated."})
            return
        if module=="staff" and method=="PATCH":
            active=data.get("active")
            if not isinstance(active,bool): raise APIError("Active must be true or false.")
            if record_id==user["id"] and not active: raise APIError("You cannot deactivate your own account.")
            with connect() as db:
                cursor=db.execute("UPDATE users SET active=? WHERE id=?",(int(active),record_id))
                if not cursor.rowcount: raise APIError("Staff member not found.",404)
                if not active: db.execute("DELETE FROM sessions WHERE user_id=?",(record_id,))
                self.record_activity(db,user["id"],f"Staff account {'restored' if active else 'deactivated'}","staff",record_id)
            self.send_json({"message":"Staff account updated."})
            return
        if module == "admissions" and method == "PATCH":
            if not record_id:
                raise APIError("An admission ID is required.", 400)
            discharge_on = validate_date(clean_text(data, "discharged_on", "Discharge date", max_length=10), "Discharge date")
            with connect() as db:
                row = db.execute("SELECT bed_id,status,admitted_on FROM admissions WHERE id=?", (record_id,)).fetchone()
                if not row:
                    raise APIError("Admission not found.", 404)
                if row["status"] == "discharged":
                    raise APIError("This patient has already been discharged.", 409)
                if discharge_on < row["admitted_on"]:
                    raise APIError("Discharge date cannot be before admission.")
                db.execute("UPDATE admissions SET status='discharged',discharged_on=? WHERE id=?", (discharge_on,record_id))
                if row["bed_id"]:
                    db.execute("UPDATE beds SET status='available' WHERE id=? AND status='occupied'", (row["bed_id"],))
                self.record_activity(db,user["id"],"Patient discharged","admissions",record_id)
            self.send_json({"message": "Patient discharged and bed released."})
            return
        if module == "billing" and method == "PATCH":
            if not record_id:
                raise APIError("An invoice ID is required.", 400)
            status = clean_text(data, "status", "Status", max_length=12)
            if status not in {"draft", "issued", "paid", "void"}:
                raise APIError("Choose a valid invoice status.")
            with connect() as db:
                cursor = db.execute("UPDATE invoices SET status=? WHERE id=?", (status, record_id))
                if not cursor.rowcount:
                    raise APIError("Invoice not found.", 404)
                if status=="paid":
                    db.execute("UPDATE invoices SET paid_on=COALESCE(paid_on,?) WHERE id=?",(date.today().isoformat(),record_id))
                elif status in {"draft","issued","void"}:
                    db.execute("UPDATE invoices SET paid_on=NULL WHERE id=?",(record_id,))
                self.record_activity(db,user["id"],f"Invoice marked {status}","billing",record_id)
            self.send_json({"message": "Invoice updated."})
            return
        if module == "laboratory" and method == "PATCH":
            if not record_id:
                raise APIError("A lab order ID is required.", 400)
            status = clean_text(data, "status", "Status", max_length=20)
            if status not in {"ordered", "in_progress", "completed", "cancelled"}:
                raise APIError("Choose a valid lab status.")
            result = clean_text(data, "result", "Result", required=False, max_length=2000)
            with connect() as db:
                cursor = db.execute("UPDATE lab_orders SET status=?,result=? WHERE id=?", (status,result,record_id))
                if not cursor.rowcount:
                    raise APIError("Lab order not found.", 404)
                self.record_activity(db,user["id"],"Laboratory result updated","laboratory",record_id)
            self.send_json({"message": "Laboratory order updated."})
            return
        if method not in {"POST", "PUT"} or (method == "PUT" and not record_id):
            raise APIError("Method not allowed.", 405)
        with connect() as db:
            cursor = self.insert_module_record(db, module, data, record_id)
            self.record_activity(db,user["id"],f"{module.replace('_',' ').title()} record {'updated' if record_id else 'created'}",module,record_id or cursor.lastrowid)
        self.send_json({"id": record_id or cursor.lastrowid, "message": "Record saved."}, 200 if record_id else 201)

    @staticmethod
    def record_activity(db,user_id,message,entity,entity_id=None):
        created=datetime.utcnow().isoformat(timespec="seconds")
        db.execute("INSERT INTO audit_log(user_id,action,entity,entity_id,created_at) VALUES(?,?,?,?,?)",(user_id,message,entity,entity_id,created))
        db.execute("INSERT INTO notifications(user_id,message,category,created_at) VALUES(?,?,?,?)",(user_id,message,"activity",created))

    def insert_module_record(self, db, module, data, record_id):
        now = datetime.utcnow().isoformat(timespec="seconds")
        if module == "departments":
            values = (clean_text(data,"name","Department",max_length=100),clean_text(data,"head","Department head",False,100),clean_text(data,"extension","Extension",False,20),clean_text(data,"description","Description",False,500))
            return self.upsert(db,"departments",("name","head","extension","description"),values,record_id,now)
        if module == "beds":
            values = (clean_text(data,"bed_number","Bed number",max_length=30),clean_text(data,"ward","Ward",max_length=80),clean_text(data,"bed_type","Bed type",max_length=50),clean_text(data,"notes","Notes",False,250))
            return self.upsert(db,"beds",("bed_number","ward","bed_type","notes"),values,record_id,now)
        if module == "records":
            patient_id = self.positive_id(data.get("patient_id"),"patient")
            doctor_id = self.optional_id(data.get("doctor_id"),"doctor")
            visit = validate_date(clean_text(data,"visit_date","Visit date",max_length=10),"Visit date")
            values=(patient_id,doctor_id,visit,clean_text(data,"diagnosis","Diagnosis",max_length=500),clean_text(data,"treatment","Treatment",False,1000),clean_text(data,"notes","Notes",False,2000))
            return self.upsert(db,"medical_records",("patient_id","doctor_id","visit_date","diagnosis","treatment","notes"),values,record_id,now)
        if module == "admissions":
            patient_id=self.positive_id(data.get("patient_id"),"patient")
            doctor_id=self.optional_id(data.get("doctor_id"),"doctor")
            bed_id=self.optional_id(data.get("bed_id"),"bed")
            admitted=validate_date(clean_text(data,"admitted_on","Admission date",max_length=10),"Admission date")
            diagnosis=clean_text(data,"diagnosis","Diagnosis",max_length=500)
            if record_id:
                raise APIError("Admissions are updated through discharge.",405)
            if db.execute("SELECT 1 FROM admissions WHERE patient_id=? AND status='admitted'",(patient_id,)).fetchone():
                raise APIError("This patient already has an active admission.",409)
            if bed_id:
                bed=db.execute("SELECT status FROM beds WHERE id=?",(bed_id,)).fetchone()
                if not bed or bed["status"]!="available":
                    raise APIError("Choose an available bed.",409)
                db.execute("UPDATE beds SET status='occupied' WHERE id=?",(bed_id,))
            cursor=db.execute("INSERT INTO admissions (patient_id,doctor_id,bed_id,admitted_on,diagnosis,created_at) VALUES (?,?,?,?,?,?)",(patient_id,doctor_id,bed_id,admitted,diagnosis,now))
            return cursor
        if module == "billing":
            patient_id=self.positive_id(data.get("patient_id"),"patient")
            appointment_id=self.optional_id(data.get("appointment_id"),"appointment")
            try: amount=int(round(float(data.get("amount",0))*100))
            except (ValueError,TypeError): raise APIError("Enter a valid invoice amount.")
            if amount<0 or amount>100_000_000_00: raise APIError("Invoice amount is outside the allowed range.")
            currency=clean_text(data,"currency","Currency",max_length=3).upper()
            if not re.fullmatch(r"[A-Z]{3}",currency): raise APIError("Enter a 3-letter currency code.")
            description=clean_text(data,"description","Description",max_length=500)
            status=clean_text(data,"status","Status",max_length=12)
            if status not in {"draft","issued","paid","void"}: raise APIError("Choose a valid invoice status.")
            issued=validate_date(clean_text(data,"issued_on","Issue date",max_length=10),"Issue date")
            due=validate_date(clean_text(data,"due_on","Due date",max_length=10),"Due date")
            if due<issued: raise APIError("Due date cannot be before the issue date.")
            if record_id:
                raise APIError("Invoice details are not editable after creation.",405)
            number=f"CF-{date.today():%y%m}-{secrets.token_hex(3).upper()}"
            paid_on=date.today().isoformat() if status=="paid" else None
            return db.execute("INSERT INTO invoices(invoice_number,patient_id,appointment_id,description,amount_cents,currency,status,issued_on,due_on,paid_on,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(number,patient_id,appointment_id,description,amount,currency,status,issued,due,paid_on,now))
        if module == "pharmacy":
            name=clean_text(data,"name","Medicine",max_length=120)
            sku=clean_text(data,"sku","SKU",max_length=40)
            try: quantity=int(data.get("quantity",0)); reorder=int(data.get("reorder_level",0)); price=int(round(float(data.get("unit_price",0))*100))
            except (ValueError,TypeError): raise APIError("Quantity, reorder level and price must be valid numbers.")
            if not 0<=quantity<=1_000_000 or not 0<=reorder<=1_000_000 or not 0<=price<=100_000_000: raise APIError("Medicine stock or price is outside the allowed range.")
            unit=clean_text(data,"unit","Unit",max_length=30)
            expires=clean_text(data,"expires_on","Expiry date",False,10)
            if expires: expires=validate_date(expires,"Expiry date")
            return self.upsert(db,"medicines",("name","sku","quantity","reorder_level","unit","expires_on","unit_price_cents"),(name,sku,quantity,reorder,unit,expires,price),record_id,now)
        if module == "laboratory":
            patient_id=self.positive_id(data.get("patient_id"),"patient")
            doctor_id=self.optional_id(data.get("doctor_id"),"doctor")
            test=clean_text(data,"test_name","Test name",max_length=150)
            ordered=validate_date(clean_text(data,"ordered_on","Order date",max_length=10),"Order date")
            notes=clean_text(data,"notes","Notes",False,1000)
            if record_id: raise APIError("Lab orders are updated through result/status actions.",405)
            return db.execute("INSERT INTO lab_orders(patient_id,doctor_id,test_name,ordered_on,notes,created_at) VALUES(?,?,?,?,?,?)",(patient_id,doctor_id,test,ordered,notes,now))
        if module == "staff":
            name=clean_text(data,"name","Name",max_length=100)
            email=clean_text(data,"email","Email",max_length=254).lower(); validate_email(email)
            role=clean_text(data,"role","Role",max_length=20)
            if role not in ROLES: raise APIError("Choose a valid staff role.")
            if record_id:
                if record_id==self.current_user()["id"]: raise APIError("Use profile settings to change your own account.",400)
                cursor=db.execute("UPDATE users SET name=?,email=?,role=? WHERE id=?",(name,email,role,record_id))
                if not cursor.rowcount: raise APIError("Staff member not found.",404)
                return cursor
            password=self.validate_password(data)
            salt,digest=self.hash_password(password)
            return db.execute("INSERT INTO users(name,email,role,password_salt,password_hash,created_at) VALUES(?,?,?,?,?,?)",(name,email,role,salt,digest,now))
        raise APIError("This module does not support this action yet.",405)

    @staticmethod
    def upsert(db, table, columns, values, record_id, now):
        if record_id:
            assignments=",".join(f"{column}=?" for column in columns)
            cursor=db.execute(f"UPDATE {table} SET {assignments} WHERE id=?",(*values,record_id))
            if not cursor.rowcount: raise APIError("Record not found.",404)
            return cursor
        placeholders=",".join("?" for _ in columns)
        return db.execute(f"INSERT INTO {table}({','.join(columns)},created_at) VALUES({placeholders},?)",(*values,now))

    @staticmethod
    def optional_id(value,label):
        if value in ("",None): return None
        return CareflowHandler.positive_id(value,label)

    def handle_profile_write(self, method, data, user):
        if method != "PUT":
            raise APIError("Method not allowed.",405)
        name=clean_text(data,"name","Name",max_length=100)
        password=data.get("password","")
        with connect() as db:
            db.execute("UPDATE users SET name=? WHERE id=?",(name,user["id"]))
            if password:
                password=self.validate_password(data)
                salt,digest=self.hash_password(password)
                db.execute("UPDATE users SET password_salt=?,password_hash=? WHERE id=?",(salt,digest,user["id"]))
                db.execute("DELETE FROM sessions WHERE user_id=?",(user["id"],))
                self.create_session(db,user["id"])
                self.set_cookie(self.new_session_token,60*60*12)
        self.send_json({"message":"Profile updated.","user":dict(user,name=name)})

    def handle_report_export(self, query, user):
        self.require_role(user,"reports")
        start=validate_date(query.get("from",[date.today().replace(day=1).isoformat()])[0],"Start date")
        end=validate_date(query.get("to",[date.today().isoformat()])[0],"End date")
        if start>end: raise APIError("Start date must be on or before end date.")
        department=query.get("department",["all"])[0]
        department_sql="" if department=="all" else " AND a.department=?"
        args=[start,end]+([] if department=="all" else [department])
        with connect() as db:
            rows=db.execute(
                self.appointment_query()+" WHERE a.date BETWEEN ? AND ?"+department_sql+" ORDER BY a.date,a.time",
                args).fetchall()
        output=io.StringIO()
        writer=csv.writer(output)
        writer.writerow(["Date","Time","Patient ID","Patient","Doctor","Department","Reason","Status"])
        for row in rows:
            writer.writerow([row["date"],row["time"],row["patient_code"],row["patient_name"],row["doctor_name"],row["department"],row["reason"],row["status"]])
        content=output.getvalue().encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type","text/csv; charset=utf-8")
        self.send_header("Content-Disposition",f'attachment; filename="careflow-report-{start}-to-{end}.csv"')
        self.send_header("Content-Length",str(len(content)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(content)

    def handle_get(self, path, query, user):
        with connect() as db:
            if path == "/api/health":
                self.send_json({"status": "ok"})
            elif path == "/api/dashboard":
                today = date.today().isoformat()
                month = today[:7]
                week_start = (date.today() - timedelta(days=6)).isoformat()
                stats = {
                    "patients": db.execute("SELECT COUNT(*) FROM patients WHERE active = 1").fetchone()[0],
                    "new_patients": db.execute("SELECT COUNT(*) FROM patients WHERE active = 1 AND created_at >= ?", (f"{month}-01",)).fetchone()[0],
                    "today_appointments": db.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND status != 'cancelled'", (today,)).fetchone()[0],
                    "upcoming": db.execute("SELECT COUNT(*) FROM appointments WHERE date = ? AND time > ? AND status = 'scheduled'", (today, datetime.now().strftime("%H:%M"))).fetchone()[0],
                    "doctors": db.execute("SELECT COUNT(*) FROM doctors WHERE active = 1").fetchone()[0],
                    "completed_month": db.execute("SELECT COUNT(*) FROM appointments WHERE date LIKE ? AND status = 'completed'", (f"{month}-%",)).fetchone()[0],
                    "completion_rate": self.completion_rate(db, month),
                    "admissions": db.execute("SELECT COUNT(*) FROM admissions WHERE status='admitted'").fetchone()[0],
                    "beds": db.execute("SELECT COUNT(*) FROM beds").fetchone()[0],
                    "occupied_beds": db.execute("SELECT COUNT(*) FROM beds WHERE status='occupied'").fetchone()[0],
                    "revenue_received": [as_dict(row) for row in db.execute("SELECT currency,SUM(amount_cents) AS total_cents FROM invoices WHERE status='paid' AND paid_on LIKE ? GROUP BY currency",(f"{month}-%",)).fetchall()],
                    "billing_outstanding": [as_dict(row) for row in db.execute("SELECT currency,SUM(amount_cents) AS total_cents FROM invoices WHERE status IN ('issued','draft') GROUP BY currency").fetchall()],
                }
                restricted=user["role"]=="billing"
                today_rows = [] if restricted else db.execute(self.appointment_query() + " WHERE a.date = ? AND a.status != 'cancelled' ORDER BY a.time", (today,)).fetchall()
                recent_rows = [] if restricted else db.execute(self.appointment_query() + " ORDER BY a.date DESC, a.time DESC LIMIT 6").fetchall()
                departments = db.execute("SELECT department, COUNT(*) AS count FROM appointments WHERE date LIKE ? AND status != 'cancelled' GROUP BY department", (f"{month}-%",)).fetchall()
                doctors = [] if restricted else db.execute("SELECT id, name FROM doctors WHERE active = 1 ORDER BY name").fetchall()
                trends = db.execute("SELECT date,COUNT(*) AS count FROM appointments WHERE date BETWEEN ? AND ? AND status!='cancelled' GROUP BY date ORDER BY date",(week_start,today)).fetchall()
                next_appointments = [] if restricted else db.execute(self.appointment_query()+" WHERE a.date>=? AND a.status='scheduled' ORDER BY a.date,a.time LIMIT 5",(today,)).fetchall()
                admissions_today = [] if restricted else db.execute(
                    """SELECT a.id,p.name AS patient_name,p.patient_code,a.admitted_on,a.diagnosis,
                       b.bed_number,b.ward FROM admissions a JOIN patients p ON p.id=a.patient_id
                       LEFT JOIN beds b ON b.id=a.bed_id WHERE a.status='admitted'
                       ORDER BY a.admitted_on DESC LIMIT 5""").fetchall()
                mode=db.execute("SELECT value FROM app_meta WHERE key='data_mode'").fetchone()["value"]
                self.send_json({"stats": stats, "today": [as_dict(row) for row in today_rows], "recent": [as_dict(row) for row in recent_rows], "upcoming": [as_dict(row) for row in next_appointments], "admissions_today":[as_dict(row) for row in admissions_today],"trends":[as_dict(row) for row in trends],"departments": {row["department"]: row["count"] for row in departments}, "doctors": [as_dict(row) for row in doctors],"data_mode":mode})
            elif path == "/api/patients":
                search = query.get("q", [""])[0].strip()
                include_inactive = query.get("include_inactive", ["false"])[0] == "true"
                if user["role"]=="billing":
                    sql = "SELECT p.id,p.patient_code,p.name,p.active FROM patients p WHERE 1=1"
                else:
                    sql = "SELECT p.*, CAST((julianday('now') - julianday(p.date_of_birth)) / 365.2425 AS INTEGER) AS age, (SELECT MAX(date) FROM appointments a WHERE a.patient_id = p.id AND a.status = 'completed') AS last_visit FROM patients p WHERE 1=1"
                args = []
                if not include_inactive:
                    sql += " AND p.active = 1"
                if search:
                    sql += " AND (p.name LIKE ? OR p.patient_code LIKE ? OR p.email LIKE ? OR p.phone LIKE ?)"
                    args.extend([f"%{search}%"] * 4)
                order = query.get("sort", ["name"])[0]
                direction = "DESC" if query.get("direction", ["asc"])[0].lower() == "desc" else "ASC"
                order_by = {"name":"p.name","id":"p.patient_code","created":"p.created_at","last_visit":"last_visit"}.get(order,"p.name")
                try:
                    page=max(1,int(query.get("page",["1"])[0]))
                    page_size=min(100,max(5,int(query.get("page_size",["20"])[0])))
                except ValueError:
                    raise APIError("Invalid patient page.")
                total=db.execute("SELECT COUNT(*) FROM patients p WHERE 1=1" + (" AND p.active=1" if not include_inactive else "") + (" AND (p.name LIKE ? OR p.patient_code LIKE ? OR p.email LIKE ? OR p.phone LIKE ?)" if search else ""),
                                 ([] if not search else [f"%{search}%"]*4)).fetchone()[0]
                sql += f" ORDER BY {order_by} {direction} LIMIT ? OFFSET ?"
                args.extend([page_size,(page-1)*page_size])
                self.send_json({"items":[as_dict(row) for row in db.execute(sql,args).fetchall()],"count":total,"page":page,"page_size":page_size,"pages":max(1,(total+page_size-1)//page_size)})
            elif path == "/api/doctors":
                search = query.get("q", [""])[0].strip()
                include_inactive = query.get("include_inactive", ["false"])[0] == "true"
                sql = "SELECT * FROM doctors WHERE 1=1"
                args = []
                if not include_inactive:
                    sql += " AND active = 1"
                if search:
                    sql += " AND (name LIKE ? OR specialty LIKE ? OR department LIKE ? OR email LIKE ?)"
                    args.extend([f"%{search}%"] * 4)
                self.send_json([as_dict(row) for row in db.execute(sql + " ORDER BY name COLLATE NOCASE LIMIT 500", args).fetchall()])
            elif path == "/api/appointments":
                search = query.get("q", [""])[0].strip()
                status = query.get("status", ["all"])[0]
                sql = self.appointment_query() + " WHERE 1=1"
                args = []
                if status in {"scheduled", "completed", "cancelled"}:
                    sql += " AND a.status = ?"
                    args.append(status)
                if search:
                    sql += " AND (p.name LIKE ? OR p.patient_code LIKE ? OR d.name LIKE ? OR a.department LIKE ? OR a.reason LIKE ?)"
                    args.extend([f"%{search}%"] * 5)
                for filter_name, column in (("from","a.date >= ?"),("to","a.date <= ?"),("date","a.date = ?"),("department","a.department = ?")):
                    filter_value=query.get(filter_name,[""])[0].strip()
                    if filter_value and filter_value != "all":
                        if filter_name in {"from","to","date"}:
                            filter_value=validate_date(filter_value,"Appointment date")
                        sql += " AND " + column
                        args.append(filter_value)
                doctor_id=query.get("doctor_id",[""])[0]
                if doctor_id:
                    args.append(self.positive_id(doctor_id,"doctor"))
                    sql += " AND a.doctor_id=?"
                sql += " ORDER BY a.date DESC, a.time DESC LIMIT 500"
                self.send_json([as_dict(row) for row in db.execute(sql, args).fetchall()])
            else:
                raise APIError("Not found.", 404)

    def handle_patient_detail(self, patient_id):
        with connect() as db:
            patient=db.execute(
                """SELECT p.*,CAST((julianday('now')-julianday(p.date_of_birth))/365.2425 AS INTEGER) AS age
                   FROM patients p WHERE p.id=?""",(patient_id,)).fetchone()
            if not patient:
                raise APIError("Patient not found.",404)
            visits=db.execute(self.appointment_query()+" WHERE a.patient_id=? ORDER BY a.date DESC,a.time DESC LIMIT 100",(patient_id,)).fetchall()
            records=db.execute(
                """SELECT r.id,r.visit_date,r.diagnosis,r.treatment,r.notes,COALESCE(d.name,'Unassigned') AS doctor_name
                   FROM medical_records r LEFT JOIN doctors d ON d.id=r.doctor_id
                   WHERE r.patient_id=? ORDER BY r.visit_date DESC LIMIT 100""",(patient_id,)).fetchall()
        self.send_json({"patient":as_dict(patient),"appointments":[as_dict(row) for row in visits],"records":[as_dict(row) for row in records]})

    @staticmethod
    def appointment_query():
        return """SELECT a.id, a.patient_id, a.doctor_id, p.patient_code, p.name AS patient_name,
                  d.name AS doctor_name, a.date, a.time, a.duration_minutes, a.department, a.reason, a.status
                  FROM appointments a JOIN patients p ON p.id = a.patient_id
                  JOIN doctors d ON d.id = a.doctor_id"""

    def appointment_values(self, db, data, ignore_id=None):
        patient_id=self.positive_id(data.get("patient_id"),"patient")
        doctor_id=self.positive_id(data.get("doctor_id"),"doctor")
        visit_date=validate_date(clean_text(data,"date","Date",max_length=10),"Date",allow_past=False)
        visit_time=clean_text(data,"time","Time",max_length=5)
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",visit_time):
            raise APIError("Choose a valid appointment time.")
        duration_value=data.get("duration_minutes",30)
        try: duration=int(duration_value)
        except (ValueError,TypeError): raise APIError("Appointment length must be a whole number.")
        if not 15<=duration<=240: raise APIError("Appointment length must be between 15 and 240 minutes.")
        start_minutes=int(visit_time[:2])*60+int(visit_time[3:])
        if start_minutes+duration>1440: raise APIError("Appointment cannot extend beyond midnight.")
        if visit_date==date.today().isoformat() and start_minutes<=datetime.now().hour*60+datetime.now().minute:
            raise APIError("Choose a future time for today.")
        department=clean_text(data,"department","Department",max_length=100)
        reason=clean_text(data,"reason","Reason",required=False,max_length=250)
        if not db.execute("SELECT id FROM departments WHERE name=? AND active=1",(department,)).fetchone():
            raise APIError("Choose an active hospital department.")
        patient=db.execute("SELECT id FROM patients WHERE id=? AND active=1",(patient_id,)).fetchone()
        doctor=db.execute("SELECT id,availability FROM doctors WHERE id=? AND active=1",(doctor_id,)).fetchone()
        if not patient: raise APIError("Choose an active patient.",400)
        if not doctor: raise APIError("Choose an active doctor.",400)
        availability=doctor["availability"].lower()
        day=date.fromisoformat(visit_date).weekday()
        if ("weekdays" in availability and day>=5) or ("weekends" in availability and day<5):
            raise APIError("The selected doctor is not available on that day.",409)
        match=re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*[–-]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)",availability)
        if match:
            h1,m1,p1,h2,m2,p2=match.groups()
            begin=(int(h1)%12+(12 if p1=="pm" else 0))*60+int(m1 or 0)
            finish=(int(h2)%12+(12 if p2=="pm" else 0))*60+int(m2 or 0)
            if start_minutes<begin or start_minutes+duration>finish:
                raise APIError("The selected time is outside this doctor's availability.",409)
        existing=db.execute("SELECT time,duration_minutes FROM appointments WHERE doctor_id=? AND date=? AND status='scheduled' AND id!=?",(doctor_id,visit_date,ignore_id or -1)).fetchall()
        for booking in existing:
            other_start=int(booking["time"][:2])*60+int(booking["time"][3:])
            if start_minutes<other_start+booking["duration_minutes"] and other_start<start_minutes+duration:
                raise APIError("That time overlaps with another appointment for this doctor.",409)
        return patient_id,doctor_id,visit_date,visit_time,duration,department,reason

    @staticmethod
    def completion_rate(db, month):
        total = db.execute("SELECT COUNT(*) FROM appointments WHERE date LIKE ? AND status != 'cancelled'", (f"{month}-%",)).fetchone()[0]
        completed = db.execute("SELECT COUNT(*) FROM appointments WHERE date LIKE ? AND status = 'completed'", (f"{month}-%",)).fetchone()[0]
        return round(completed / total * 100) if total else 0

    def handle_write(self, path, method, data, user):
        match = re.fullmatch(r"/api/(patients|doctors|appointments)(?:/(\d+))?", path)
        if not match:
            raise APIError("Not found.", 404)
        resource, raw_id = match.groups()
        record_id = int(raw_id) if raw_id else None
        if method == "POST" and record_id is None and resource in {"patients", "doctors", "appointments"}:
            with connect() as db:
                if resource == "patients":
                    name, email, phone = validate_person(data)
                    birth_date = clean_text(data, "date_of_birth", "Date of birth", required=False, max_length=10)
                    if birth_date:
                        birth_date = validate_date(birth_date, "Date of birth")
                        if date.fromisoformat(birth_date) > date.today():
                            raise APIError("Date of birth cannot be in the future.")
                    gender = clean_text(data, "gender", "Gender", required=False, max_length=30)
                    blood = clean_text(data, "blood_group", "Blood group", required=False, max_length=4)
                    address = clean_text(data, "address", "Address", required=False, max_length=250)
                    valid_gender = {"", "Female", "Male", "Non-binary", "Prefer not to say"}
                    valid_blood = {"", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
                    if gender not in valid_gender or blood not in valid_blood:
                        raise APIError("Choose a valid gender and blood group.")
                    cursor = db.execute(
                        """INSERT INTO patients (name, email, phone, date_of_birth, gender, blood_group, address, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (name, email, phone, birth_date, gender, blood, address, date.today().isoformat()),
                    )
                    db.execute("UPDATE patients SET patient_code = ? WHERE id = ?", (f"PT-{1000 + cursor.lastrowid}", cursor.lastrowid))
                    self.record_activity(db,user["id"],"Patient record created","patients",cursor.lastrowid)
                    self.send_json({"id": cursor.lastrowid, "message": "Patient created."}, 201)
                elif resource == "doctors":
                    name, email, phone = validate_person(data)
                    specialty = clean_text(data, "specialty", "Specialty", max_length=100)
                    department = clean_text(data, "department", "Department", max_length=50)
                    if not db.execute("SELECT id FROM departments WHERE name=? AND active=1",(department,)).fetchone():
                        raise APIError("Choose an active hospital department.")
                    try:
                        experience = int(data.get("experience", 0))
                    except (ValueError, TypeError):
                        raise APIError("Experience must be a whole number.")
                    if not 0 <= experience <= 80:
                        raise APIError("Experience must be between 0 and 80 years.")
                    bio = clean_text(data, "bio", "Bio", required=False, max_length=500)
                    availability=clean_text(data,"availability","Availability",max_length=120)
                    if not re.search(r"\b(weekdays|weekends|daily|every day)\b",availability.lower()):
                        raise APIError("Availability must specify weekdays, weekends, or daily.")
                    cursor = db.execute("INSERT INTO doctors (name, specialty, department, email, phone, experience, bio, availability) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (name, specialty, department, email, phone, experience, bio,availability))
                    self.record_activity(db,user["id"],"Doctor profile created","doctors",cursor.lastrowid)
                    self.send_json({"id": cursor.lastrowid, "message": "Doctor created."}, 201)
                else:
                    db.execute("BEGIN IMMEDIATE")
                    patient_id,doctor_id,visit_date,visit_time,duration,department,reason=self.appointment_values(db,data)
                    cursor = db.execute("INSERT INTO appointments (patient_id, doctor_id, date, time, duration_minutes, department, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (patient_id, doctor_id, visit_date, visit_time,duration, department, reason, datetime.now().isoformat(timespec="seconds")))
                    self.record_activity(db,user["id"],"Appointment booked","appointments",cursor.lastrowid)
                    self.send_json({"id": cursor.lastrowid, "message": "Appointment created."}, 201)
            return
        if record_id is None:
            raise APIError("A record ID is required.", 404)
        with connect() as db:
            if resource in {"patients", "doctors"} and method == "DELETE":
                active = data.get("active", False)
                if not isinstance(active, bool):
                    raise APIError("Active must be true or false.")
                cursor = db.execute(f"UPDATE {resource} SET active = ? WHERE id = ?", (int(active), record_id))
                if cursor.rowcount == 0:
                    raise APIError("Record not found.", 404)
                self.record_activity(db,user["id"],f"{resource[:-1].title()} {'restored' if active else 'archived'}",resource,record_id)
                self.send_json({"message": "Record status updated."})
            elif resource in {"patients", "doctors"} and method == "PUT":
                if resource == "patients":
                    name, email, phone = validate_person(data)
                    birth_date = clean_text(data, "date_of_birth", "Date of birth", required=False, max_length=10)
                    if birth_date:
                        birth_date = validate_date(birth_date, "Date of birth")
                        if date.fromisoformat(birth_date) > date.today():
                            raise APIError("Date of birth cannot be in the future.")
                    gender = clean_text(data, "gender", "Gender", required=False, max_length=30)
                    blood = clean_text(data, "blood_group", "Blood group", required=False, max_length=4)
                    address = clean_text(data, "address", "Address", required=False, max_length=250)
                    if gender not in {"", "Female", "Male", "Non-binary", "Prefer not to say"} or blood not in {"", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}:
                        raise APIError("Choose a valid gender and blood group.")
                    cursor = db.execute("UPDATE patients SET name=?, email=?, phone=?, date_of_birth=?, gender=?, blood_group=?, address=? WHERE id=?", (name, email, phone, birth_date, gender, blood, address, record_id))
                else:
                    name, email, phone = validate_person(data)
                    specialty = clean_text(data, "specialty", "Specialty", max_length=100)
                    department = clean_text(data, "department", "Department", max_length=50)
                    if department not in DEPARTMENTS:
                        raise APIError("Choose a valid department.")
                    try:
                        experience = int(data.get("experience", 0))
                    except (ValueError, TypeError):
                        raise APIError("Experience must be a whole number.")
                    if not 0 <= experience <= 80:
                        raise APIError("Experience must be between 0 and 80 years.")
                    bio = clean_text(data, "bio", "Bio", required=False, max_length=500)
                    if not db.execute("SELECT id FROM departments WHERE name=? AND active=1",(department,)).fetchone():
                        raise APIError("Choose an active hospital department.")
                    availability=clean_text(data,"availability","Availability",max_length=120)
                    if not re.search(r"\b(weekdays|weekends|daily|every day)\b",availability.lower()):
                        raise APIError("Availability must specify weekdays, weekends, or daily.")
                    cursor = db.execute("UPDATE doctors SET name=?, specialty=?, department=?, email=?, phone=?, experience=?, bio=?,availability=? WHERE id=?", (name, specialty, department, email, phone, experience, bio,availability,record_id))
                if cursor.rowcount == 0:
                    raise APIError("Record not found.", 404)
                self.record_activity(db,user["id"],f"{resource[:-1].title()} profile updated",resource,record_id)
                self.send_json({"message": "Record updated."})
            elif resource == "appointments" and method == "PUT":
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT id FROM appointments WHERE id=?",(record_id,)).fetchone():
                    raise APIError("Appointment not found.",404)
                values=self.appointment_values(db,data,record_id)
                cursor=db.execute("UPDATE appointments SET patient_id=?,doctor_id=?,date=?,time=?,duration_minutes=?,department=?,reason=?,status='scheduled' WHERE id=?",
                                  (*values,record_id))
                if not cursor.rowcount: raise APIError("Appointment not found.",404)
                self.record_activity(db,user["id"],"Appointment rescheduled","appointments",record_id)
                self.send_json({"message":"Appointment rescheduled."})
            elif resource == "appointments" and method == "PATCH":
                status = clean_text(data, "status", "Status", max_length=20)
                if status not in {"scheduled", "completed", "cancelled"}:
                    raise APIError("Choose a valid appointment status.")
                if status=="scheduled":
                    db.execute("BEGIN IMMEDIATE")
                    row=db.execute("SELECT patient_id,doctor_id,date,time,duration_minutes,department,reason FROM appointments WHERE id=?",(record_id,)).fetchone()
                    if not row: raise APIError("Appointment not found.",404)
                    self.appointment_values(db,dict(row),record_id)
                cursor = db.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, record_id))
                if cursor.rowcount == 0:
                    raise APIError("Appointment not found.", 404)
                self.record_activity(db,user["id"],f"Appointment marked {status}","appointments",record_id)
                self.send_json({"message": "Appointment updated."})
            else:
                raise APIError("Method not allowed.", 405)

    @staticmethod
    def positive_id(value, label):
        try:
            result = int(value)
        except (ValueError, TypeError):
            raise APIError(f"Choose a valid {label}.")
        if result <= 0:
            raise APIError(f"Choose a valid {label}.")
        return result

    def serve_static(self, path, head_only=False):
        if path in {"/", "/index.html"}:
            path = "/index.html"
        requested = (ROOT / unquote(path.lstrip("/"))).resolve()
        if ROOT not in requested.parents or not requested.is_file():
            self.send_error(404, "File not found")
            return
        content_types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
        try:
            content = requested.read_bytes()
        except OSError:
            self.send_error(500, "Could not read file")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(requested.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(content)


if __name__ == "__main__":
    initialize_database()
    print(f"Careflow is running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the server.")
    ThreadingHTTPServer((HOST, PORT), CareflowHandler).serve_forever()
