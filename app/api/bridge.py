"""
Bridge API - HTTP endpoint for Node adapter communication.

Provides a simple REST API that the Node.js WhatsApp adapter can use
to send messages to the Python coach and receive responses.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.coach import ACLRehabCoach
from app.config import get_settings
from app.scheduler import init_scheduler, get_scheduler

logger = logging.getLogger(__name__)


class MessageRequest(BaseModel):
    """Request model for incoming messages."""

    user_id: str = Field(..., description="WhatsApp user ID (e.g., 1234567890@s.whatsapp.net)")
    message_text: str = Field(..., description="The message content from the user")
    media: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """Response model for message handling."""

    success: bool
    response: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    provider: str
    model: str


# Global coach instance (initialized on startup)
coach: ACLRehabCoach | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global coach

    # Startup
    settings = get_settings()
    coach = ACLRehabCoach(settings)

    # Init APScheduler
    init_scheduler(settings.database_path, settings.node_bridge_port)

    logger.info(f"[BRIDGE] Started with provider: {settings.llm_provider}")
    logger.info(f"[BRIDGE] Model: {settings.llm_model}")
    logger.info(f"[BRIDGE] Database: {settings.database_path}")

    yield

    # Shutdown
    scheduler = get_scheduler()
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
            logger.info("[BRIDGE] Scheduler shutdown")
        except Exception as e:
            logger.warning(f"[BRIDGE] Scheduler shutdown error: {e}")

    if coach:
        try:
            coach.close()
        except Exception as e:
            logger.warning(f"[BRIDGE] Coach close error: {e}")
    logger.info("[BRIDGE] Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="ACL Rehab Coach Bridge",
    description="HTTP bridge for Node.js WhatsApp adapter to Python coach",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        provider=settings.llm_provider,
        model=settings.llm_model,
    )


@app.post("/message", response_model=MessageResponse)
async def handle_message(request: Request) -> MessageResponse:
    """
    Handle an incoming message from the Node.js WhatsApp adapter.

    This endpoint receives messages from the Node bridge client,
    processes them through the coach, and returns the response.
    """
    global coach

    if not coach:
        raise HTTPException(status_code=503, detail="Coach not initialized")

    try:
        content_type = request.headers.get("content-type", "")

        if content_type.startswith("application/json"):
            payload = await request.json()
            request_data = MessageRequest(**payload)
        elif content_type.startswith("multipart/form-data"):
            form = await request.form()
            user_id = form.get("user_id")
            if not user_id:
                raise HTTPException(status_code=400, detail="Missing user_id")
            message_text = form.get("message_text") or ""
            media_caption = form.get("media_caption")
            media_file = form.get("media")

            media_payload = None
            if media_file is not None and hasattr(media_file, "read"):
                media_bytes = await media_file.read()
                media_payload = {
                    "filename": getattr(media_file, "filename", "unknown"),
                    "content_type": getattr(media_file, "content_type", "application/octet-stream"),
                    "size": len(media_bytes),
                    "caption": media_caption,
                    "data": media_bytes,
                }

            request_data = MessageRequest(
                user_id=str(user_id),
                message_text=str(message_text),
                media=media_payload,
            )
        else:
            raise HTTPException(status_code=415, detail="Unsupported content type")

        logger.info(f"[BRIDGE] Received message from {request_data.user_id}")

        response = await coach.handle_message(
            user_id=request_data.user_id,
            message_text=request_data.message_text,
            media=request_data.media,
        )

        return MessageResponse(success=True, response=response)

    except Exception as e:
        logger.error(f"[BRIDGE] Error handling message: {e}")
        return MessageResponse(
            success=False,
            error=str(e),
            response="❌ I apologize, but I encountered a technical issue. Please try sending your message again.",
        )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with basic info."""
    return {
        "service": "ACL Rehab Coach Bridge",
        "version": "1.0.0",
        "docs": "/docs",
    }
