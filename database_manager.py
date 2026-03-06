import sqlite3
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'database')
DB_FILE = os.path.join(DB_DIR, 'app.db')

def get_db_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # User Profile (Singleton for local app but structured for scale)
    c.execute('''CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY DEFAULT 1,
        name TEXT, phone TEXT, email TEXT,
        emergency_contact_email TEXT, emergency_contact_name TEXT, emergency_contact_phone TEXT,
        medical_info TEXT, password_hash TEXT
    )''')
    
    # Settings (Key-Value)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        keywords TEXT, secret_phrases TEXT, sensitivity TEXT, emergency_contact_number TEXT
    )''')
    
    # Analytics Counters
    c.execute('''CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        voice_inputs INTEGER DEFAULT 0, 
        distress_alerts INTEGER DEFAULT 0,
        normal_interactions INTEGER DEFAULT 0, 
        total_interactions INTEGER DEFAULT 0,
        last_alert_time TEXT
    )''')
    
    # Notification Logs (For Email alerts)
    c.execute('''CREATE TABLE IF NOT EXISTS notification_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contact_email TEXT, status TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Location History
    c.execute('''CREATE TABLE IF NOT EXISTS location_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lat REAL, lng REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Incident Reports
    c.execute('''CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT, description TEXT, category TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Alert Logs (Tracking SOS history)
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_type TEXT, triggers TEXT, danger_score INTEGER, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Initialize singletons if empty
    c.execute('SELECT COUNT(*) FROM profile')
    if c.fetchone()[0] == 0:
        default_pwd = generate_password_hash('default123') # Basic protection
        c.execute('INSERT INTO profile (id, password_hash) VALUES (1, ?)', (default_pwd,))
        
    c.execute('SELECT COUNT(*) FROM settings')
    if c.fetchone()[0] == 0:
        keywords = ["help", "help me", "danger", "emergency", "save me", "i am in danger", "please help", "call police", "someone is following me", "attack"]
        c.execute('INSERT INTO settings (id, keywords, secret_phrases, sensitivity) VALUES (1, ?, ?, ?)',
            (json.dumps(keywords),
             json.dumps(["where is my red file", "call my sister"]), "medium"))
             
    c.execute('SELECT COUNT(*) FROM analytics')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO analytics (id) VALUES (1)')
    
    # Force sync default keywords to ensure "Step 4" works
    ensure_keywords_synced(c)
        
    conn.commit()
    conn.close()

def ensure_keywords_synced(cursor):
    """Guarantees the latest distress keywords are in the DB."""
    keywords = ["help", "help me", "danger", "emergency", "save me", "i am in danger", "please help", "call police", "someone is following me", "attack"]
    cursor.execute('UPDATE settings SET keywords = ? WHERE id = 1', (json.dumps(keywords),))

# Run init on start
init_db()

# --- Settings ---
def get_settings():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM settings WHERE id = 1').fetchone()
    conn.close()
    if not row: return {}
    return {
        "keywords": json.loads(row['keywords'] or '[]'),
        "secret_phrases": json.loads(row['secret_phrases'] or '[]'),
        "sensitivity": row['sensitivity'] or "medium",
        "emergency_contact_number": row['emergency_contact_number'] or ""
    }

def update_settings(new_settings):
    current = get_settings()
    current.update(new_settings)
    conn = get_db_connection()
    conn.execute('''UPDATE settings SET 
        keywords = ?, secret_phrases = ?, sensitivity = ?, emergency_contact_number = ? 
        WHERE id = 1''',
        (json.dumps(current['keywords']), json.dumps(current['secret_phrases']), 
         current['sensitivity'], current.get('emergency_contact_number', ''))
    )
    conn.commit()
    conn.close()

# --- Profile ---
def get_profile():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM profile WHERE id = 1').fetchone()
    conn.close()
    if not row: return {}
    return dict(row) # Converts sqlite3.Row to dict

def update_profile(new_profile):
    current = get_profile()
    
    # Handle password hashing if provided
    new_pwd = new_profile.get('password')
    if new_pwd:
        new_profile['password_hash'] = generate_password_hash(new_pwd)
        
    current.update(new_profile)
    
    conn = get_db_connection()
    conn.execute('''UPDATE profile SET 
        name = ?, phone = ?, email = ?, emergency_contact_email = ?, 
        emergency_contact_name = ?, emergency_contact_phone = ?, 
        medical_info = ?, password_hash = ?
        WHERE id = 1''',
        (current.get('name', ''), current.get('phone', ''), current.get('email', ''),
         current.get('emergency_contact_email', ''), current.get('emergency_contact_name', ''),
         current.get('emergency_contact_phone', ''), current.get('medical_info', ''),
         current.get('password_hash', ''))
    )
    conn.commit()
    conn.close()

# --- Analytics ---
def get_analytics():
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM analytics WHERE id = 1').fetchone()
    conn.close()
    
    # We also inject the total actual SOS alerts by querying the alerts table
    stats = dict(row) if row else {}
    
    conn = get_db_connection()
    total_alerts = conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
    total_incidents = conn.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]
    stats['total_db_alerts'] = total_alerts
    stats['total_incidents'] = total_incidents
    conn.close()
    
    return stats

def log_analytic(event_type):
    valid_cols = ['voice_inputs', 'distress_alerts', 'normal_interactions', 'total_interactions']
    if event_type in valid_cols:
        conn = get_db_connection()
        conn.execute(f'UPDATE analytics SET {event_type} = {event_type} + 1 WHERE id = 1')
        if event_type == 'distress_alerts':
            conn.execute('UPDATE analytics SET last_alert_time = ? WHERE id = 1', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit()
        conn.close()
        
def reset_analytics():
    conn = get_db_connection()
    conn.execute('UPDATE analytics SET voice_inputs = 0, distress_alerts = 0, normal_interactions = 0, total_interactions = 0, last_alert_time = NULL WHERE id = 1')
    conn.execute('DELETE FROM alerts')
    conn.execute('DELETE FROM incidents')
    conn.execute('DELETE FROM location_history')
    conn.execute('DELETE FROM notification_logs')
    conn.commit()
    conn.close()

# --- Extended SOS & Incident Logic ---
def log_alert(alert_type, triggers, danger_score):
    conn = get_db_connection()
    conn.execute('INSERT INTO alerts (alert_type, triggers, danger_score) VALUES (?, ?, ?)',
                 (alert_type, triggers, danger_score))
    conn.commit()
    conn.close()
    
def log_location(lat, lng):
    if lat is None or lng is None: return
    conn = get_db_connection()
    conn.execute('INSERT INTO location_history (lat, lng) VALUES (?, ?)', (lat, lng))
    conn.commit()
    conn.close()

def log_incident(location, description, category):
    conn = get_db_connection()
    conn.execute('INSERT INTO incidents (location, description, category) VALUES (?, ?, ?)',
                 (location, description, category))
    conn.commit()
    conn.close()

def log_notification(email, status):
    conn = get_db_connection()
    conn.execute('INSERT INTO notification_logs (contact_email, status) VALUES (?, ?)', (email, status))
    conn.commit()
    conn.close()

def get_incidents():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM incidents ORDER BY timestamp DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_notification_logs():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM notification_logs ORDER BY timestamp DESC LIMIT 10').fetchall()
    conn.close()
    return [dict(r) for r in rows]
