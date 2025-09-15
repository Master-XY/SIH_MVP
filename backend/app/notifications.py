# backend/app/notifications.py
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def send_sms_mock(to: str, body: str):
    logger.info(f"[MOCK SMS] to={to} body={body}")
    return {"status": "mock_sent", "channel": "sms", "to": to}

def send_telegram_mock(chat_id: str, body: str):
    logger.info(f"[MOCK TELEGRAM] chat_id={chat_id} body={body}")
    return {"status": "mock_sent", "channel": "telegram", "chat_id": chat_id}

def send_email_mock(to_email: str, subject: str, body: str):
    logger.info(f"[MOCK EMAIL] to={to_email} subject={subject} body={body}")
    return {"status": "mock_sent", "channel": "email", "to": to_email}

def send_notifications(alert_obj, channels: list, targets: dict):
    """
    channels: list like ['sms','telegram','email']
    targets: dict with keys 'sms','telegram','email'
    """
    body = f"Advisory: {alert_obj.type} — {alert_obj.message}"
    result = {}
    for ch in channels:
        if ch == "sms":
            to = targets.get("sms", os.environ.get("DEMO_SMS_TO", "+0000000000"))
            result["sms"] = send_sms_mock(to, body)
        elif ch == "telegram":
            chat_id = targets.get("telegram", os.environ.get("DEMO_TG_CHAT", "demo_chat"))
            result["telegram"] = send_telegram_mock(chat_id, body)
        elif ch == "email":
            mail = targets.get("email", os.environ.get("DEMO_EMAIL", "demo@example.com"))
            result["email"] = send_email_mock(mail, "Advisory", body)
    return result
