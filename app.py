from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime, timedelta
from database import init_db, get_connection
from email_reminder import start_reminder_thread

app = Flask(__name__)
app.secret_key = 'earlycare_secret_key_2026'

# ─── AM/PM helper ────────────────────────────────────────────────────────────
def ampm_to_24(hour, minute, ampm):
    """Convert 12-hour AM/PM time to HH:MM 24-hour string."""
    try:
        h = int(hour)
        m = int(minute)
        if ampm == 'PM' and h != 12:
            h += 12
        elif ampm == 'AM' and h == 12:
            h = 0
        return f'{h:02d}:{m:02d}'
    except Exception:
        return '08:00'

def time24_to_ampm(time24):
    """Convert HH:MM to (hour12, minute, ampm) tuple for display."""
    try:
        h, m = map(int, time24.split(':'))
        ampm = 'AM' if h < 12 else 'PM'
        h12  = h % 12 or 12
        return str(h12), f'{m:02d}', ampm
    except Exception:
        return '8', '00', 'AM'

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def calculate_bmi(height_cm, weight_kg):
    try:
        h = float(height_cm) / 100.0
        w = float(weight_kg)
        bmi = round(w / (h * h), 2)
        return bmi
    except Exception:
        return None


def bmi_category(bmi):
    if bmi is None:
        return "N/A"
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal weight"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"


def analyse_survey(survey):
    suggestions = {}

    try:
        water = float(survey['water_intake_liters'])
    except (TypeError, ValueError):
        water = 0
    if water < 2.0:
        suggestions['water'] = "Your daily water intake seems low. Set a Water Reminder to drink at least 2 litres per day."
    else:
        suggestions['water'] = "Good water intake! Keep it up with regular Water Reminders."

    activity = (survey['activity_level'] or '').lower()
    if activity in ('sedentary', 'low', 'none', ''):
        suggestions['exercise'] = "Your physical activity level is low. An Exercise Reminder is recommended."
    else:
        suggestions['exercise'] = "You are active! Use Exercise Reminders to stay consistent."

    try:
        sleep = float(survey['sleep_hours'])
    except (TypeError, ValueError):
        sleep = 0
    if sleep < 7:
        suggestions['sleep'] = "You sleep less than 7 hours. Try to maintain 7-9 hours of sleep per night."
    else:
        suggestions['sleep'] = "Good sleep duration. Keep maintaining healthy sleep habits."

    medicine = (survey['takes_medicine'] or '').lower()
    if medicine in ('yes', 'y'):
        suggestions['medicine'] = "You take medicines regularly. Add a Medicine Reminder so you never miss a dose."
    else:
        suggestions['medicine'] = "No regular medicines reported. Consult a doctor if needed."

    return suggestions


