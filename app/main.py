import os
import uuid
from fastapi import FastAPI, File, UploadFile, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.chat.models import Message
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Quantum Connect - WhatsApp UI")

os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(chat_router)
app.include_router(contacts_router)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join("uploads", filename)
    
    with open(filepath, "wb") as buffer:
        buffer.write(await file.read())
        
    return {"file_url": f"/uploads/{filename}"}

@app.delete("/message/{msg_id}")
def delete_message(msg_id: int, db: Session = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == msg_id).first()
    if msg:
        db.delete(msg)
        db.commit()
        return {"status": "success", "id": msg_id}
    return {"status": "not_found"}

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "WhatsApp Clone Running"}

@app.get("/", response_class=HTMLResponse)
async def get_app():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())