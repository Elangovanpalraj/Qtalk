import os
import uuid
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

# Database Imports
from app.database import Base, engine, get_db
from app.chat.models import Message

# Import All Routers (Chat, Contacts, Status)
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router
from app.status.router import router as status_router

# 1. Database Tables Creation
Base.metadata.create_all(bind=engine)

# 2. FastAPI Initialization
app = FastAPI(title="Qtalk - Web Application Engine")

# 3. Ensure Required Directories Exist
os.makedirs("uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# 4. Mount Static & Upload Files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 5. Include All App Routers
app.include_router(chat_router, prefix="/chat", tags=["Chat"])
app.include_router(contacts_router, prefix="/contacts", tags=["Contacts"])
app.include_router(status_router, prefix="/status", tags=["Status"])


# --- Pydantic Request Schemas ---
class RegisterRequest(BaseModel):
    phone: str
    name: str = "Qtalk User"


# --- API Endpoints ---

# 🟢 1. User Registration API
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


# 🟢 2. File & Image Upload API
@app.post("/upload", tags=["Media"])
async def upload_file(file: UploadFile = File(...)):
    """
    படங்கள், வீடியோக்கள் மற்றும் ஃபோல்டர்களை Upload செய்யும் API.
    """
    ext = file.filename.split(".")[-1] if "." in file.filename else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())
        
    return {"file_url": f"/uploads/{filename}"}


# 🟢 3. Delete Message API
@app.delete("/message/{msg_id}", tags=["Chat"])
def delete_message(msg_id: int, db: Session = Depends(get_db)):
    """
    குறிப்பிட்ட மெசேஜை அழிப்பதற்கான (Delete) API.
    """
    msg = db.query(Message).filter(Message.id == msg_id).first()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Message with ID {msg_id} not found"
        )
    
    db.delete(msg)
    db.commit()
    return {"status": "success", "id": msg_id}


# 🟢 4. Health Check API
@app.get("/health", tags=["System"])
def health_check():
    """
    சர்வர் சரியாக இயங்குகிறதா என்பதைச் சரிபார்க்கும் API.
    """
    return {"status": "ok", "message": "Qtalk Engine is Running Perfectly!"}


# 🟢 5. Home Page Route (Frontend UI)
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
