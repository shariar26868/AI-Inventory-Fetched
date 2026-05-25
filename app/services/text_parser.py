import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def parse_text(file_path: str) -> List[Dict[str, Any]]:
    """
    Read a plain text file and return one entry per non-empty line.
    """
    try:
        results: List[Dict[str, Any]] = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue
                results.append({
                    "raw_text": text,
                    "_line": i,
                    "_source": "txt",
                })

        logger.info(f"TXT parsed: {len(results)} non-empty lines from {file_path}")
        return results

    except Exception as e:
        logger.error(f"TXT parse error: {e}")
        raise
