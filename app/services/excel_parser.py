import pandas as pd
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


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
                all_rows.append(row_dict)

        logger.info(f"Excel parsed: {len(all_rows)} rows from {len(xl.sheet_names)} sheet(s)")
        return all_rows

    except Exception as e:
        logger.error(f"Excel parse error: {e}")
        raise