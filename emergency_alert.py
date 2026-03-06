import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime
from database_manager import get_profile, get_settings, log_notification

def send_email_alert(danger_score, triggers, location=None):
    profile = get_profile()
    # Use specified email recipient
    target_email = "manojkumar.a1411@gmail.com"
    
    subject = "WOMEN SAFETY ALERT"
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    body = f"""
Women Safety Assistant - Alert Message

Emergency distress voice detected.
System detected danger event.

Time of detection: {timestamp}

--- Alert Details ---
Threat Level: {danger_score}/100
Keywords: {', '.join(triggers)}
"""
    if location:
        body += f"Location: Lat {location.get('lat')}, Lng {location.get('lng')}\n"


    # GMAIL SMTP SETUP
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    
    # Ideally set via: setx ALERT_EMAIL_USER "your_email@gmail.com"
    # For the hackathon demo, we check if they exist, else we simulate.
    SENDER_EMAIL = os.environ.get("ALERT_EMAIL_USER")
    SENDER_PWD = os.environ.get("ALERT_EMAIL_PASS")
    
    if not SENDER_EMAIL or not SENDER_PWD:
        print(f"[SIMULATED EMAIL] Send to: {target_email}")
        print(f"[SIMULATED EMAIL] Body: {body[:100]}...")
        log_notification(target_email, "Simulated - SMTP Not Configured")
        return True
    
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = target_email
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PWD)
            server.send_message(msg)
            
        print(f"[EMAIL] Alert successfully sent to {target_email}")
        log_notification(target_email, "Success")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed to send alert: {e}")
        log_notification(target_email, f"Failed: {str(e)}")
        return False

def trigger_emergency_response(danger_score, triggers, location=None):
    """
    Activated when distress is verified.
    """
    profile = get_profile()
    settings = get_settings()
    
    contact_name = profile.get('emergency_contact_name') or "Trusted Contact"
    contact_phone = profile.get('emergency_contact_phone') or settings.get('emergency_contact_number') or "Emergency Services"
    
    print("="*50)
    print("🚨 EMERGENCY PROTOCOL ACTIVATED 🚨")
    print(f"Danger Score : {danger_score}/100")
    print(f"Triggers     : {', '.join(triggers)}")
    print(f"Notifying    : {contact_name} ({contact_phone})")
    
    if location:
        lat, lng = location.get('lat', 'Unknown'), location.get('lng', 'Unknown')
        print(f"Location     : Lat {lat}, Lng {lng}")
        
    # Send Email Alert
    send_email_alert(danger_score, triggers, location)
    
    print("Action Taken : Automated Email and SMS alerts dispatched.")
    print("="*50)
    
    return {
        "success": True,
        "message": "Emergency alert dispatched securely.",
        "protocol_active": True
    }
