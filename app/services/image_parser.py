import base64
import json
import logging
import httpx
from typing import List, Dict, Any
from app.core.config import settings
from app.services.openai_service import SYSTEM_PROMPT as ITEM_SYSTEM_PROMPT
from app.services.quotation_openai_service import QUOTATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def encode_image(file_path: str) -> str:
    """Encode the image at file_path to base64."""
    with open(file_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

async def extract_items_from_image(file_path: str) -> List[Dict[str, Any]]:
    """
    Use GPT-4o Vision to extract structured procurement items from an image.
    Uses the same SYSTEM_PROMPT as standard Excel/PDF extraction.
    """
    try:
        base64_image = encode_image(file_path)
        
        payload = {
            "model": "gpt-4o",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": ITEM_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all procurement items from this image."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Strip markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            parsed = json.loads(content)

            # Unwrap {"items": [...]} if needed
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    parsed = []

            logger.info(f"Vision AI extracted {len(parsed)} items from image.")
            
            # Decorate extracted items
            decorated_items = []
            for item in parsed:
                item["_source"] = "image"
                decorated_items.append(item)
                
            return decorated_items

    except Exception as e:
        logger.error(f"Failed to extract items from image via Vision API: {e}")
        return []

async def extract_quotations_from_image(file_path: str) -> List[Dict[str, Any]]:
    """
    Use GPT-4o Vision to extract structured quotation details from an image.
    Uses the same QUOTATION_SYSTEM_PROMPT as standard Excel/PDF extraction.
    """
    try:
        base64_image = encode_image(file_path)
        
        payload = {
            "model": "gpt-4o",
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": QUOTATION_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract quotation data from this image."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Strip markdown if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            parsed = json.loads(content)

            # Unwrap {"quotations": [...]}
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    parsed = []

            logger.info(f"Vision AI extracted {len(parsed)} quotations from image.")
            
            decorated = []
            for item in parsed:
                item["_source"] = "image"
                decorated.append(item)
                
            return decorated

    except Exception as e:
        logger.error(f"Failed to extract quotations from image via Vision API: {e}")
        return []
