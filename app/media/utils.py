import os
import uuid
import shutil
from fastapi import UploadFile, HTTPException

# Directory settings
UPLOAD_DIR = "uploads/media"
ALLOWED_EXTENSIONS = {
    "image": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
    "audio": [".mp3", ".wav", ".aac", ".m4a", ".ogg"],
    "video": [".mp4", ".mkv", ".webm"],
    "document": [".pdf", ".docx", ".txt", ".zip"]
}
MAX_FILE_SIZE_MB = 15 * 1024 * 1024  # 15 MB limit


def ensure_upload_dir_exists():
    """Ensure that the media upload directory exists on the disk."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_file_type(filename: str) -> str:
    """Determine the category of the uploaded file based on its extension."""
    ext = os.path.splitext(filename)[1].lower()
    for file_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return file_type
    return "other"


def validate_media_file(file: UploadFile):
    """Validate file extension and ensure it meets allowable upload criteria."""
    ext = os.path.splitext(file.filename)[1].lower()
    all_allowed = [ext for sublist in ALLOWED_EXTENSIONS.values() for ext in sublist]
    
    if ext not in all_allowed:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(all_allowed)}"
        )


def save_media_file(file: UploadFile) -> dict:
    """Save the file safely with a unique filename to prevent collisions."""
    ensure_upload_dir_exists()
    validate_media_file(file)

    # Generate a unique filename using UUID
    file_ext = os.path.splitext(file.filename)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    file_size = os.path.getsize(file_path)
    file_category = get_file_type(file.filename)

    return {
        "original_name": file.filename,
        "saved_filename": unique_filename,
        "file_path": file_path,
        "file_type": file_category,
        "size_bytes": file_size,
        "media_url": f"/media/file/{unique_filename}"
    }


def delete_media_file(filename: str) -> bool:
    """Utility to delete a media file from the local storage."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    return False
