import io
import pandas as pd
from src.validators import validate_export
from src.errors import UserFacingError


def _unique_col_name(name: str, existing: set[str]) -> str:
    if name not in existing:
        return name
    v = 2
    while f"{name}_v{v}" in existing:
        v += 1
    return f"{name}_v{v}"


def build_export_csv(
    df: pd.DataFrame,
    translated_cols: dict[str, pd.Series],
) -> bytes:
    output_df = df.copy()
    existing_cols = set(output_df.columns)

    for col_name, series in translated_cols.items():
        unique_name = _unique_col_name(col_name, existing_cols)
        output_df[unique_name] = series.values
        existing_cols.add(unique_name)

    validate_export(df, output_df)

    buf = io.BytesIO()
    output_df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue()
