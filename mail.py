import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


def send_email(to_email, subject, text_body, html_body=None):
    """
    Sends an email via SMTP using the credentials in config (from your
    .env file). If html_body is given, sends a proper multipart email
    (HTML version shown by clients that support it, text_body as the
    plain-text fallback for clients that don't).

    Returns True on success, False if SMTP isn't configured or sending
    failed — the caller decides what to do (e.g. fall back to a
    dev-mode on-screen link).
    """
    host = current_app.config.get("SMTP_HOST")
    port = current_app.config.get("SMTP_PORT")
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    from_email = current_app.config.get("SMTP_FROM_EMAIL")

    if not host or not username or not password:
        current_app.logger.warning(
            "Email not sent: SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD not set in .env"
        )
        return False

    if html_body:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
    else:
        msg = MIMEText(text_body)

    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to_email}: {e}")
        return False
