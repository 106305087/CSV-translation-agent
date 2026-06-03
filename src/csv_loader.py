import io
import pandas as pd
from src.errors import UserFacingError
from src.config import MAX_FILE_ROWS


def load_csv(file_bytes: bytes, filename: str = "file.csv") -> tuple[pd.DataFrame, dict]:
    encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin-1"]
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue

    if df is None:
        raise UserFacingError(
            "I couldn't read this CSV. Please check that it is a valid CSV file with headers."
        )

    if df.empty or len(df.columns) == 0:
        raise UserFacingError("The uploaded CSV file is empty. Please upload a file with data.")

    if len(df) == 0:
        raise UserFacingError("The CSV has headers but no rows. Please upload a file with at least one data row.")

    if len(df) > MAX_FILE_ROWS:
        raise UserFacingError(
            f"This file has {len(df):,} rows, which exceeds the limit of {MAX_FILE_ROWS:,} rows."
        )

    profile = {
        "filename": filename,
        "rows": len(df),
        "columns": len(df.columns),
        "col_names": list(df.columns),
    }
    return df, profile
