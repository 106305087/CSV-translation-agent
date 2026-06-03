import re
import pandas as pd
from src.config import TEXT_COLUMN_KEYWORDS, METADATA_KEYWORDS

_CHINESE_RE = re.compile(r"[一-鿿㐀-䶿]")


def _chinese_ratio(series: pd.Series) -> float:
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return 0.0
    total_chars = sum(len(s) for s in sample)
    if total_chars == 0:
        return 0.0
    chinese_chars = sum(len(_CHINESE_RE.findall(s)) for s in sample)
    return chinese_chars / total_chars


def _avg_len(series: pd.Series) -> float:
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return 0.0
    return sum(len(s) for s in sample) / len(sample)


def detect_text_columns(df: pd.DataFrame) -> list[str]:
    scores: dict[str, int] = {}
    for col in df.columns:
        col_lower = col.lower()
        if df[col].dtype not in (object, "string"):
            continue

        score = 0
        if any(kw in col_lower for kw in TEXT_COLUMN_KEYWORDS):
            score += 3
        if any(kw in col_lower for kw in METADATA_KEYWORDS):
            score -= 3

        ratio = _chinese_ratio(df[col])
        if ratio > 0.3:
            score += 2
        elif ratio > 0.05:
            score += 1

        if _avg_len(df[col]) > 5:
            score += 1

        if score >= 1:
            scores[col] = score

    return sorted(scores, key=lambda c: scores[c], reverse=True)


def detect_chinese_columns(df: pd.DataFrame) -> list[str]:
    return [
        col for col in df.columns
        if df[col].dtype in (object, "string") and _chinese_ratio(df[col]) > 0.3
    ]


def build_column_samples(
    df: pd.DataFrame, n_rows: int = 10, max_chars: int = 200
) -> dict[str, list[str]]:
    """First ``n_rows`` non-null values of each text (object/string) column.

    Numeric/float/bool/datetime columns are dropped (dtype-only filter), so GPT
    only sees translatable text columns. Long cells are truncated to ``max_chars``
    to keep token usage bounded.
    """
    samples: dict[str, list[str]] = {}
    for col in df.columns:
        if df[col].dtype not in (object, "string"):
            continue
        vals = df[col].dropna().astype(str).head(n_rows)
        samples[col] = [v[:max_chars] for v in vals]
    return samples
