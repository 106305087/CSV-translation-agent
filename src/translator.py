import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
import pandas as pd
import openai
from openai import OpenAI
from pydantic import BaseModel
from src.config import get_openai_api_key, BATCH_SIZE, MAX_CONCURRENT_BATCHES
from src.validators import validate_translation_output
from src.errors import UserFacingError, RecoverableError


class TranslationItem(BaseModel):
    row_id: int
    translated_text: str


class TranslationBatch(BaseModel):
    translations: list[TranslationItem]


_TRANSLATION_SYSTEM = """\
You are a professional translator. Translate each text from Chinese to {target_language}.

Rules:
- Preserve the original meaning exactly. Do not summarize or add explanation.
- Keep proper nouns when appropriate.
- Return valid JSON only in this exact format:
  {{"translations": [{{"row_id": <int>, "translated_text": "<string>"}}, ...]}}
- Preserve the row_id values exactly as given.
- Empty strings must be returned as empty strings.
"""


def _get_retry_after(e: openai.RateLimitError) -> float:
    try:
        return float(e.response.headers.get("retry-after", 5))
    except Exception:
        return 5.0


def _translate_batch(
    client: OpenAI,
    rows: list[dict],
    target_language: str,
) -> list[dict]:
    system = _TRANSLATION_SYSTEM.format(target_language=target_language)
    user_content = json.dumps({"rows": rows}, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        translations = data.get("translations", [])
        row_ids = [r["row_id"] for r in rows]
        validate_translation_output(row_ids, translations)
        return translations
    except (UserFacingError, RecoverableError):
        raise
    except Exception as e:
        raise RecoverableError(f"Batch translation failed: {e}")


def _run_batch(
    client: OpenAI,
    rows: list[dict],
    target_language: str,
    results: dict[int, str],
    failed_indices: list[int],
    lock: threading.Lock,
    on_start: Callable[[], None] | None = None,
) -> None:
    if on_start:
        on_start()
    generic_attempts = 0
    while True:
        try:
            translations = _translate_batch(client, rows, target_language)
            with lock:
                for t in translations:
                    results[t["row_id"]] = t["translated_text"]
            return
        except openai.RateLimitError as e:
            time.sleep(_get_retry_after(e))
            continue
        except RecoverableError:
            generic_attempts += 1
            if generic_attempts >= 3:
                break
            time.sleep(2 ** (generic_attempts - 1))
            continue
        except Exception:
            break

    with lock:
        for row in rows:
            failed_indices.append(row["row_id"])
            results[row["row_id"]] = ""


def translate_column(
    df: pd.DataFrame,
    col: str,
    lang_code: str,
    target_language: str,
    progress_cb: Callable[[int, int, int], None] | None = None,
    on_batch_start: Callable[[int, int], None] | None = None,
) -> pd.Series:
    client = OpenAI(api_key=get_openai_api_key())

    non_empty_mask = df[col].notna() & (df[col].astype(str).str.strip() != "")
    source_rows = df.loc[non_empty_mask, col].astype(str)

    results: dict[int, str] = {}
    failed_indices: list[int] = []
    lock = threading.Lock()
    total = len(source_rows)
    completed = 0

    indices = source_rows.index.tolist()
    batches = [
        indices[i : i + BATCH_SIZE]
        for i in range(0, len(indices), BATCH_SIZE)
    ]
    total_batches = len(batches)
    started_count = [0]
    start_lock = threading.Lock()

    def make_on_start():
        def cb():
            with start_lock:
                started_count[0] += 1
                n = started_count[0]
            if on_batch_start:
                on_batch_start(n, total_batches)
        return cb

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        future_to_size = {
            executor.submit(
                _run_batch,
                client,
                [{"row_id": int(idx), "text": source_rows[idx]} for idx in batch],
                target_language,
                results,
                failed_indices,
                lock,
                make_on_start(),
            ): len(batch)
            for batch in batches
        }
        for future in as_completed(future_to_size):
            completed += future_to_size[future]
            if progress_cb:
                with lock:
                    progress_cb(completed, total, len(failed_indices))

    output = pd.Series("", index=df.index, dtype=str)
    for idx, text in results.items():
        output.at[idx] = text

    if failed_indices:
        raise UserFacingError(
            f"Translation completed with {len(failed_indices)} failed row(s) "
            f"(rows: {failed_indices[:10]}{'...' if len(failed_indices) > 10 else ''}). "
            "Failed rows are left empty in the output."
        )

    return output
