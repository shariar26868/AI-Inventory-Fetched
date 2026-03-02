import json
import logging
import httpx
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

QUOTATION_SYSTEM_PROMPT = """You are a procurement quotation data extraction expert.
Given raw row data from Excel or PDF files, extract and normalize quotation information.

Always return a valid JSON object with a key "quotations" containing an array.
Each quotation object must have:
- quotation_number: Quotation/PO reference number (e.g. PTC-Q-2024-154)
- project_id: Project ID or code (e.g. PRJ-2026-0001)
- project_name: Hotel or company name (e.g. Marina Bay Hotel)
- supplier: Supplier or vendor name (e.g. Premium Textiles)
- total_amount: Total amount as string (e.g. "USD 68,750")
- currency: Currency code (e.g. "USD")
- valid_until: Validity date as string (e.g. "Mar 23, 2026")
- payment_terms: Payment terms (e.g. "40% advance, 60% on delivery")
- delivery_terms: Delivery terms (e.g. "DDP Dubai, custom made 5-6 weeks")
- items: Array of item objects, each with:
    - item_name: Name of the item
    - quantity: Quantity as string
    - unit_price: Unit price as string
    - total: Total price as string
    - remarks: Any remarks or notes
    - item_type: Type label e.g. "As Specified", "Alternatives"

Rules:
- If a field cannot be found, set it to null.
- items must always be an array, even if only one item.
- Return ONLY valid JSON. No explanation, no markdown.

Example:
{"quotations": [{"quotation_number": "PTC-Q-2024-154", "project_id": "PRJ-2026-0001", "project_name": "Marina Bay Hotel", "supplier": "Premium Textiles", "total_amount": "USD 68,750", "currency": "USD", "valid_until": "Mar 23, 2026", "payment_terms": "40% advance, 60% on delivery", "delivery_terms": "DDP Dubai", "items": [{"item_name": "Blackout Curtains - Full Drop", "quantity": "50", "unit_price": "USD 275", "total": "USD 54,750", "remarks": "100% blackout lining", "item_type": "As Specified"}]}]}
"""

REQUIRED_QUOTATION_FIELDS = [
    "quotation_number", "project_id", "project_name",
    "supplier", "total_amount", "valid_until"
]


def determine_quotation_status(q: Dict[str, Any]):
    missing = [f for f in REQUIRED_QUOTATION_FIELDS if not q.get(f)]
    if missing:
        return "Needs Review", missing
    return "Parsed", []


async def extract_quotations_with_ai(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Send raw rows to OpenAI and extract structured quotation data.
    """
    BATCH_SIZE = 20
    all_results = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(raw_rows), BATCH_SIZE):
            batch = raw_rows[i: i + BATCH_SIZE]
            batch_text = json.dumps(batch, ensure_ascii=False, default=str)

            payload = {
                "model": "gpt-4o",
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": QUOTATION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Extract quotation data from this:\n{batch_text}"}
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

                all_results.extend(parsed)
                logger.info(f"Quotation AI batch {i // BATCH_SIZE + 1}: extracted {len(parsed)} quotations")

            except Exception as e:
                logger.error(f"Quotation AI error batch {i // BATCH_SIZE + 1}: {e}")
                # Fallback: add raw as minimal quotation
                for row in batch:
                    all_results.append({
                        "quotation_number": row.get("quotation_number") or row.get("Quotation No") or row.get("PO No"),
                        "project_id": row.get("project_id") or row.get("Project ID"),
                        "project_name": row.get("project_name") or row.get("Project"),
                        "supplier": row.get("supplier") or row.get("Supplier"),
                        "total_amount": row.get("total_amount") or row.get("Total Amount"),
                        "currency": row.get("currency") or row.get("Currency"),
                        "valid_until": row.get("valid_until") or row.get("Valid Until"),
                        "payment_terms": row.get("payment_terms") or row.get("Payment Terms"),
                        "delivery_terms": row.get("delivery_terms") or row.get("Delivery Terms"),
                        "items": [],
                        "_raw": row,
                    })

    return all_results