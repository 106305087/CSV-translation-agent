import difflib
import pandas as pd
from src.config import LANGUAGE_MAP, MAX_FILE_ROWS
from src.errors import UserFacingError


def validate_file(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        raise UserFacingError("The CSV file is empty.")
    if len(df) > MAX_FILE_ROWS:
        raise UserFacingError(f"File exceeds the {MAX_FILE_ROWS:,} row limit.")
    if len(df.columns) == 0:
        raise UserFacingError("The CSV has no columns.")


def validate_columns(selected: list[str], df_cols: list[str]) -> None:
    df_cols_lower = {c.lower(): c for c in df_cols}
    missing = []
    for col in selected:
        if col not in df_cols and col.lower() not in df_cols_lower:
            close = difflib.get_close_matches(col, df_cols, n=3, cutoff=0.5)
            suggestion = f" Did you mean: {', '.join(f'`{c}`' for c in close)}?" if close else ""
            missing.append(f"`{col}`{suggestion}")

    if missing:
        raise UserFacingError(
            f"I couldn't find the column(s): {'; '.join(missing)}\n"
            f"Available columns: {', '.join(f'`{c}`' for c in df_cols)}"
        )


def validate_languages(codes: list[str]) -> None:
    supported_codes = set(LANGUAGE_MAP.values())
    unsupported = [c for c in codes if c not in supported_codes]
    if unsupported:
        raise UserFacingError(
            f"Unsupported language code(s): {', '.join(unsupported)}. "
            f"Supported: {', '.join(sorted(supported_codes))}"
        )


def validate_translation_output(
    row_ids: list[int],
    translations: list[dict],
) -> None:
    returned_ids = {t["row_id"] for t in translations}
    expected_ids = set(row_ids)
    missing = expected_ids - returned_ids
    if missing:
        raise UserFacingError(
            f"Translation response is missing {len(missing)} row(s). "
            "This batch will be retried."
        )
    for t in translations:
        if not isinstance(t.get("translated_text"), str):
            raise UserFacingError("Translation response contained a non-string value.")


def validate_export(original_df: pd.DataFrame, output_df: pd.DataFrame) -> None:
    if len(output_df) != len(original_df):
        raise UserFacingError(
            f"Row count mismatch after export: expected {len(original_df)}, got {len(output_df)}."
        )
    for col in original_df.columns:
        if col not in output_df.columns:
            raise UserFacingError(f"Original column `{col}` is missing from the export.")
