import json
import logging
import re
from typing import Any

from sqlalchemy import text

from app.database import DatabaseManager
from app.llm.providers import LLMProvider

logger = logging.getLogger(__name__)


async def parse_prescription_image(
    db: DatabaseManager, llm: LLMProvider | None, user_id: str, media_id: str
) -> dict[str, Any]:
    if not llm:
        return {"error": True, "message": "LLM provider not configured for image analysis."}

    try:
        with db.engine.connect() as conn:
            result = conn.execute(
                text("SELECT path FROM media WHERE id = :id AND user_id = :uid"),
                {"id": media_id, "uid": user_id}
            ).fetchone()

        if not result:
            return {"error": True, "message": f"Media ID {media_id} not found."}

        image_path = result[0]

        prompt = """You are a medical data extraction assistant. 
Please carefully read this prescription/medication label and extract the following details in JSON format.
If you cannot find a detail, use null.
The output MUST be valid JSON matching this schema exactly:
{
    "meds": [
        {
            "name": "string (name of medication)",
            "dose": "string (e.g. 500mg)",
            "frequency": "string (e.g. twice daily, q12h)",
            "duration": "string (e.g. 7 days)",
            "raw_text": "string (the exact text snippet you found this in)"
        }
    ],
    "suggestions": ["string (e.g. 'Set a reminder for twice daily', 'Ensure taken with food')"]
}
Do not include any text outside the JSON."""

        response_text = await llm.analyze_image(image_path, prompt)

        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            json_str = json_match.group(1) if json_match else response_text

        parsed_data = json.loads(json_str)

        with db.engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO prescription_parses (user_id, media_id, raw_text, parsed_json) "
                    "VALUES (:uid, :mid, :raw, :json)"
                ),
                {"uid": user_id, "mid": media_id, "raw": response_text, "json": json.dumps(parsed_data)}
            )
            conn.commit()

        return {
            "success": True,
            "parsed_data": parsed_data,
            "message": f"Successfully parsed prescription. Found {len(parsed_data.get('meds', []))} medications."
        }

    except Exception as e:
        logger.error(f"[TOOL] Error parsing prescription: {e}")
        return {"error": True, "message": str(e)}


async def interpret_knee_image(
    db: DatabaseManager, llm: LLMProvider | None, user_id: str, media_id: str
) -> dict[str, Any]:
    if not llm:
        return {"error": True, "message": "LLM provider not configured for image analysis."}

    try:
        with db.engine.connect() as conn:
            result = conn.execute(
                text("SELECT path FROM media WHERE id = :id AND user_id = :uid"),
                {"id": media_id, "uid": user_id}
            ).fetchone()

        if not result:
            return {"error": True, "message": f"Media ID {media_id} not found."}

        image_path = result[0]

        prompt = """You are an ACL rehabilitation assistant. 
Please look at this image of a knee post-surgery.
You must NEVER provide a definitive medical diagnosis. Provide OBSERVATIONS ONLY.

Evaluate the image for:
1. Dressing status (is it covered, exposed, clean, soiled?)
2. Visible redness (erythema)
3. Swelling (compare to surrounding tissue if possible)
4. Bruising (ecchymosis)
5. Any visible drainage or discharge
6. Overall impression

Output MUST be valid JSON:
{
    "observations": [
        "Observation 1",
        "Observation 2"
    ],
    "flags": [
        "Any red flags (e.g. extreme redness, purulent drainage). Empty array if none."
    ],
    "confidence": "high|medium|low"
}
Do not include any text outside the JSON."""

        response_text = await llm.analyze_image(image_path, prompt)

        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
            json_str = json_match.group(1) if json_match else response_text

        parsed_data = json.loads(json_str)

        return {
            "success": True,
            "data": parsed_data,
            "message": "Successfully interpreted knee image. Please review the observations and flags."
        }

    except Exception as e:
        logger.error(f"[TOOL] Error interpreting knee image: {e}")
        return {"error": True, "message": str(e)}
