"""
Developer WhatsApp Assistant - Main Application Entry Point

Starts the FastAPI server for the Python bridge.
"""

import logging
import os
import sys

import uvicorn

from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the application."""
    settings = get_settings()

    # Set log level from settings
    log_level = settings.log_level.upper()
    logging.getLogger().setLevel(log_level)

    logger.info("Dev Assistant Starting...")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Model: {settings.llm_model}")
    logger.info(f"Database: {settings.database_path}")
    logger.info(f"Bridge: http://{settings.python_bridge_host}:{settings.python_bridge_port}")

    # Start the FastAPI server
    uvicorn.run(
        "app.api.bridge:app",
        host=settings.python_bridge_host,
        port=settings.python_bridge_port,
        reload=False,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
