"""
sender.py — Gmail Email Sender
Sends personalized application emails with CV attached.
"""

import os
import smtplib
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders


def send_email(to_address, subject, body, cv_path, sender_email, sender_password, candidate_name=""):
    """
    Send a job application email with CV attached.

    Args:
        to_address (str): Recipient email
        subject (str): Email subject
        body (str): Email body text
        cv_path (str): Path to CV PDF file
        sender_email (str): Your Gmail address
        sender_password (str): Gmail App Password (not your login password!)
        candidate_name (str): Your name for the From field

    Returns:
        bool: True if sent successfully, False otherwise
    """
    try:
        # Build email
        msg = MIMEMultipart()
        msg["From"] = f"{candidate_name} <{sender_email}>" if candidate_name else sender_email
        msg["To"] = to_address
        msg["Subject"] = subject

        # Body
        msg.attach(MIMEText(body, "plain"))

        # Attach CV
        if cv_path and os.path.exists(cv_path):
            with open(cv_path, "rb") as f:
                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            cv_filename = f"{candidate_name.replace(' ', '_')}_CV.pdf" if candidate_name else "Resume_CV.pdf"
            attachment.add_header("Content-Disposition", f'attachment; filename="{cv_filename}"')
            msg.attach(attachment)
            print(f"[sender] CV attached: {cv_filename}")
        else:
            print(f"[sender] Warning: CV file not found at {cv_path}")

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_address, msg.as_string())

        print(f"[sender] ✅ Email sent to {to_address}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[sender] ❌ Gmail authentication failed.")
        print("   → Make sure you're using an App Password, not your Gmail password.")
        print("   → How to get App Password: Google Account → Security → 2-Step Verification → App Passwords")
        return False

    except smtplib.SMTPException as e:
        print(f"[sender] ❌ SMTP error: {e}")
        return False

    except Exception as e:
        print(f"[sender] ❌ Unexpected error: {e}")
        return False


def send_with_delay(to_address, subject, body, cv_path, sender_email, sender_password, candidate_name=""):
    """
    Send email with a human-like delay to avoid spam flags.
    Use this in loops instead of send_email directly.
    """
    delay = random.uniform(30, 90)  # 30 to 90 seconds between emails
    print(f"[sender] Waiting {delay:.0f}s before sending (anti-spam delay)...")
    time.sleep(delay)
    return send_email(to_address, subject, body, cv_path, sender_email, sender_password, candidate_name)


def send_batch(email_tasks, sender_email, sender_password, candidate_name="", max_per_session=10):
    """
    Send multiple emails safely with delays.

    Args:
        email_tasks (list): List of dicts: { to, subject, body, cv_path }
        max_per_session (int): Safety limit per run

    Returns:
        list: Results [{ to, success, error }]
    """
    results = []
    sent_count = 0

    for task in email_tasks:
        if sent_count >= max_per_session:
            print(f"[sender] ⚠️ Reached daily limit of {max_per_session} emails. Stopping.")
            break

        success = send_with_delay(
            to_address=task["to"],
            subject=task["subject"],
            body=task["body"],
            cv_path=task.get("cv_path", ""),
            sender_email=sender_email,
            sender_password=sender_password,
            candidate_name=candidate_name
        )

        results.append({"to": task["to"], "success": success})
        if success:
            sent_count += 1

    print(f"[sender] Session complete: {sent_count}/{len(email_tasks)} emails sent.")
    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Test with a single email to yourself first!
    test_result = send_email(
        to_address=os.getenv("GMAIL_ADDRESS"),  # Send to yourself for testing
        subject="TEST - LinkedIn Bot Email",
        body="This is a test email from your LinkedIn AutoApply Bot. If you received this, the setup is working!",
        cv_path="cvs/general.pdf",
        sender_email=os.getenv("GMAIL_ADDRESS"),
        sender_password=os.getenv("GMAIL_APP_PASSWORD"),
        candidate_name=os.getenv("YOUR_NAME", "Test")
    )

    print("Test result:", "✅ SUCCESS" if test_result else "❌ FAILED")