def generate_notifications(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now().strftime('%Y-%m-%d')

    # Medicine reminders
    cursor.execute('''
        SELECT id, medicine_name, reminder_time, start_date, end_date
        FROM medicines WHERE user_id=? AND is_active=1
    ''', (user_id,))
    medicines = cursor.fetchall()
    for med in medicines:
        if med['start_date'] and med['end_date']:
            if not (med['start_date'] <= today <= med['end_date']):
                continue
        sched = today + ' ' + (med['reminder_time'] or '08:00')
        cursor.execute('''
            SELECT id FROM notifications
            WHERE user_id=? AND reminder_type='Medicine' AND reminder_ref_id=? AND scheduled_time=?
        ''', (user_id, med['id'], sched))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO notifications (user_id, reminder_type, reminder_ref_id, message, scheduled_time, status)
                VALUES (?, 'Medicine', ?, ?, ?, 'Pending')
            ''', (user_id, med['id'],
                  f"Time to take your medicine: {med['medicine_name']}", sched))

    # Water reminders
    cursor.execute('''
        SELECT id, daily_goal, goal_unit, frequency_hours, start_time, end_time
        FROM water_reminders WHERE user_id=? AND is_active=1
    ''', (user_id,))
    water = cursor.fetchone()
    if water:
        try:
            start_h, start_m = map(int, (water['start_time'] or '08:00').split(':'))
            end_h,   end_m   = map(int, (water['end_time']   or '20:00').split(':'))
            freq = int(water['frequency_hours'] or 2)
            current = datetime.strptime(today, '%Y-%m-%d').replace(hour=start_h, minute=start_m)
            end_dt  = datetime.strptime(today, '%Y-%m-%d').replace(hour=end_h,   minute=end_m)
            while current <= end_dt:
                sched = current.strftime('%Y-%m-%d %H:%M')
                cursor.execute('''
                    SELECT id FROM notifications
                    WHERE user_id=? AND reminder_type='Water' AND scheduled_time=?
                ''', (user_id, sched))
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO notifications (user_id, reminder_type, reminder_ref_id, message, scheduled_time, status)
                        VALUES (?, 'Water', ?, ?, ?, 'Pending')
                    ''', (user_id, water['id'],
                          f"Time to drink water! Goal: {water['daily_goal']} {water['goal_unit']}", sched))
                current += timedelta(hours=freq)
        except Exception:
            pass

    # Exercise reminders
    cursor.execute('''
        SELECT id, exercise_type, reminder_time, duration_min, frequency
        FROM exercise_reminders WHERE user_id=? AND is_active=1
    ''', (user_id,))
    exercises = cursor.fetchall()
    for ex in exercises:
        sched = today + ' ' + (ex['reminder_time'] or '06:00')
        cursor.execute('''
            SELECT id FROM notifications
            WHERE user_id=? AND reminder_type='Exercise' AND reminder_ref_id=? AND scheduled_time=?
        ''', (user_id, ex['id'], sched))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO notifications (user_id, reminder_type, reminder_ref_id, message, scheduled_time, status)
                VALUES (?, 'Exercise', ?, ?, ?, 'Pending')
            ''', (user_id, ex['id'],
                  f"Time for your {ex['exercise_type']} exercise ({ex['duration_min']} min)!", sched))

    # Doctor appointments
    cursor.execute('''
        SELECT id, doctor_name, appointment_date, appointment_time
        FROM doctor_appointments
        WHERE user_id=? AND appointment_date=? AND status='Upcoming'
    ''', (user_id, today))
    appts = cursor.fetchall()
    for appt in appts:
        sched = appt['appointment_date'] + ' ' + (appt['appointment_time'] or '10:00')
        cursor.execute('''
            SELECT id FROM notifications
            WHERE user_id=? AND reminder_type='Doctor' AND reminder_ref_id=? AND scheduled_time=?
        ''', (user_id, appt['id'], sched))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO notifications (user_id, reminder_type, reminder_ref_id, message, scheduled_time, status)
                VALUES (?, 'Doctor', ?, ?, ?, 'Pending')
            ''', (user_id, appt['id'],
                  f"Doctor appointment with Dr. {appt['doctor_name']} today!", sched))

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# PWA — Service Worker
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/sw.js')
def sw():
    return app.send_static_file('sw.js'), 200, {
        'Content-Type': 'application/javascript'
    }


