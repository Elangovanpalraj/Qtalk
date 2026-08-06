from fastapi import APIRouter

router = APIRouter(prefix="", tags=["Contacts"])

@router.get("/users")
def get_users():
    return [
        {"username": "priya", "phone": "9787609729"},
        {"username": "karthik", "phone": "9876543210"},
        {"username": "arun", "phone": "9123456789"}
    ]