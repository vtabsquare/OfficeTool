from flask import Flask, jsonify, request, session, current_app
from flask_mail import Mail, Message
import os
import traceback
from dotenv import load_dotenv

# Load env for local dev
if os.path.exists("id.env"):
    load_dotenv("id.env")
load_dotenv()

# Standalone app for backward compatibility (not used when imported)
app = Flask(__name__)
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME'])
mail = Mail(app)

print("DEBUG: MAIL_USERNAME =", os.getenv("MAIL_USERNAME"))
print("DEBUG: MAIL_DEFAULT_SENDER =", os.getenv("MAIL_DEFAULT_SENDER"))


# ------------------------------
# ✉️ Email Send Function
# ------------------------------
def send_email(subject, recipients, body, html=None, cc=None, attachments=None):
    """
    Send email using Flask-Mail.
    Uses the calling app's context if available, otherwise falls back to standalone app.
    """
    print(f"[MAIL] send_email called: to={recipients}, subject={subject}", flush=True)
    
    # Determine which app/mail instance to use
    try:
        # If called from within a Flask request context, use that app's mail
        flask_app = current_app._get_current_object()
        mail_instance = flask_app.extensions.get('mail')
        if not mail_instance:
            print("[MAIL] No mail extension on current_app, using standalone", flush=True)
            flask_app = app
            mail_instance = mail
    except RuntimeError:
        # No app context, use standalone
        print("[MAIL] No app context, using standalone app", flush=True)
        flask_app = app
        mail_instance = mail

    try:
        with flask_app.app_context():
            print(f"[MAIL] Using MAIL_SERVER={flask_app.config.get('MAIL_SERVER')}", flush=True)
            print(f"[MAIL] Using MAIL_USERNAME={flask_app.config.get('MAIL_USERNAME')}", flush=True)
            
            msg = Message(subject=subject, recipients=recipients, cc=cc, body=body, html=html)

            # Add attachments if provided
            if attachments:
                for filename, file_data in attachments:
                    msg.attach(
                        filename=filename,
                        content_type='application/pdf',
                        data=file_data
                    )
                    print(f"[MAIL] Attached: {filename}", flush=True)

            print("[MAIL] Calling mail.send()...", flush=True)
            mail_instance.send(msg)
            print(f"[MAIL] Email sent successfully -> {recipients}", flush=True)
            return True
    except Exception as e:
        print(f"[MAIL] Failed to send email to {recipients}: {e}", flush=True)
        traceback.print_exc()
        return False
    
    
