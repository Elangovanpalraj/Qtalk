import firebase_admin
from firebase_admin import credentials, messaging

# Firebase initialization (ungalathu firebase json file path-ai podungal)
# cred = credentials.Certificate("app/firebase_creds.json")
# firebase_admin.initialize_app(cred)

def send_push_notification(token: str, title: str, body: str, data_payload: dict = None):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data_payload or {},
            token=token,
        )
        response = messaging.send(message)
        return {"success": True, "message_id": response}
    except Exception as e:
        return {"success": False, "error": str(e)}
