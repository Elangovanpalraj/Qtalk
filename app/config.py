import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quantum_connect.db")
SECRET_KEY = os.getenv("SECRET_KEY", "quantum_super_secret_key_123")