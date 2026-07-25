import asyncio
import json
import logging
import httpx
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["item_name", "item_code", "description", "qty", "manufacturer", "commodity"]

# ── Retry settings: fail fast so Swagger doesn't spin forever ──
MAX_RETRIES = 1          # Only 1 retry per batch (2 total attempts)
INITIAL_RETRY_DELAY = 3.0
MAX_RETRY_DELAY = 10.0   # Cap the delay so we don't wait forever

SYSTEM_PROMPT = """You are a procurement data extraction expert.
Given raw extracted rows from procurement documents (Excel, PDF, DOCX, PPTX, TXT, or OCR text), extract and normalize procurement item information.

Each row may contain structured columns, paragraph text, slide text, or unstructured fields such as raw_text, Item Name, Description, Qty, or Category.
Always return a valid JSON object with a key "items" containing an array. Each object must attempt to fill these fields:
- item_name: Product name
- item_code: SKU/code (e.g. GR-SAF-009)
- description: Full product description/specs
- qty: Quantity (number + unit if available)
- manufacturer: Brand or manufacturer name
- commodity: Category (e.g. Furniture, Electronics, Stone)

Rules:
- If a field cannot be found, set it to null — do NOT guess or fabricate.
- Use raw_text as input when explicit fields are missing.
- Return ONLY valid JSON. No explanation, no markdown, no extra text.
- Prefer one item record per procurement line or product.
- If the input row does not represent a procurement item, omit it.

Example response format:
{"items": [{"item_name": "Electronic Safe", "item_code": "GR-SAF-009", "description": "20L capacity", "qty": "50 pcs", "manufacturer": "Kohler", "commodity": "Furniture"}]}
"""


def _build_fallback_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a structured item directly from raw row columns without AI.
    Tries many common column name variants so data isn't lost.
    """
    raw_text = row.get("raw_text") or row.get("Raw Text") or row.get("text") or ""
    public_fields = {
        k: v for k, v in row.items()
        if not k.startswith("_") and v is not None and str(v).strip()
    }
    fallback_description = raw_text or "; ".join(
        f"{k}: {v}" for k, v in public_fields.items()
    )

    return {
        "item_name": (
            row.get("item_name") or row.get("Item Name") or
            row.get("Name") or row.get("ITEM NAME") or
            row.get("Product Name") or row.get("product_name") or
            row.get("PRODUCT NAME") or row.get("Item") or row.get("ITEM")
        ),
        "item_code": (
            row.get("item_code") or row.get("Code") or
            row.get("SKU") or row.get("Item Code") or
            row.get("ITEM CODE") or row.get("Part No") or
            row.get("Part Number") or row.get("Model") or
            row.get("MODEL") or row.get("Ref") or row.get("Reference")
        ),
        "description": (
            row.get("description") or row.get("Description") or
            row.get("DESCRIPTION") or row.get("Specs") or
            row.get("Specification") or row.get("Details") or
            fallback_description
        ),
        "qty": (
            row.get("qty") or row.get("Qty") or
            row.get("Quantity") or row.get("QTY") or
            row.get("No.") or row.get("Count") or
            row.get("QUANTITY") or row.get("Amount")
        ),
        "manufacturer": (
            row.get("manufacturer") or row.get("Manufacturer") or
            row.get("Brand") or row.get("BRAND") or
            row.get("Make") or row.get("Vendor") or
            row.get("Supplier") or row.get("MANUFACTURER")
        ),
        "commodity": (
            row.get("commodity") or row.get("Commodity") or
            row.get("Category") or row.get("CATEGORY") or
            row.get("Type") or row.get("Group") or
            row.get("COMMODITY") or row.get("Section")
        ),
        "_raw": row,
    }


async def _try_openai_batch(
    client: httpx.AsyncClient,
    batch: List[Dict[str, Any]],
    batch_num: int,
    model: str = "gpt-4o",
) -> List[Dict[str, Any]]:
    """
    Try one batch with OpenAI. Returns extracted items or raises on failure.
    Fast-fail: only MAX_RETRIES retries, capped delay.
    """
    batch_text = json.dumps(batch, ensure_ascii=False, default=str)
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract procurement items from this data:\n{batch_text}"}
        ]
    }

    content = "n/a"
    for attempt in range(MAX_RETRIES + 1):
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code in {429, 500, 502, 503, 504}:
            if attempt >= MAX_RETRIES:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(float(retry_after) if retry_after else INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
            except ValueError:
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)

            logger.warning(
                "OpenAI rate limit (status %s) on batch %s [%s]. Retrying in %.1fs.",
                response.status_code, batch_num, model, delay,
            )
            await asyncio.sleep(delay)
            continue

        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        parsed = json.loads(content)

        # Normalize to list
        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                parsed = parsed["items"]
            else:
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
                else:
                    parsed = []

        if not isinstance(parsed, list) or not parsed:
            raise ValueError(f"Empty or unexpected response format: {type(parsed).__name__}")

        logger.info("AI batch %s [%s]: extracted %d items", batch_num, model, len(parsed))
        return parsed

    raise RuntimeError(f"OpenAI batch {batch_num} failed after {MAX_RETRIES + 1} attempts")


async def extract_items_with_ai(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Send raw rows to OpenAI in batches.

    Circuit Breaker Logic:
    - If the first batch fails with 429, AI is clearly unavailable.
    - Skip all remaining AI calls and use direct fallback for ALL rows.
    - This prevents Swagger from spinning for minutes.

    Model Fallback:
    - Try gpt-4o first. If it fails with 429, try gpt-3.5-turbo.
    - If both fail, use direct column-mapping fallback.
    """
    BATCH_SIZE = 20
    all_results = []

    # Circuit breaker flag: if True, skip AI for all remaining batches
    ai_unavailable = False

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i in range(0, len(raw_rows), BATCH_SIZE):
            batch = raw_rows[i: i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            # ── Circuit breaker: AI already known unavailable ──────────
            if ai_unavailable:
                logger.warning("Circuit breaker OPEN — skipping AI for batch %s, using fallback.", batch_num)
                for row in batch:
                    all_results.append(_build_fallback_item(row))
                continue

            # ── Small inter-batch delay to spread requests ─────────────
            if i > 0:
                await asyncio.sleep(1.5)

            # ── Try gpt-4o ────────────────────────────────────────────
            items = None
            try:
                items = await _try_openai_batch(client, batch, batch_num, model="gpt-4o")
                all_results.extend(items)
                continue
            except Exception as e_4o:
                logger.warning("gpt-4o failed on batch %s: %s. Trying gpt-3.5-turbo...", batch_num, e_4o)

            # ── Try gpt-3.5-turbo as cheaper fallback model ───────────
            try:
                items = await _try_openai_batch(client, batch, batch_num, model="gpt-3.5-turbo")
                all_results.extend(items)
                continue
            except Exception as e_35:
                logger.error(
                    "gpt-3.5-turbo also failed on batch %s: %s. "
                    "Opening circuit breaker — all remaining batches will use direct fallback.",
                    batch_num, e_35
                )
                # ── Open circuit breaker ──────────────────────────────
                ai_unavailable = True
                for row in batch:
                    all_results.append(_build_fallback_item(row))

    if ai_unavailable:
        logger.warning(
            "⚠️  AI was unavailable — all %d items saved via direct column mapping (Needs Review).",
            len(all_results)
        )

    return all_results