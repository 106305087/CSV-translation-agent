import io
import pandas as pd
from src.errors import UserFacingError
from src.config import MAX_FILE_ROWS

_ENCODINGS = ["utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin-1"]


def _find_header_row(raw: pd.DataFrame, max_scan: int = 20) -> int:
    """Index of the real header row, skipping leading title/banner rows.

    Spreadsheets exported to CSV often start with a title row (e.g.
    "Sample Preview - Product Reviews") followed by the actual table. A title
    row populates only one or two cells, while the header spans the full table
    width — so the first row that is close to the widest row is the header.
    """
    non_null = raw.notna().sum(axis=1)
    scan = non_null.iloc[:max_scan]
    widest = int(scan.max()) if len(scan) else 0
    if widest <= 1:
        return 0
    threshold = max(2, widest * 0.6)  # tolerate a header with one blank cell
    for i in range(len(scan)):
        if scan.iloc[i] >= threshold:
            return i
    return 0


def load_csv(file_bytes: bytes, filename: str = "file.csv") -> tuple[pd.DataFrame, dict]:
    df = None
    for enc in _ENCODINGS:
        try:
            # Pass 1: read raw to locate the real header row (skip any preamble).
            raw = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, header=None)
            header_idx = _find_header_row(raw)
            # Pass 2: re-read from the header row so pandas infers column dtypes.
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, skiprows=header_idx)
            break
        except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
            continue

    if df is None:
        raise UserFacingError(
            "I couldn't read this CSV. Please check that it is a valid CSV file with headers."
        )

    # Normalize labels to strings so numeric headers (1, 2, 3) don't become int labels
    # that mismatch string column selections downstream.
    df.columns = [str(c) for c in df.columns]

    # Drop blank auto-named columns left over from a title row's trailing commas.
    junk = [c for c in df.columns if c.startswith("Unnamed:") and df[c].isna().all()]
    if junk:
        df = df.drop(columns=junk)

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
