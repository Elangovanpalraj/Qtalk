from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# You can set DATABASE_URL in environment variables or default to local SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./whatsapp.db")

# Heroku/Render/Supabase fix for postgres:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session in endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
