from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os

from .utils import save_media_file, delete_media_file, UPLOAD_DIR

router = APIRouter(
    prefix="/media",
    tags=["Media & Attachments"]
)


@router.post("/upload")
async def upload_media(file: UploadFile = File(...)):
    """
    Endpoint to upload chat attachments (images, voice notes, videos, documents).
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    saved_info = save_media_file(file)
    return {
        "success": True,
        "message": "File uploaded successfully",
        "data": saved_info
    }


@router.get("/file/{filename}")
async def get_media_file(filename: str):
    """
    Endpoint to stream or serve uploaded media files directly to the chat frontend.
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Requested media file not found")
    
    return FileResponse(file_path)


@router.delete("/file/{filename}")
async def remove_media_file(filename: str):
    """
    Endpoint to delete a media file when a chat attachment is deleted.
    """
    success = delete_media_file(filename)
    if not success:
        raise HTTPException(status_code=404, detail="File not found or already deleted")
    
    return {
        "success": True,
        "message": f"File '{filename}' deleted successfully"
    }
