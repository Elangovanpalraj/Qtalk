import os
import uuid
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Database Base & Session Setup
from app.database import Base, engine, get_db

# Import Models (SQLAlchemy Tables உருவாக்க அனைத்து மாடல்களும் தேவை)
from app.chat.models import Message, Group, GroupMember, MessageReaction
from app.status.models import Status, StatusView

# Import App Routers
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router
from app.status.router import router as status_router


# 🟢 1. DATABASE TABLES CREATION
# அனைத்து மாடல்களுக்கான அட்டவணைகளையும் தானாக உருவாக்கும்
Base.metadata.create_all(bind=engine)


# 🟢 2. FASTAPI APP INITIALIZATION
app = FastAPI(
    title="Qtalk - Web Application Engine",
    description="Real-time Chat, Group Messaging, Status Stories, and Media Engine",
    version="1.0.0"
)


# 🟢 3. ENSURE REQUIRED DIRECTORIES EXIST
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)


# 🟢 4. MOUNT STATIC & UPLOAD FILES
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# 🟢 5. INCLUDE ALL APP ROUTERS
# (குறிப்பு: Routers-க்குள் ஏற்கனவே Prefixes வரையறுக்கப்பட்டுள்ளதால் இங்கு கூடுதல் prefix தவிர்க்கப்பட்டுள்ளது)
app.include_router(chat_router)
app.include_router(contacts_router)
app.include_router(status_router)


# ------------------------------------------------------------------
# 🟢 6. PYDANTIC SCHEMAS (Request Validation)
# ------------------------------------------------------------------
class RegisterRequest(BaseModel):
    phone: str
    name: str = "Qtalk User"


# ------------------------------------------------------------------
# 🟢 7. SYSTEM & MEDIA ENDPOINTS
# ------------------------------------------------------------------

# A. User Registration / Auth Mock Endpoint
@app.post("/register", tags=["Auth"])
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    """
    பயனர் OTP சரிபார்த்து லாகின் செய்யும்போது,
    அவர் போன் நம்பரை சிஸ்டமில் Register செய்யும் Route.
    """
    return {
        "status": "success",
        "message": f"User {data.phone} ({data.name}) registered on Qtalk successfully"
    }


# B. File & Media Upload API
@app.post("/upload", tags=["Media"])
async def upload_file(file: UploadFile = File(...)):
    """
    படங்கள், வீடியோக்கள் மற்றும் ஆவணங்களை Upload செய்யும் API.
    """
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", filename)

    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())

    return {
        "success": True,
        "filename": file.filename,
        "file_url": f"/uploads/{filename}"
    }


# C. System Health Check API
@app.get("/health", tags=["System"])
def health_check():
    """
    சர்வர் சரியாக இயங்குகிறதா என்பதைச் சரிபார்க்கும் API.
    """
    return {
        "status": "ok",
        "app_name": "Qtalk Engine",
        "message": "Qtalk Backend Engine is Running Perfectly!"
    }


# D. Home Page Route (Frontend UI)
@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def get_app():
    """
    Qtalk வெப் பயன்பாட்டின் முகப்புப் பக்கத்தை (index.html) காட்டும் Route.
    """
    template_path = os.path.join("templates", "index.html")
    if not os.path.exists(template_path):
        return HTMLResponse(
            content="<h2>Qtalk Server is Running! (templates/index.html file not found)</h2>",
            status_code=200
        )

    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
