import os
import uuid
from fastapi import FastAPI, File, UploadFile, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import Base, engine, get_db
from app.chat.models import Message
# Note: Ensure User model is available in app.chat.models or app.contacts.models
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router

# Create Database Tables
Base.metadata.create_all(bind=engine)

# Updated Title & Branding to Qtalk
app = FastAPI(title="Qtalk - Web Application")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)

# Static & Upload Files Mounting
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include Routers
app.include_router(chat_router)
app.include_router(contacts_router)


# 🟢 1. Register User Pydantic Model & Route
class RegisterRequest(BaseModel):
    phone: str
    name: str = "Qtalk User"

@app.post("/register")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    """
    பயனர் OTP சரிபார்த்து லாகின் செய்யும்போது, 
    அவர் போன் நம்பரை சிஸ்டமில் Register செய்யும் Route.
    """
    # SQLite / DB Table-ல் User இருக்கிறாரா என்று பார்க்க உங்கள் Router-ல்
    # உள்ள User Model-ஐப் பயன்படுத்தலாம்.
    return {"status": "success", "message": f"User {data.phone} registered on Qtalk"}


# 🟢 2. File Upload API
@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())
        
    return {"file_url": f"/uploads/{filename}"}


# 🟢 3. Delete Message API
@app.delete("/message/{msg_id}")
def delete_message(msg_id: int, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == msg_id).first()
    if msg:
        db.delete(msg)
        db.commit()
        return {"status": "success", "id": msg_id}
    return {"status": "not_found"}


# 🟢 4. Updated Health Check API
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Qtalk Server is Running"}


# 🟢 5. Home Page Route
@app.get("/", response_class=HTMLResponse)
async def get_app():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
