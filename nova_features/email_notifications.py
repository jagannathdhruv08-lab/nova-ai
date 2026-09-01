# ==========================================
# NOVA EMAIL NOTIFICATIONS — Send reminders/recap via SMTP
# ==========================================
import os
import json
import time
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".nova", "email_config.json")

# Quick provider templates
SMTP_PROVIDERS = {
    "gmail": {"host": "smtp.gmail.com", "port": 587},
    "outlook": {"host": "smtp-mail.outlook.com", "port": 587},
    "yahoo": {"host": "smtp.mail.yahoo.com", "port": 587},
    "custom": {"host": "", "port": 587},
}


def _load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_email_config(email, password, smtp_host, smtp_port=587, provider="custom"):
    """Save email SMTP config (stored in ~/.nova/email_config.json)."""
    config = {
        "email": email,
        "password": password,   # NOTE: For real use, prefer app-passwords/env vars
        "smtp_host": smtp_host,
        "smtp_port": int(smtp_port),
        "provider": provider,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    return {"success": True, "feature": "email_notifications",
            "message": f"✅ Email config saved for {email}"}


def send_email_notification(recipient, subject, body, sender=None):
    """Send an email notification to recipient."""
    config = _load_config()
    if not config.get("email") or not config.get("password"):
        return {"success": False, "feature": "email_notifications",
                "message": "⚠️ Email not configured. Use save_email_config() first. e.g. save_email_config('you@gmail.com', 'app_password', 'smtp.gmail.com', 587, 'gmail')"}

    sender_email = config.get("email")
    sender_pass = config.get("password")
    smtp_host = config.get("smtp_host")
    smtp_port = int(config.get("smtp_port", 587))

    try:
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls(context=context)
        server.login(sender_email, sender_pass)
        text = msg.as_string()
        server.sendmail(sender_email, recipient, text)
        server.quit()
        return {"success": True, "feature": "email_notifications",
                "to": recipient, "subject": subject,
                "message": f"📧 Sent to {recipient}: {subject}"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "feature": "email_notifications",
                "message": "❌ Auth failed. Check email/password/app-password."}
    except Exception as e:
        return {"success": False, "feature": "email_notifications",
                "message": f"❌ Email error: {str(e)}"}


def send_reminder_email(reminder_text, recipient, sender=None):
    """Convenience: send a reminder as an email."""
    subject = f"🔔 Nova Reminder — {time.strftime('%H:%M')}"
    body = f"Reminder:\n\n{reminder_text}\n\n— Sent via Nova AI Assistant"
    return send_email_notification(recipient, subject, body)


def get_email_status():
    """Check if email config is set up."""
    config = _load_config()
    if not config.get("email"):
        return {"success": True, "feature": "email_notifications",
                "configured": False,
                "message": "📭 Email not configured. Use save_email_config(email, password, host, port, provider) to set up."}
    return {"success": True, "feature": "email_notifications",
            "configured": True, "email": config["email"],
            "provider": config.get("provider"),
            "message": f"📧 Configured: {config['email']}"}


def get_smtp_providers():
    """List the built-in SMTP provider templates."""
    return {"success": True, "feature": "email_notifications",
            "providers": {k: v for k, v in SMTP_PROVIDERS.items()},
            "message": "🔧 Providers: " + ", ".join(SMTP_PROVIDERS.keys())}


__version__ = "1.0.0"
__all__ = ["save_email_config", "send_email_notification", "send_reminder_email",
           "get_email_status", "get_smtp_providers"]
