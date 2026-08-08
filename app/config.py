import os

class Settings:
    APP_NAME: str = "Qtalk"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "qtalk-super-secret-key-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./qtalk.db")
    UPLOAD_DIR: str = "uploads"

settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
