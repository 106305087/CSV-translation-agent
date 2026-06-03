# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A **CSV Translation Agent** — a Streamlit chat app that translates text columns of an
uploaded CSV into one or more languages using the OpenAI API (`gpt-4o-mini`). The user
uploads a CSV, describes in natural language what to translate, confirms the auto-filled
selections, and downloads a CSV with new `<column>_<langcode>` columns appended.

## Run it

```bash
pip install -r requirements.txt          # streamlit, pandas, pydantic, openai, python-dotenv
cp .env.example .env                      # then put a real key in OPENAI_API_KEY
python3 -m streamlit run app.py           # opens on http://localhost:8501
```

- **Python 3.10+ is required.** The code uses `X | None` union syntax. The machine's
  default `python` (anaconda) is 3.9 and will raise `TypeError: unsupported operand type(s)
  for |`. Always use `python3` (3.10.11) here.
- Needs a valid `OPENAI_API_KEY` in `.env` for intent parsing and translation to work.

## Architecture (data flow)

```
app.py (Streamlit UI + orchestration + session_state)
  └─ csv_loader.load_csv()          multi-encoding read → (df, profile)
  └─ column_detector.build_column_samples(df)   dtype-filtered 10-row samples
  └─ intent_parser.parse_intent()   GPT → IntentResult{column_targets:[{column, languages, codes}], clarify}
  └─ translator.translate_column()  batched + concurrent GPT translation per (col, lang)
  └─ exporter.build_export_csv()    appends translated columns → downloadable bytes
  └─ validators.*                   guardrails at every boundary
  └─ errors.UserFacingError         all user-visible failures funnel through this
```

## Key conventions & gotchas

- **`src/column_detector.py` has dead code on purpose.** `detect_text_columns` and
  `detect_chinese_columns` are the *legacy heuristic* detector — kept for reference but
  **no longer called**. Column detection is now GPT-driven via `build_column_samples` +
  `parse_intent`. Do not re-wire the heuristic in without being asked.
- **Column detection happens at instruction time, not upload time.** The upload greeting
  only reports row/column counts; GPT picks columns from real sample data + the user's
  typed instruction inside `parse_intent`.
- **`build_column_samples` is dtype-only filtering**: keeps `object`/`string` columns,
  drops numeric/float/bool/datetime. String IDs/UUIDs survive the filter but GPT skips
  them from the samples.
- **`load_csv` skips title/banner rows.** Spreadsheet exports often start with a title row
  above the real header. `load_csv` does a two-pass read: pass 1 (`header=None`) finds the
  header row via `_find_header_row`, pass 2 re-reads with `skiprows=` so dtype inference is
  preserved. If you change the read, keep both passes — dropping pass 2 makes every column
  `object` and breaks the numeric filter above.
- **Both GPT calls use** `model="gpt-4o-mini"`, `response_format={"type": "json_object"}`,
  `temperature=0`. Outputs are validated with Pydantic models (`IntentResult`,
  `TranslationBatch`).
- **Per-column language mapping.** `IntentResult.column_targets` is a list of
  `ColumnTarget{column, target_languages, language_codes}` — each column carries its OWN
  languages. The translation loop iterates per target (`for ct in column_targets: for lang
  in ct.language_codes`), so "reviews→Korean, names→French" stays mapped. Do NOT reintroduce
  a flat `columns × languages` cartesian product. The confirm UI mirrors this: a column
  multiselect plus one language multiselect per selected column (keys `lang_sel_<column>`).
- **Translation is batched and concurrent**: `BATCH_SIZE=50` rows/call,
  `MAX_CONCURRENT_BATCHES=5` threads (`ThreadPoolExecutor`). Rate limits honor the
  `retry-after` header; generic errors retry up to 3× with exponential backoff. Permanently
  failed rows are left empty and surfaced via `UserFacingError`.
- **Errors:** raise `UserFacingError` for anything the user should see; `RecoverableError`
  (a subclass) signals "retry this batch first." The UI catches `UserFacingError` and shows it.
- **Streamlit state:** widget prefills (`prefill_cols`/`prefill_langs`) are written into
  widget keys (`col_sel_widget`/`lang_sel_widget`) at the top of the script *before* widgets
  render, because Streamlit ignores `default=` once a key exists in `session_state`.
- **Output columns** are named `f"{col}_{lang_code}"`; `exporter._unique_col_name` adds a
  `_v2` suffix on collision. Export encoding is `utf-8-sig` (Excel-friendly).

## Configuration (`src/config.py`)

`BATCH_SIZE`, `MAX_CONCURRENT_BATCHES`, `MAX_FILE_ROWS` (50k), `MAX_FILE_SIZE_MB` (50),
`LANGUAGE_MAP` (30 languages → ISO codes). `TEXT_COLUMN_KEYWORDS`/`METADATA_KEYWORDS` are
only used by the now-unused heuristic.

## Verifying changes

- Quick (no API): `python3 -c "import pandas as pd; from src.column_detector import build_column_samples; ..."`
  to confirm dtype filtering.
- Compile check: `python3 -m py_compile app.py src/*.py`.
- End-to-end: run the app, upload `sample_data/sample_chinese_reviews.csv`, type
  "translate the reviews to Japanese", confirm `review_text` (not `id`/`rating`) prefills.

## Repo layout

```
app.py                 Streamlit UI + orchestration
src/config.py          env/API key, constants, LANGUAGE_MAP
src/csv_loader.py      load_csv (encoding fallback, validation, profile)
src/column_detector.py build_column_samples (active) + heuristic detectors (legacy/unused)
src/intent_parser.py   parse_intent + IntentResult (GPT intent extraction)
src/translator.py      translate_column (batched/concurrent/retry) + Pydantic models
src/exporter.py        build_export_csv
src/validators.py      file/column/language/output/export guardrails
src/errors.py          UserFacingError, RecoverableError
sample_data/           sample_chinese_reviews.csv
translation_agent_prd.md   product requirements doc
```
