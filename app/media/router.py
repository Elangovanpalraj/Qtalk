import os
import uuid
from fastapi import APIRouter, UploadFile, File
from app.config import settings

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    extension = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{extension}"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {"url": f"/uploads/{filename}"}
