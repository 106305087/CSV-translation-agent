# CSV Translation Agent 🌐

A conversational web app that translates the text columns of a CSV file into one or more
languages using the OpenAI API. Upload a CSV, tell the agent in plain language what you
want translated, confirm the auto-filled selections, and download a CSV with the
translations appended as new columns.

Built with **Streamlit** (UI), **pandas** (data), **OpenAI `gpt-4o-mini`** (intent +
translation), and **Pydantic** (output validation).

---

## Table of contents

1. [What it does](#what-it-does)
2. [Quick start](#quick-start)
3. [How a translation flows through the app](#how-a-translation-flows-through-the-app)
4. [Architecture overview](#architecture-overview)
5. [Module & function reference](#module--function-reference)
6. [The two LLM calls in detail](#the-two-llm-calls-in-detail)
7. [Configuration](#configuration)
8. [Error handling model](#error-handling-model)
9. [Extending the app](#extending-the-app)
10. [Verifying changes](#verifying-changes)
11. [Project layout](#project-layout)

---

## What it does

- **Upload** a CSV (any common encoding — UTF-8, GBK, Big5, etc. are auto-detected).
- **Describe** what to translate in natural language, e.g. *"translate the customer
  reviews into Japanese and Korean."*
- The agent uses GPT to figure out **which columns** you mean (by looking at real sample
  data, not just column names) and **which languages** you want.
- It **pre-fills dropdowns** with its guess. You adjust if needed and click **Start
  Translating**.
- Translation runs in **concurrent batches** with progress reporting and automatic retries.
- **Download** the result: your original CSV with new `<column>_<langcode>` columns
  appended (e.g. `review_text_ja`).

### Key design choice: data-aware column detection

Column detection is **GPT-driven and content-aware**. When you type your instruction, the
app samples the first 10 rows of each text column and sends those samples (plus your
instruction) to GPT, which decides which columns you're focusing on. This replaced an
older keyword-heuristic detector (still present in the code as
`detect_text_columns`/`detect_chinese_columns` but no longer used — see
[`src/column_detector.py`](src/column_detector.py)).

---

## Quick start

> **Requires Python 3.10+** (the code uses `X | None` union syntax). On this machine use
> `python3` — the default `python` is anaconda 3.9 and will fail to import.

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your OpenAI key
cp .env.example .env
#    edit .env and set OPENAI_API_KEY=sk-...

# 3. Run the app
python3 -m streamlit run app.py
```

The app opens at **http://localhost:8501**. Try it with the included
[`sample_data/sample_chinese_reviews.csv`](sample_data/sample_chinese_reviews.csv) — upload
it, then type *"translate the reviews to Japanese."*

---

## How a translation flows through the app

```
┌─────────────┐   upload    ┌──────────────────┐
│   Browser   │ ──────────▶ │  load_csv()      │  multi-encoding read,
│ (Streamlit) │             │  csv_loader.py   │  validation → (df, profile)
└─────────────┘             └──────────────────┘
       │ types instruction
       ▼
┌──────────────────────────┐   samples    ┌──────────────────────────┐
│ build_column_samples(df) │ ───────────▶ │ parse_intent()           │  GPT call #1:
│ column_detector.py       │              │ intent_parser.py         │  columns + languages
│ dtype-filtered 10 rows   │              └──────────────────────────┘  → IntentResult
└──────────────────────────┘                         │
       │ prefilled dropdowns + "Start Translating"   ▼
       ▼                              ┌──────────────────────────┐
┌──────────────────────────┐          │ validate_columns()       │  guardrails
│ translate_column()       │          │ validate_languages()     │
│ translator.py            │          └──────────────────────────┘
│ GPT call #2, batched     │
│ + concurrent + retries   │
└──────────────────────────┘
       │ pd.Series per (column, language)
       ▼
┌──────────────────────────┐          ┌──────────────────────────┐
│ build_export_csv()       │ ───────▶ │ Download Translated CSV  │
│ exporter.py              │          │ (utf-8-sig bytes)        │
└──────────────────────────┘          └──────────────────────────┘
```

---

## Architecture overview

The app is a thin Streamlit orchestration layer ([`app.py`](app.py)) over a set of small,
single-responsibility modules in [`src/`](src/). All user-visible failures funnel through
one exception type (`UserFacingError`), and both LLM calls return strict JSON validated by
Pydantic models.

| Concern | Module | Entry point(s) |
|---|---|---|
| UI, chat, session state, orchestration | `app.py` | (Streamlit script) |
| Load & validate the CSV | `src/csv_loader.py` | `load_csv` |
| Pick sample data for the LLM | `src/column_detector.py` | `build_column_samples` |
| Understand the user's request | `src/intent_parser.py` | `parse_intent`, `IntentResult` |
| Do the translation | `src/translator.py` | `translate_column` |
| Build the downloadable file | `src/exporter.py` | `build_export_csv` |
| Guardrails | `src/validators.py` | `validate_*` |
| Config & secrets | `src/config.py` | `get_openai_api_key`, constants |
| Error types | `src/errors.py` | `UserFacingError`, `RecoverableError` |

---

## Module & function reference

### `app.py` — UI & orchestration

The Streamlit entry point. Responsibilities:

- **Session state** (`_init_state`): holds `df`, `profile`, `chat_history`, `intent`,
  `translated_cols`, `export_bytes`, UI flags (`awaiting_selection`, `translating`), and
  widget prefills (`prefill_cols`, `prefill_langs`).
- **Prefill transfer** (top of script): copies NL-derived prefills into the multiselect
  widget keys *before* the widgets render — necessary because Streamlit ignores a widget's
  `default=` once its key already exists in `session_state`.
- **Upload handling**: calls `load_csv` + `validate_file`, resets state, and posts a
  greeting that reports row/column counts (no column guesses — detection happens later).
- **Chat input handling**: on each user message, builds column samples and calls
  `parse_intent`. If the model needs clarification, it asks; otherwise it validates and
  pre-fills the column/language dropdowns.
- **`_run_translation()`**: iterates each column's own target languages
  (`for ct in column_targets: for lang in ct.language_codes`), calls `translate_column` with
  progress callbacks that drive a `st.progress` bar, accumulates results, and builds the
  export via `build_export_csv`. (No `columns × languages` cartesian product — each column
  is translated only into the languages requested for it.)
- **Results panel**: previews the first 20 rows and offers a download button + "upload
  another document" reset.

### `src/csv_loader.py`

- **`load_csv(file_bytes, filename) -> (pd.DataFrame, dict)`** — Tries encodings
  `utf-8, utf-8-sig, gb18030, gbk, big5, latin-1` in order until one parses. **Skips leading
  title/banner rows**: a first pass (`header=None`) locates the real header via
  `_find_header_row` (the first row roughly as wide as the table), then it re-reads from that
  row so pandas still infers column dtypes. Blank `Unnamed:` columns from a title row's
  trailing commas are dropped. Raises `UserFacingError` for unreadable/empty/header-only
  files or files over `MAX_FILE_ROWS`. Returns the dataframe plus a `profile` dict:
  `{filename, rows, columns, col_names}`.
- **`_find_header_row(raw, max_scan=20)`** — Returns the index of the header row, treating
  narrow leading rows (e.g. a report title) as preamble to skip.

### `src/column_detector.py`

- **`build_column_samples(df, n_rows=10, max_chars=200) -> dict[str, list[str]]`**
  ⭐ *(active)* — Returns the first `n_rows` non-null values of each **text** column
  (`object`/`string` dtype only; numeric/float/bool/datetime are dropped). Long cells are
  truncated to `max_chars` to bound token usage. This is the data GPT sees when deciding
  which columns to translate.
- **`detect_text_columns(df)` / `detect_chinese_columns(df)`** *(legacy, unused)* — The
  original keyword + Chinese-ratio heuristic. Kept for reference; **not called** anywhere.
- Helpers `_chinese_ratio`, `_avg_len` support only the legacy detectors.

### `src/intent_parser.py`

- **`ColumnTarget` (Pydantic)** — `column: str`, `target_languages: list[str]`,
  `language_codes: list[str]`. One column mapped to its own languages.
- **`IntentResult` (Pydantic)** — `column_targets: list[ColumnTarget]`,
  `needs_clarification: bool`, `clarification_question: str | None`. The per-column mapping
  prevents a `columns × languages` cartesian product (so "reviews→Korean, names→French"
  stays mapped).
- **`parse_intent(user_message, col_names, column_samples, previous_intent=None, chat_history=None) -> IntentResult`**
  — Builds a system prompt embedding the **sample data block** + supported languages +
  any previously-known mapping, sends the full chat history as multi-turn messages, and
  asks GPT (JSON mode) to produce a **per-column** language mapping. Carries forward prior
  mappings, merges on continuity words ("also", "add"), replaces on ("instead", "only"), and
  only asks for clarification when no column can be paired with a language. See
  [the LLM-call section](#the-two-llm-calls-in-detail) for the exact prompt/messages.

### `src/translator.py`

- **`translate_column(df, col, lang_code, target_language, progress_cb=None, on_batch_start=None) -> pd.Series`**
  — Translates one column into one language. Filters out empty/NaN rows, splits the
  remaining rows into batches of `BATCH_SIZE`, runs up to `MAX_CONCURRENT_BATCHES` batches
  concurrently via a `ThreadPoolExecutor`, and reassembles a `pd.Series` aligned to the
  original index (untranslated/empty rows stay empty). Raises `UserFacingError` listing any
  rows that permanently failed.
- **`_translate_batch(...)`** — One GPT call for a batch of `{row_id, text}` rows; validates
  the response with `validate_translation_output`.
- **`_run_batch(...)`** — Wraps `_translate_batch` with retry logic: honors the
  `retry-after` header on `RateLimitError`, retries generic `RecoverableError`s up to 3×
  with exponential backoff, and on permanent failure records the row ids and leaves them empty.
- **`TranslationItem` / `TranslationBatch` (Pydantic)** — Shape of the batch response.

### `src/exporter.py`

- **`build_export_csv(df, translated_cols) -> bytes`** — Copies the original dataframe,
  appends each translated `pd.Series` as a new column (using `_unique_col_name` to avoid
  collisions, e.g. `review_text_ja_v2`), validates row/column integrity via
  `validate_export`, and serializes to `utf-8-sig` CSV bytes (opens cleanly in Excel).

### `src/validators.py`

Pure guardrail functions, each raising `UserFacingError` on violation:

- **`validate_file(df)`** — non-empty, within row limit, has columns.
- **`validate_columns(selected, df_cols)`** — every selected column exists; suggests close
  matches via `difflib` when one doesn't.
- **`validate_languages(codes)`** — every code is in `LANGUAGE_MAP`.
- **`validate_translation_output(row_ids, translations)`** — the batch response covers all
  requested `row_id`s and every `translated_text` is a string.
- **`validate_export(original_df, output_df)`** — row count preserved and no original column
  dropped.

### `src/config.py`

- **`get_openai_api_key()`** — reads `OPENAI_API_KEY` from `.env` (via `python-dotenv`,
  `override=True`), raising `UserFacingError` if missing.
- Constants: `BATCH_SIZE`, `MAX_CONCURRENT_BATCHES`, `MAX_FILE_ROWS`, `MAX_FILE_SIZE_MB`.
- **`LANGUAGE_MAP`** — 30 supported languages → ISO codes.
- `TEXT_COLUMN_KEYWORDS` / `METADATA_KEYWORDS` — used only by the legacy heuristic.

### `src/errors.py`

- **`UserFacingError`** — anything that should be shown to the user; caught in `app.py`.
- **`RecoverableError(UserFacingError)`** — signals "retry this batch before giving up."

---

## The two LLM calls in detail

Both use `model="gpt-4o-mini"`, `response_format={"type": "json_object"}`, `temperature=0`,
and validate the JSON with a Pydantic model.

### Call #1 — Intent parsing (`parse_intent`)

**Message structure** (multi-turn so short replies like *"Japanese"* resolve against
earlier questions):

```python
messages = [
    {"role": "system",  "content": <prompt with sample data, languages, prior selection>},
    *chat_history[-8:],                       # last ~4 exchanges
    {"role": "user",    "content": user_message},  # e.g. "translate the reviews to Japanese"
]
```

**System prompt** embeds a sample-data block built from `build_column_samples`:

```
Text columns with sample values (first 10 rows each):
- review_text: "物流速度很快", "防水效果很好", "价格实惠" ...
- product_name: "智能音箱", "便携充电宝", "智能手表" ...

All CSV columns: id, review_text, product_name, rating, created_at
Supported languages and codes: chinese (zh), english (en), japanese (ja), ...
```

…followed by rules instructing the model to map **each** column to only the languages
requested for it (no cross-application), pick columns from *both* the instruction and the
sample content, map languages to ISO codes, carry forward known mappings, and only ask for
clarification when no column can be paired with a language.

**Returns** an `IntentResult` whose `column_targets` is a list of
`{column, target_languages, language_codes}` — e.g. `review_text → [Korean]`,
`product_name → [French]`.

### Call #2 — Translation (`_translate_batch`)

```python
messages = [
    {"role": "system", "content": "Translate each text from Chinese to <language>. ..."},
    {"role": "user",   "content": '{"rows": [{"row_id": 0, "text": "好吃"}, ...]}'},
]
# expects: {"translations": [{"row_id": 0, "translated_text": "..."}, ...]}
```

Each batch is independently validated, retried, and merged back by `row_id`.

---

## Configuration

All in [`src/config.py`](src/config.py):

| Constant | Default | Meaning |
|---|---|---|
| `BATCH_SIZE` | 50 | rows per translation API call |
| `MAX_CONCURRENT_BATCHES` | 5 | parallel batches per column/language |
| `MAX_FILE_ROWS` | 50,000 | upload row limit |
| `MAX_FILE_SIZE_MB` | 50 | upload size limit |
| `LANGUAGE_MAP` | 30 langs | language name → ISO code |

Secrets: `OPENAI_API_KEY` in `.env` (see `.env.example`).

---

## Error handling model

- Raise **`UserFacingError`** for anything the user should read; `app.py` catches it and
  renders it in the chat (or as `st.error`).
- Raise **`RecoverableError`** inside translation to mean "transient — retry this batch."
  `_run_batch` retries before the error ever reaches the user.
- Rate limits are handled specially: the `retry-after` response header drives the sleep.
- Rows that fail permanently are **left empty** rather than aborting the whole job, and the
  affected row ids are reported.

---

## Extending the app

- **Add a language** → add an entry to `LANGUAGE_MAP` in `src/config.py`. It immediately
  appears in the dropdown and is accepted by `validate_languages`.
- **Translate from a non-Chinese source** → the translation system prompt in
  `src/translator.py` (`_TRANSLATION_SYSTEM`) hardcodes "from Chinese." Generalize it (e.g.
  detect or pass a source language) if needed.
- **Tune throughput / cost** → adjust `BATCH_SIZE` and `MAX_CONCURRENT_BATCHES`.
- **Change column-detection behavior** → edit the prompt/rules in
  `src/intent_parser.py` and/or the sampling in `build_column_samples`. (Don't re-enable the
  legacy heuristic unless that's the explicit goal.)

---

## Verifying changes

```bash
# Compile-check everything
python3 -m py_compile app.py src/*.py

# Unit-check the sample builder (no API needed) — numeric/id columns should be dropped
python3 -c "
import pandas as pd
from src.column_detector import build_column_samples
df = pd.DataFrame({'id':[1,2], 'rating':[4,5], 'review_text':['好吃','服務好']})
print(build_column_samples(df))   # -> {'review_text': ['好吃','服務好']}
"

# End-to-end (needs OPENAI_API_KEY)
python3 -m streamlit run app.py
# upload sample_data/sample_chinese_reviews.csv, type "translate the reviews to Japanese",
# confirm review_text (not id/rating) is pre-filled, run, and download.
```

---

## Project layout

```
app.py                      Streamlit UI + orchestration
requirements.txt            streamlit, pandas, pydantic, openai, python-dotenv
.env.example                template for OPENAI_API_KEY
CLAUDE.md                   guidance for Claude Code
src/
  config.py                 env/API key, constants, LANGUAGE_MAP
  csv_loader.py             load_csv (encoding fallback + validation)
  column_detector.py        build_column_samples (active) + legacy heuristic (unused)
  intent_parser.py          parse_intent + IntentResult (GPT intent extraction)
  translator.py             translate_column (batched/concurrent/retry) + Pydantic models
  exporter.py               build_export_csv
  validators.py             file/column/language/output/export guardrails
  errors.py                 UserFacingError, RecoverableError
sample_data/
  sample_chinese_reviews.csv  example input
translation_agent_prd.md    product requirements document
```