# ─────────────────────────────────────────────────────────────────────────────
# SPLASH
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def splash():
    return render_template('splash.html')


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name        = request.form.get('full_name', '').strip()
        email            = request.form.get('email', '').strip().lower()
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        age              = request.form.get('age', '')
        gender           = request.form.get('gender', '')

        if not full_name or not email or not password:
            flash('Full Name, Email and Password are required.')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('register.html')

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email=?', (email,))
        if cursor.fetchone():
            flash('Email already registered. Please login.')
            conn.close()
            return render_template('register.html')

        cursor.execute('''
            INSERT INTO users (full_name, email, password, age, gender)
            VALUES (?, ?, ?, ?, ?)
        ''', (full_name, email, password, age or None, gender))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()

        session['user_id']    = new_id
        session['user_name']  = full_name
        session['user_email'] = email
        flash('Registration successful! Please complete your Health Survey.')
        return redirect(url_for('survey'))

    return render_template('register.html')


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and Password are required.')
            return render_template('login.html')

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email=? AND password=?', (email, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id']    = user['id']
            session['user_name']  = user['full_name']
            session['user_email'] = user['email']

            conn2 = get_connection()
            c2 = conn2.cursor()
            c2.execute('SELECT id FROM health_survey WHERE user_id=?', (user['id'],))
            survey_done = c2.fetchone()
            conn2.close()

            if survey_done:
                return redirect(url_for('dashboard'))
            else:
                flash('Welcome! Please complete your Health Survey.')
                return redirect(url_for('survey'))
        else:
            flash('Invalid email or password.')
            return render_template('login.html')

    return render_template('login.html')


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH SURVEY
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/survey', methods=['GET', 'POST'])
@login_required
def survey():
    if request.method == 'POST':
        user_id  = session['user_id']
        name     = request.form.get('name', '').strip()
        age      = request.form.get('age', '')
        gender   = request.form.get('gender', '')
        height   = request.form.get('height', '')
        weight   = request.form.get('weight', '')
        water    = request.form.get('water_intake', '')
        activity = request.form.get('activity_level', '')
        sleep    = request.form.get('sleep_hours', '')
        medicine = request.form.get('takes_medicine', '')
        reminders= request.form.get('needs_reminders', '')
        smoking  = request.form.get('smoking_status', '')
        diet     = request.form.get('diet_type', '')
        stress   = request.form.get('stress_level', '')

        bmi = calculate_bmi(height, weight) if height and weight else None

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM health_survey WHERE user_id=?', (user_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
                UPDATE health_survey SET name=?, age=?, gender=?, height_cm=?, weight_kg=?,
                bmi=?, water_intake_liters=?, activity_level=?, sleep_hours=?,
                takes_medicine=?, needs_reminders=?, smoking_status=?, diet_type=?,
                stress_level=?, submitted_at=datetime('now','localtime')
                WHERE user_id=?
            ''', (name, age, gender, height, weight, bmi, water, activity, sleep,
                  medicine, reminders, smoking, diet, stress, user_id))
        else:
            cursor.execute('''
                INSERT INTO health_survey (user_id, name, age, gender, height_cm, weight_kg,
                bmi, water_intake_liters, activity_level, sleep_hours, takes_medicine,
                needs_reminders, smoking_status, diet_type, stress_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, name, age, gender, height, weight, bmi, water, activity,
                  sleep, medicine, reminders, smoking, diet, stress))

        cat = bmi_category(bmi)
        suggestions = analyse_survey({
            'water_intake_liters': water,
            'activity_level': activity,
            'sleep_hours': sleep,
            'takes_medicine': medicine
        })

        cursor.execute('''
            INSERT OR REPLACE INTO health_profile
            (user_id, bmi, bmi_category, water_suggestion, exercise_suggestion,
             medicine_suggestion, sleep_suggestion, general_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, bmi, cat,
              suggestions.get('water', ''),
              suggestions.get('exercise', ''),
              suggestions.get('medicine', ''),
              suggestions.get('sleep', ''),
              'This prototype provides general health reminders and is NOT a medical diagnosis.'))

        conn.commit()
        conn.close()
        flash('Survey submitted! Here is your Health Profile.')
        return redirect(url_for('health_profile'))

    return render_template('survey.html', user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH PROFILE
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/health_profile')
@login_required
def health_profile():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()
    cursor.execute('SELECT * FROM health_survey WHERE user_id=?', (user_id,))
    survey = cursor.fetchone()
    cursor.execute('SELECT * FROM health_profile WHERE user_id=?', (user_id,))
    profile = cursor.fetchone()
    conn.close()
    return render_template('health_profile.html',
                           survey=survey, profile=profile,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    generate_notifications(user_id)
    conn   = get_connection()
    cursor = conn.cursor()
    today  = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('''
        SELECT * FROM notifications
        WHERE user_id=? AND scheduled_time LIKE ? AND status='Pending'
        ORDER BY scheduled_time
    ''', (user_id, today + '%'))
    todays_reminders = cursor.fetchall()

    cursor.execute('''
        SELECT * FROM doctor_appointments
        WHERE user_id=? AND appointment_date >= ? AND status='Upcoming'
        ORDER BY appointment_date, appointment_time LIMIT 5
    ''', (user_id, today))
    upcoming_appts = cursor.fetchall()

    cursor.execute('''
        SELECT COUNT(*) as cnt FROM notifications WHERE user_id=? AND status='Pending'
    ''', (user_id,))
    notif_count = cursor.fetchone()['cnt']

    conn.close()
    return render_template('dashboard.html',
                           user_name=session.get('user_name', ''),
                           todays_reminders=todays_reminders,
                           upcoming_appts=upcoming_appts,
                           notif_count=notif_count,
                           today=today)


# ─────────────────────────────────────────────────────────────────────────────
# MEDICINE
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/medicine', methods=['GET', 'POST'])
@login_required
def medicine():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            reminder_time = ampm_to_24(request.form.get('reminder_hour','8'),
                                       request.form.get('reminder_min','00'),
                                       request.form.get('reminder_ampm','AM'))
            cursor.execute('''
                INSERT INTO medicines (user_id, medicine_name, dosage, medicine_type,
                food_timing, reminder_time, start_date, end_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id,
                  request.form.get('medicine_name', ''),
                  request.form.get('dosage', ''),
                  request.form.get('medicine_type', ''),
                  request.form.get('food_timing', ''),
                  reminder_time,
                  request.form.get('start_date', ''),
                  request.form.get('end_date', ''),
                  request.form.get('notes', '')))
            conn.commit()
            flash('Medicine added successfully!')

        elif action == 'edit':
            med_id = request.form.get('med_id')
            reminder_time = ampm_to_24(request.form.get('reminder_hour','8'),
                                       request.form.get('reminder_min','00'),
                                       request.form.get('reminder_ampm','AM'))
            cursor.execute('''
                UPDATE medicines SET medicine_name=?, dosage=?, medicine_type=?,
                food_timing=?, reminder_time=?, start_date=?, end_date=?, notes=?
                WHERE id=? AND user_id=?
            ''', (request.form.get('medicine_name', ''),
                  request.form.get('dosage', ''),
                  request.form.get('medicine_type', ''),
                  request.form.get('food_timing', ''),
                  reminder_time,
                  request.form.get('start_date', ''),
                  request.form.get('end_date', ''),
                  request.form.get('notes', ''),
                  med_id, user_id))
            conn.commit()
            flash('Medicine updated successfully!')

        elif action == 'delete':
            med_id = request.form.get('med_id')
            cursor.execute('DELETE FROM medicines WHERE id=? AND user_id=?', (med_id, user_id))
            conn.commit()
            flash('Medicine deleted.')

        conn.close()
        return redirect(url_for('medicine'))

    edit_id  = request.args.get('edit_id')
    edit_med = None
    if edit_id:
        cursor.execute('SELECT * FROM medicines WHERE id=? AND user_id=?', (edit_id, user_id))
        edit_med = cursor.fetchone()

    cursor.execute('SELECT * FROM medicines WHERE user_id=? ORDER BY id DESC', (user_id,))
    all_medicines = cursor.fetchall()
    conn.close()
    # convert reminder_time to AM/PM for display
    med_times = {}
    for med in all_medicines:
        h, m, ap = time24_to_ampm(med['reminder_time'] or '08:00')
        med_times[med['id']] = f"{h}:{m} {ap}"
    edit_med_time = None
    if edit_med:
        h, m, ap = time24_to_ampm(edit_med['reminder_time'] or '08:00')
        edit_med_time = {'h': h, 'm': m, 'ap': ap}
    return render_template('medicine.html',
                           all_medicines=all_medicines,
                           med_times=med_times,
                           edit_med=edit_med,
                           edit_med_time=edit_med_time,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# WATER REMINDER
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/water', methods=['GET', 'POST'])
@login_required
def water():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()

    if request.method == 'POST':
        daily_goal      = request.form.get('daily_goal', '2')
        goal_unit       = request.form.get('goal_unit', 'Litres')
        frequency_hours = request.form.get('frequency_hours', '2')
        start_time      = ampm_to_24(request.form.get('start_hour','8'),
                                     request.form.get('start_min','00'),
                                     request.form.get('start_ampm','AM'))
        end_time        = ampm_to_24(request.form.get('end_hour','8'),
                                     request.form.get('end_min','00'),
                                     request.form.get('end_ampm','PM'))

        cursor.execute('SELECT id FROM water_reminders WHERE user_id=?', (user_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute('''
                UPDATE water_reminders SET daily_goal=?, goal_unit=?,
                frequency_hours=?, start_time=?, end_time=? WHERE user_id=?
            ''', (daily_goal, goal_unit, frequency_hours, start_time, end_time, user_id))
            flash('Water reminder updated!')
        else:
            cursor.execute('''
                INSERT INTO water_reminders (user_id, daily_goal, goal_unit, frequency_hours, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, daily_goal, goal_unit, frequency_hours, start_time, end_time))
            flash('Water reminder saved!')

        conn.commit()
        conn.close()
        return redirect(url_for('water'))

    cursor.execute('SELECT * FROM water_reminders WHERE user_id=?', (user_id,))
    water_setting = cursor.fetchone()
    conn.close()
    # parse stored times for AM/PM display
    if water_setting:
        sh, sm, sa = time24_to_ampm(water_setting['start_time'] or '08:00')
        eh, em, ea = time24_to_ampm(water_setting['end_time']   or '20:00')
    else:
        sh,sm,sa = '8','00','AM'
        eh,em,ea = '8','00','PM'
    return render_template('water.html',
                           water_setting=water_setting,
                           sh=sh, sm=sm, sa=sa,
                           eh=eh, em=em, ea=ea,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# EXERCISE REMINDER
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/exercise', methods=['GET', 'POST'])
@login_required
def exercise():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            ex_reminder_time = ampm_to_24(request.form.get('reminder_hour','6'),
                                          request.form.get('reminder_min','00'),
                                          request.form.get('reminder_ampm','AM'))
            cursor.execute('''
                INSERT INTO exercise_reminders (user_id, exercise_type, reminder_time, duration_min, frequency)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id,
                  request.form.get('exercise_type', ''),
                  ex_reminder_time,
                  request.form.get('duration_min', ''),
                  request.form.get('frequency', '')))
            conn.commit()
            flash('Exercise reminder added!')

        elif action == 'delete':
            ex_id = request.form.get('ex_id')
            cursor.execute('DELETE FROM exercise_reminders WHERE id=? AND user_id=?', (ex_id, user_id))
            conn.commit()
            flash('Exercise reminder deleted.')

        conn.close()
        return redirect(url_for('exercise'))

    cursor.execute('SELECT * FROM exercise_reminders WHERE user_id=? ORDER BY id DESC', (user_id,))
    all_exercises = cursor.fetchall()
    conn.close()
    ex_times = {}
    for ex in all_exercises:
        h, m, ap = time24_to_ampm(ex['reminder_time'] or '06:00')
        ex_times[ex['id']] = f"{h}:{m} {ap}"
    return render_template('exercise.html',
                           all_exercises=all_exercises,
                           ex_times=ex_times,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# DOCTOR APPOINTMENT
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/appointment', methods=['GET', 'POST'])
@login_required
def appointment():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()

    if request.method == 'POST':
        action = request.form.get('action', 'add')

        if action == 'add':
            appt_time = ampm_to_24(request.form.get('appt_hour','10'),
                                   request.form.get('appt_min','00'),
                                   request.form.get('appt_ampm','AM'))
            cursor.execute('''
                INSERT INTO doctor_appointments (user_id, doctor_name, appointment_date, appointment_time, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id,
                  request.form.get('doctor_name', ''),
                  request.form.get('appointment_date', ''),
                  appt_time,
                  request.form.get('notes', '')))
            conn.commit()
            flash('Appointment saved!')

        elif action == 'delete':
            appt_id = request.form.get('appt_id')
            cursor.execute('DELETE FROM doctor_appointments WHERE id=? AND user_id=?', (appt_id, user_id))
            conn.commit()
            flash('Appointment deleted.')

        elif action == 'complete':
            appt_id = request.form.get('appt_id')
            cursor.execute('''
                UPDATE doctor_appointments SET status='Completed' WHERE id=? AND user_id=?
            ''', (appt_id, user_id))
            conn.commit()
            flash('Appointment marked as Completed.')

        conn.close()
        return redirect(url_for('appointment'))

    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT * FROM doctor_appointments WHERE user_id=?
        ORDER BY appointment_date DESC, appointment_time DESC
    ''', (user_id,))
    all_appointments = cursor.fetchall()
    conn.close()
    return render_template('appointment.html',
                           all_appointments=all_appointments,
                           today=today,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    generate_notifications(user_id)
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM notifications WHERE user_id=?
        ORDER BY
            CASE status WHEN 'Pending' THEN 1 WHEN 'Snoozed' THEN 2 ELSE 3 END,
            scheduled_time
    ''', (user_id,))
    all_notifs = cursor.fetchall()
    conn.close()
    return render_template('notifications.html',
                           all_notifs=all_notifs,
                           user_name=session.get('user_name', ''),
                           now=datetime.now().strftime('%Y-%m-%d %H:%M'))


@app.route('/notification_action', methods=['POST'])
@login_required
def notification_action():
    user_id  = session['user_id']
    notif_id = request.form.get('notif_id')
    action   = request.form.get('action')

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM notifications WHERE id=? AND user_id=?', (notif_id, user_id))
    notif = cursor.fetchone()

    if notif:
        if action == 'taken':
            cursor.execute("UPDATE notifications SET status='Taken' WHERE id=?", (notif_id,))
            status = 'Taken'
        elif action == 'snooze':
            snooze_time = (datetime.now() + timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M')
            cursor.execute('''
                UPDATE notifications SET status='Snoozed', snoozed_until=? WHERE id=?
            ''', (snooze_time, notif_id))
            status = 'Snoozed'
        elif action == 'skip':
            cursor.execute("UPDATE notifications SET status='Skipped' WHERE id=?", (notif_id,))
            status = 'Skipped'
        else:
            status = notif['status']

        cursor.execute('''
            INSERT INTO reminder_history (user_id, reminder_name, reminder_type, date, scheduled_time, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id,
              notif['message'],
              notif['reminder_type'],
              notif['scheduled_time'][:10] if notif['scheduled_time'] else '',
              notif['scheduled_time'],
              status))
        conn.commit()
        flash(f'Reminder marked as {status}.')

    conn.close()
    return redirect(url_for('notifications'))


# ─────────────────────────────────────────────────────────────────────────────
# REMINDER HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/history')
@login_required
def history():
    user_id = session['user_id']
    conn    = get_connection()
    cursor  = conn.cursor()
    cursor.execute('''
        SELECT * FROM reminder_history WHERE user_id=? ORDER BY logged_at DESC
    ''', (user_id,))
    all_history = cursor.fetchall()
    conn.close()
    return render_template('history.html',
                           all_history=all_history,
                           user_name=session.get('user_name', ''))


# ─────────────────────────────────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    start_reminder_thread()
    app.run(debug=True, host='0.0.0.0', port=5000)
