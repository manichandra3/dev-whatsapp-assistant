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
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


class MessageRequest(BaseModel):
    """Request model for incoming messages."""

    user_id: str = Field(..., description="WhatsApp user ID (e.g., 1234567890@s.whatsapp.net)")
    message_text: str = Field(..., description="The message content from the user")
    media: dict[str, Any] | None = None
    context: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """Response model for message handling."""

    success: bool
    response: str | None = None
    whatsapp_payload: dict[str, Any] | None = None
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

    # Init APScheduler with database manager reference for scheduled jobs
    init_scheduler(settings.database_path, settings.node_bridge_port, db=coach.db)

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
            # Ensure context is preserved when forwarded from Node bridge
            ctx = payload.get("context")
            request_data = MessageRequest(**payload)
            if ctx and isinstance(ctx, dict):
                request_data.context = ctx
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

            # Parse optional context field (may be JSON string)
            context_field = form.get("context")
            context_obj = None
            if context_field:
                try:
                    import json

                    context_obj = json.loads(context_field)
                except Exception:
                    context_obj = {"raw": str(context_field)}

            request_data = MessageRequest(
                user_id=str(user_id),
                message_text=str(message_text),
                media=media_payload,
                context=context_obj,
            )
        else:
            raise HTTPException(status_code=415, detail="Unsupported content type")

        logger.info(f"[BRIDGE] Received message from {request_data.user_id}")

        # Always update last message time BEFORE any early returns
        coach.db.update_last_message_time(request_data.user_id)

        # Check for "done" style replies when context contains stanza id
        ctx = request_data.context or {}
        stanza_id = ctx.get("stanzaId") or ctx.get("stanza_id")
        message_text_str = request_data.message_text or ""
        text = message_text_str.strip().lower()
        if stanza_id and text in ("done", "done.", "✓", "ok", "okay"):
            # Match to reminder by last_stanza_id
            try:
                engine = coach.db.get_engine_or_raise()
                with engine.connect() as conn:
                    row = conn.execute(
                        sa_text("SELECT id, user_id FROM reminders WHERE last_stanza_id = :sid"),
                        {"sid": stanza_id},
                    ).fetchone()
                    if row and row[1] == request_data.user_id:
                        # Insert adherence log
                        conn.execute(
                            sa_text(
                                "INSERT INTO adherence_logs (user_id, reminder_type, action_time, status, reminder_id, stanza_id) VALUES (:uid, :rtype, DATETIME('now'), :status, :rid, :sid)"
                            ),
                            {
                                "uid": request_data.user_id,
                                "rtype": "reminder",
                                "status": "done",
                                "rid": row[0],
                                "sid": stanza_id,
                            },
                        )
                        conn.commit()
                        return MessageResponse(success=True, response="Thanks — logged your completion of the reminder.")
            except Exception as e:
                logger.warning(f"[BRIDGE] Error matching done reply: {e}")

        response = await coach.handle_message(
            user_id=request_data.user_id,
            message_text=request_data.message_text,
            media=request_data.media,
            
        )
        
        response_text = response
        whatsapp_payload = None
        if isinstance(response, tuple):
            response_text = response[0]
            whatsapp_payload = response[1]

        return MessageResponse(success=True, response=response_text, whatsapp_payload=whatsapp_payload)

    except Exception as e:
        logger.error(f"[BRIDGE] Error handling message: {e}")
        return MessageResponse(
            success=False,
            error="An unexpected error occurred. Please try again.",
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
