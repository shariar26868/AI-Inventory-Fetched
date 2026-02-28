import json
import logging
import httpx
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["item_name", "item_code", "description", "qty", "manufacturer", "commodity"]

SYSTEM_PROMPT = """You are a procurement data extraction expert.
Given raw row data from Excel or PDF files, extract and normalize procurement item information.

Always return a valid JSON object with a key "items" containing an array. Each object must attempt to fill these fields:
- item_name: Product name
- item_code: SKU/code (e.g. GR-SAF-009)
- description: Full product description/specs
- qty: Quantity (number + unit if available)
- manufacturer: Brand or manufacturer name
- commodity: Category (e.g. Furniture, Electronics, Stone)

Rules:
- If a field cannot be found, set it to null — do NOT guess or fabricate.
- Return ONLY valid JSON. No explanation, no markdown, no extra text.
- Merge related rows if they clearly belong to the same item.

Example response format:
{"items": [{"item_name": "Electronic Safe", "item_code": "GR-SAF-009", "description": "20L capacity", "qty": "50 pcs", "manufacturer": "Kohler", "commodity": "Furniture"}]}
"""


async def extract_items_with_ai(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Send raw rows to OpenAI in batches using httpx directly.
    Avoids openai SDK version/httpx compatibility issues.
    """
    BATCH_SIZE = 30
    all_results = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(raw_rows), BATCH_SIZE):
            batch = raw_rows[i: i + BATCH_SIZE]
            batch_text = json.dumps(batch, ensure_ascii=False, default=str)

            payload = {
                "model": "gpt-4o",
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Extract procurement items from this data:\n{batch_text}"}
                ]
            }

            try:
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

                all_results.extend(parsed)
                logger.info(f"AI batch {i // BATCH_SIZE + 1}: extracted {len(parsed)} items")

            except Exception as e:
                logger.error(f"OpenAI error on batch {i // BATCH_SIZE + 1}: {e}")
                # Fallback: map raw row fields directly
                for row in batch:
                    all_results.append({
                        "item_name": row.get("item_name") or row.get("Item Name") or row.get("Name"),
                        "item_code": row.get("item_code") or row.get("Code") or row.get("SKU"),
                        "description": row.get("description") or row.get("Description"),
                        "qty": row.get("qty") or row.get("Qty") or row.get("Quantity"),
                        "manufacturer": row.get("manufacturer") or row.get("Manufacturer"),
                        "commodity": row.get("commodity") or row.get("Commodity") or row.get("Category"),
                        "_raw": row,
                    })

    return all_results