import pandas as pd
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def _has_meaningful_excel_row(row_dict: Dict[str, Any]) -> bool:
    """Return True if the row contains meaningful data beyond metadata and unit-only rows."""
    meaningful_keys = [k for k in row_dict.keys() if not k.startswith("_")]
    if not meaningful_keys:
        return False

    non_empty_fields = [k for k in meaningful_keys if row_dict.get(k) is not None and str(row_dict[k]).strip()]
    if not non_empty_fields:
        return False

    # If the only non-empty field is unit, this row is not useful for extraction.
    if len(non_empty_fields) == 1 and non_empty_fields[0].lower() == "unit":
        return False

    return True


def parse_excel(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse Excel file and return list of raw row dicts.
    Handles multiple sheets and merges all rows.
    """
    try:
        xl = pd.ExcelFile(file_path)
        all_rows = []

        for sheet_name in xl.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, dtype=str)
            df = df.dropna(how="all")
            df.columns = [str(c).strip() for c in df.columns]

            for _, row in df.iterrows():
                row_dict = {k: (v if pd.notna(v) else None) for k, v in row.items()}
                row_dict["_sheet"] = sheet_name
                row_dict["_source"] = "excel"
                if _has_meaningful_excel_row(row_dict):
                    all_rows.append(row_dict)

        logger.info(f"Excel parsed: {len(all_rows)} rows from {len(xl.sheet_names)} sheet(s)")
        return all_rows

    except Exception as e:
        logger.error(f"Excel parse error: {e}")
        raise