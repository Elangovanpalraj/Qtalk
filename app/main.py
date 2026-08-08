import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import Base, engine
from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.contacts.router import router as contacts_router
from app.status.router import router as status_router
from app.calls.router import router as calls_router
from app.media.router import router as media_router

# Create Database Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Qtalk")

# Absolute Paths Resolution
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOADS_DIR = BASE_DIR / "uploads"
TEMPLATES_DIR = BASE_DIR / "templates"

# Auto-create directories on boot to prevent missing folder errors
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Mount Static & Uploads Folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# Configure Jinja2 Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include Feature Routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(contacts_router, prefix="/api/contacts", tags=["Contacts"])
app.include_router(status_router, prefix="/api/status", tags=["Status"])
app.include_router(calls_router, prefix="/api/calls", tags=["Calls"])
app.include_router(media_router, prefix="/api/media", tags=["Media"])

@app.get("/")
def home(request: Request):
    # Updated signature for FastAPI / Starlette compliance
    return templates.TemplateResponse(request=request, name="index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
