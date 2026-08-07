import os

# Database and Security Configurations for Qtalk
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./qtalk.db")
SECRET_KEY = os.getenv("SECRET_KEY", "quantum_super_secret_key_123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
