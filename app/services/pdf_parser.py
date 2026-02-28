import pdfplumber
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse PDF: extracts tables first, falls back to raw text per page.
    Returns list of dicts representing rows/entries.
    """
    try:
        all_rows = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()

                if tables:
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        # First row = headers
                        headers = [
                            str(h).strip() if h else f"col_{i}"
                            for i, h in enumerate(table[0])
                        ]
                        for row in table[1:]:
                            if not any(row):
                                continue
                            row_dict = {}
                            for i, cell in enumerate(row):
                                key = headers[i] if i < len(headers) else f"col_{i}"
                                row_dict[key] = str(cell).strip() if cell else None
                            row_dict["_page"] = page_num
                            row_dict["_source"] = "pdf"
                            all_rows.append(row_dict)
                else:
                    # Fallback: raw text block
                    text = page.extract_text()
                    if text:
                        all_rows.append({
                            "_page": page_num,
                            "_source": "pdf",
                            "raw_text": text.strip()
                        })

        logger.info(f"PDF parsed: {len(all_rows)} entries")
        return all_rows

    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        raise