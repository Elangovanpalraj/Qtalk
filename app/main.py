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

# Initialize Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Qtalk")

# Static & Media Mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
templates = Jinja2Templates(directory="templates")

# Register Feature Modules
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(contacts_router, prefix="/api/contacts", tags=["Contacts"])
app.include_router(status_router, prefix="/api/status", tags=["Status"])
app.include_router(calls_router, prefix="/api/calls", tags=["Calls"])
app.include_router(media_router, prefix="/api/media", tags=["Media"])

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
