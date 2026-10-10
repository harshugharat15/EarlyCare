import sqlite3
import os

# Works both locally and on Render server
DB_PATH = os.environ.get('DATABASE_URL', 
          os.path.join(os.path.dirname(__file__), 'database', 'earlycare.db'))

# Make sure database folder exists
os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else '.', exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # ── 1. USERS ──────────────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name   TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            password    TEXT    NOT NULL,
            age         INTEGER,
            gender      TEXT,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    ''')

    # ── 2. HEALTH SURVEY ──────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS health_survey (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            name                TEXT,
            age                 INTEGER,
            gender              TEXT,
            height_cm           REAL,
            weight_kg           REAL,
            bmi                 REAL,
            water_intake_liters REAL,
            activity_level      TEXT,
            sleep_hours         REAL,
            takes_medicine      TEXT,
            needs_reminders     TEXT,
            smoking_status      TEXT,
            diet_type           TEXT,
            stress_level        TEXT,
            submitted_at        TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 3. HEALTH PROFILE ─────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS health_profile (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id                 INTEGER NOT NULL UNIQUE,
            bmi                     REAL,
            bmi_category            TEXT,
            water_suggestion        TEXT,
            exercise_suggestion     TEXT,
            medicine_suggestion     TEXT,
            sleep_suggestion        TEXT,
            general_note            TEXT,
            created_at              TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 4. MEDICINES ──────────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS medicines (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            medicine_name   TEXT    NOT NULL,
            dosage          TEXT,
            medicine_type   TEXT,
            food_timing     TEXT,
            reminder_time   TEXT,
            start_date      TEXT,
            end_date        TEXT,
            notes           TEXT,
            is_active       INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 5. WATER REMINDERS ────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS water_reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL UNIQUE,
            daily_goal      REAL,
            goal_unit       TEXT,
            frequency_hours INTEGER,
            start_time      TEXT,
            end_time        TEXT,
            is_active       INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 6. EXERCISE REMINDERS ─────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exercise_reminders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            exercise_type   TEXT,
            reminder_time   TEXT,
            duration_min    INTEGER,
            frequency       TEXT,
            is_active       INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 7. DOCTOR APPOINTMENTS ────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS doctor_appointments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL,
            doctor_name         TEXT,
            appointment_date    TEXT,
            appointment_time    TEXT,
            notes               TEXT,
            status              TEXT DEFAULT 'Upcoming',
            created_at          TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 8. NOTIFICATIONS ──────────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            reminder_type   TEXT,
            reminder_ref_id INTEGER,
            message         TEXT,
            scheduled_time  TEXT,
            status          TEXT DEFAULT 'Pending',
            snoozed_until   TEXT,
            created_at      TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ── 9. REMINDER HISTORY ───────────────────────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminder_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            reminder_name   TEXT,
            reminder_type   TEXT,
            date            TEXT,
            scheduled_time  TEXT,
            status          TEXT,
            logged_at       TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Database initialised successfully.")

if __name__ == '__main__':
    init_db()
