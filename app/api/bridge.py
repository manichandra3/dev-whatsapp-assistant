"""
Bridge API - HTTP endpoint for Node adapter communication.

Provides a simple REST API that the Node.js WhatsApp adapter can use
to send messages to the Python brain and receive responses.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.assistant import DevAssistantBrain
from app.config import get_settings
from app.scheduler import ReminderScheduler
from app.proactive import ProactiveAgent

logger = logging.getLogger(__name__)


class MessageRequest(BaseModel):
    """Request model for incoming messages."""

    user_id: str = Field(..., description="WhatsApp user ID (e.g., 1234567890@s.whatsapp.net)")
    message_text: str = Field(..., description="The message content from the user")


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


# Global brain instance (initialized on startup)
brain: DevAssistantBrain | None = None
scheduler: ReminderScheduler | None = None
proactive_agent: ProactiveAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global brain
    global scheduler
    global proactive_agent

    # Startup
    settings = get_settings()
    brain = DevAssistantBrain(settings)
    scheduler = ReminderScheduler(brain.db, settings)
    proactive_agent = ProactiveAgent(brain.db)
    
    await scheduler.start()
    await proactive_agent.start()

    logger.info(f"[BRIDGE] Started with provider: {settings.llm_provider}")
    logger.info(f"[BRIDGE] Model: {settings.llm_model}")
    logger.info(f"[BRIDGE] Database: {settings.database_path}")

    yield

    # Shutdown
    if proactive_agent:
        await proactive_agent.stop()
    if scheduler:
        await scheduler.stop()
    if brain:
        brain.close()
    logger.info("[BRIDGE] Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Dev Assistant Bridge",
    description="HTTP bridge for Node.js WhatsApp adapter to Python brain",
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
async def handle_message(request: MessageRequest) -> MessageResponse:
    """
    Handle an incoming message from the Node.js WhatsApp adapter.

    This endpoint receives messages from the Node bridge client,
    processes them through the brain, and returns the response.
    """
    global brain

    if not brain:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    try:
        logger.info(f"[BRIDGE] Received message from {request.user_id}")

        response = await brain.handle_message(
            user_id=request.user_id,
            message_text=request.message_text,
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
        "service": "Dev Assistant Bridge",
        "version": "1.0.0",
        "docs": "/docs",
    }
