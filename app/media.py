import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

class MediaManager:
    """Manages secure storage and cleanup of media files."""

    def __init__(self, db):
        self.settings = get_settings()
        self.db = db
        self.media_dir = Path(self.settings.media_root)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = self.settings.media_retention_days

    def save_media(self, user_id: str, media_data: dict) -> str:
        """Saves media securely to disk and registers in DB. Returns media ID."""
        data_bytes = media_data["data"]
        mime_type = media_data.get("content_type", "application/octet-stream")
        
        # Calculate SHA256
        sha256_hash = hashlib.sha256(data_bytes).hexdigest()
        
        # Generate ID and Path
        media_id = str(uuid.uuid4())
        user_dir = self.media_dir / user_id.replace("@", "_").replace(".", "_")
        user_dir.mkdir(parents=True, exist_ok=True)
        
        ext = ".jpg" if "jpeg" in mime_type or "jpg" in mime_type else ".png"
        file_path = user_dir / f"{media_id}{ext}"
        
        # Write file securely
        with open(file_path, "wb") as f:
            f.write(data_bytes)
            
        # Restrict permissions (owner read/write only)
        os.chmod(file_path, 0o600)

        # Register in DB
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(days=self.retention_days)
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(
                text(
                    """
                    INSERT INTO media (id, user_id, path, mime, created_at, expires_at, sha256)
                    VALUES (:id, :uid, :path, :mime, :created_at, :expires_at, :sha256)
                    """
                ),
                {
                    "id": media_id,
                    "uid": user_id,
                    "path": str(file_path.absolute()),
                    "mime": mime_type,
                    "created_at": created_at,
                    "expires_at": expires_at,
                    "sha256": sha256_hash,
                }
            )
            conn.commit()
            
        logger.info(f"[MEDIA] Saved media {media_id} for user {user_id}")
        return media_id

    def cleanup_expired_media(self) -> int:
        """Deletes expired media from disk and DB."""
        now = datetime.now(timezone.utc)
        count = 0
        
        with self.db.engine.connect() as conn:
            from sqlalchemy import text
            # Get expired media
            result = conn.execute(
                text("SELECT id, path FROM media WHERE expires_at <= :now"),
                {"now": now}
            ).fetchall()
            
            for row in result:
                media_id = row[0]
                file_path = Path(row[1])
                
                # Delete file
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        logger.error(f"[MEDIA] Failed to delete file {file_path}: {e}")
                        
                # Delete DB record
                conn.execute(
                    text("DELETE FROM media WHERE id = :id"),
                    {"id": media_id}
                )
                count += 1
                
            if count > 0:
                conn.commit()
                
        if count > 0:
            logger.info(f"[MEDIA] Cleaned up {count} expired media files")
        return count
