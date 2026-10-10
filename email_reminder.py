import smtplib
import sqlite3
import os
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ─── EMAIL CONFIGURATION ─────────────────────────────────────────────────────
# Credentials stored safely in environment variables
SENDER_EMAIL    = os.environ.get('SENDER_EMAIL', 'harshugharat15@gmail.com')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', '')
SENDER_NAME     = "Early Care"

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'earlycare.db')

# ─── DATABASE CONNECTION ──────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── SEND EMAIL ───────────────────────────────────────────────────────────────
def send_email(to_email, subject, body_html):
    """Send an HTML email using Gmail SMTP."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg['To']      = to_email

        part = MIMEText(body_html, 'html')
        msg.attach(part)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

        print(f"[Early Care] Email sent to {to_email} | Subject: {subject}")
        return True

    except Exception as e:
        print(f"[Early Care] Email error: {e}")
        return False

# ─── EMAIL BODY BUILDER ───────────────────────────────────────────────────────
def build_email(user_name, reminder_type, message, scheduled_time):
    """Build a beautiful HTML email body."""

    # Pick colour and icon per type
    colors = {
        'Medicine': ('#e91e63', '#fce4ec', '💊'),
        'Water':    ('#1976d2', '#e3f2fd', '💧'),
        'Exercise': ('#388e3c', '#e8f5e9', '🏃'),
        'Doctor':   ('#f57c00', '#fff3e0', '🩺'),
    }
    color, bg, icon = colors.get(reminder_type, ('#00897b', '#e0f2f1', '🔔'))

    html = f"""
    <html>
    <body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:30px 0;">
        <tr><td align="center">
          <table width="560" cellpadding="0" cellspacing="0"
                 style="background:white;border-radius:16px;
                        box-shadow:0 4px 20px rgba(0,0,0,0.1);overflow:hidden;">

            <!-- HEADER -->
            <tr>
              <td style="background:linear-gradient(135deg,{color},{color}cc);
                         padding:28px 30px;text-align:center;">
                <div style="font-size:48px;margin-bottom:8px;">{icon}</div>
                <h1 style="color:white;margin:0;font-size:24px;letter-spacing:2px;">
                  EARLY CARE
                </h1>
                <p style="color:rgba(255,255,255,0.9);margin:6px 0 0 0;font-size:13px;">
                  Healthcare Reminder System
                </p>
              </td>
            </tr>

            <!-- BODY -->
            <tr>
              <td style="padding:28px 30px;">
                <p style="color:#333;font-size:15px;margin:0 0 16px 0;">
                  Dear <b>{user_name}</b>,
                </p>

                <div style="background:{bg};border-radius:12px;padding:20px 22px;
                            border-left:5px solid {color};margin-bottom:20px;">
                  <p style="color:#333;font-size:15px;font-weight:bold;margin:0 0 8px 0;">
                    {icon} {reminder_type} Reminder
                  </p>
                  <p style="color:#555;font-size:14px;margin:0 0 10px 0;line-height:1.6;">
                    {message}
                  </p>
                  <p style="color:#888;font-size:13px;margin:0;">
                    ⏰ Scheduled Time: <b style="color:{color};">{scheduled_time}</b>
                  </p>
                </div>

                <p style="color:#666;font-size:13px;line-height:1.7;margin:0 0 20px 0;">
                  Please open the Early Care app and take the required action:<br>
                  <b style="color:#388e3c;">✓ Mark as Taken</b> &nbsp;|&nbsp;
                  <b style="color:#f57c00;">⏰ Snooze</b> &nbsp;|&nbsp;
                  <b style="color:#e53935;">✗ Skip</b>
                </p>

                <div style="background:#fff8e1;border:1px solid #ffc107;border-radius:10px;
                            padding:12px 16px;font-size:12px;color:#6d4c00;">
                  ⚠️ <b>Note:</b> This is a general health reminder only.
                  It is NOT a medical diagnosis. Please consult a doctor for medical advice.
                </div>
              </td>
            </tr>

            <!-- FOOTER -->
            <tr>
              <td style="background:#f9f9f9;padding:16px 30px;text-align:center;
                         border-top:1px solid #eee;">
                <p style="color:#aaa;font-size:11px;margin:0;">
                  ❤️ Early Care &mdash; Your Health, Your Reminder<br>
                  This email was sent automatically. Do not reply to this email.
                </p>
              </td>
            </tr>

          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """
    return html

# ─── CHECK AND SEND DUE REMINDERS ─────────────────────────────────────────────
def check_and_send_reminders():
    """Check for due reminders and send emails."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now()
    now_str      = now.strftime('%Y-%m-%d %H:%M')
    window_start = (now - timedelta(minutes=2)).strftime('%Y-%m-%d %H:%M')

    # Get all pending notifications whose time has come
    cursor.execute('''
        SELECT n.id, n.user_id, n.reminder_type, n.message, n.scheduled_time,
               u.full_name, u.email
        FROM notifications n
        JOIN users u ON n.user_id = u.id
        WHERE n.status = 'Pending'
          AND n.scheduled_time >= ?
          AND n.scheduled_time <= ?
          AND (n.email_sent IS NULL OR n.email_sent = 0)
    ''', (window_start, now_str))

    due = cursor.fetchall()

    for notif in due:
        user_name  = notif['full_name']
        to_email   = notif['email']
        rtype      = notif['reminder_type']
        message    = notif['message']
        sched_time = notif['scheduled_time']
        notif_id   = notif['id']

        subject = f"Early Care Reminder — {message[:50]}"
        body    = build_email(user_name, rtype, message, sched_time)

        success = send_email(to_email, subject, body)

        if success:
            # Mark email as sent so we don't send it again
            cursor.execute('''
                UPDATE notifications SET email_sent=1 WHERE id=?
            ''', (notif_id,))

    conn.commit()
    conn.close()

# ─── ADD email_sent COLUMN IF NOT EXISTS ─────────────────────────────────────
def ensure_email_sent_column():
    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE notifications ADD COLUMN email_sent INTEGER DEFAULT 0')
        conn.commit()
        print("[Early Care] Added email_sent column to notifications table.")
    except Exception:
        pass  # Column already exists
    conn.close()

# ─── BACKGROUND THREAD ────────────────────────────────────────────────────────
def start_reminder_thread():
    """Run the reminder checker every 60 seconds in background."""
    ensure_email_sent_column()

    def run():
        print("[Early Care] Email reminder service started. Checking every 60 seconds.")
        while True:
            try:
                check_and_send_reminders()
            except Exception as e:
                print(f"[Early Care] Reminder check error: {e}")
            time.sleep(60)

    t = threading.Thread(target=run, daemon=True)
    t.start()

if __name__ == '__main__':
    print("Testing email...")
    send_email(
        SENDER_EMAIL,
        "Early Care — Test Email",
        build_email("Test User", "Medicine", "Time to take Paracetamol 500mg!", "Now")
    )
