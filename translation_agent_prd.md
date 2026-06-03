# PRD: Multi-Language CSV Translation Agent

## 1. Product Goal

Build a **chat-based AI translation agent** that allows users to upload a CSV file containing Chinese content, describe in natural language which column(s) they want translated and into which target language(s), preview the translated result, and export a new translated CSV file.

This project is designed to satisfy the assessment requirement: users can upload a CSV, specify one or more target languages through chat, let the system identify translatable content, and generate a new CSV containing both original and translated content. The solution should support at least 100 rows of source content and prioritize practical problem-solving over over-engineered implementation.

## 2. Core User Problem

Users often have CSV files with product reviews, survey responses, titles, descriptions, or comments in Chinese and need a fast way to translate selected columns into one or more languages without manually editing spreadsheets or configuring complex translation tools.

The agent should make the process feel simple:

> “Upload CSV → Tell the agent what to translate → Preview result → Export translated CSV.”

## 3. Target User

Primary user:
- Business, product, operations, or localization team member who works with multilingual CSV content.

User characteristics:
- May not know column names exactly.
- May describe translation needs in natural language.
- Wants quick preview before downloading.
- Needs confidence that the exported CSV preserves the original data.

## 4. Key Requirements

### Must Have

1. **CSV Upload**
   - User can upload a `.csv` file.
   - System parses headers and rows.
   - System shows basic file summary:
     - file name
     - number of rows
     - number of columns
     - detected candidate text columns

2. **Chat-Based Instruction**
   - User can type instructions such as:
     - “Translate the review column to Japanese.”
     - “Translate title and description into French and German.”
     - “Translate all Chinese text columns into English.”
   - AI extracts:
     - source column(s)
     - target language(s)
     - whether to auto-detect columns or use explicit columns

3. **Content Column Identification**
   - If user explicitly names columns, validate that they exist.
   - If user says “Chinese content” or “all text columns,” infer candidate columns based on:
     - column names
     - text density
     - Chinese character ratio
     - sample values
   - Ask for clarification only when ambiguity is high.

4. **Translation Execution**
   - Translate selected cells into target language(s).
   - Preserve all original columns.
   - Add new translated columns using a clear naming convention:
     - `review_ja`
     - `review_fr`
     - `description_en`
   - Empty cells remain empty.
   - Non-text cells are not translated.

5. **Preview Before Export**
   - Show a preview table before download.
   - Preview should include:
     - original selected column(s)
     - translated column(s)
     - first 5–20 translated rows
   - User can confirm, revise language/column selection, or export.

6. **CSV Export**
   - User can download a new CSV file.
   - Output contains:
     - all original columns
     - translated columns for each target language
   - CSV encoding should support multilingual text, preferably UTF-8 with BOM if targeting Excel compatibility.

7. **Minimum Scale**
   - Must support at least 100 rows.
   - Should be designed to handle larger files through batching, progress tracking, and resumable partial results.

## 5. Nice-to-Have Features

- Let user choose whether to translate all rows or only a row range.
- Let user choose formal vs. casual tone.
- Let user provide glossary terms.
- Let user retry failed rows only.
- Let user view estimated token/cost before full translation.
- Let user export an error report for failed cells.

## 6. User Interaction Flow

### Step 1: Landing Page

The interface should clearly communicate the workflow:

**Upload CSV → Chat Instructions → Preview → Download**

UI elements:
- File uploader
- Chat input
- File summary card
- Candidate column list
- Translation preview area
- Export button

### Step 2: Upload CSV

After upload, the app parses the CSV and displays:

```text
Uploaded: customer_reviews.csv
Rows: 2,438
Columns: id, review_text, product_name, rating, created_at
Detected text columns: review_text, product_name
```

The agent responds:

```text
I found 2 likely text columns: review_text and product_name.
Tell me which column you want to translate and the target language(s).
For example: “Translate review_text into Japanese and French.”
```

### Step 3: User Gives Natural Language Instruction

Example user input:

```text
Translate the review_text column into Japanese and Korean.
```

The agent parses this into structured intent:

```json
{
  "columns": ["review_text"],
  "target_languages": ["Japanese", "Korean"],
  "language_codes": ["ja", "ko"],
  "row_scope": "all_rows"
}
```

The app shows a confirmation summary:

```text
I will translate:
- Column: review_text
- Target languages: Japanese, Korean
- Rows: all 2,438 rows
```

### Step 4: Sanity Check Before Translation

Before running translation, the system checks:

- Does the selected column exist?
- Does the target language exist in the supported language map?
- Are there non-empty values to translate?
- Is the file size within supported limits?
- Are duplicate output column names possible?
- Is the OpenAI API key available server-side?

If checks pass, translation starts.

### Step 5: Translation Progress

For large files, the UI should show:

```text
Translating 2,438 rows...
Batch 4 / 25 completed
Successful cells: 400
Failed cells: 0
```

The system should process data in batches instead of sending the full CSV at once.

### Step 6: Preview Result

After translation, show preview:

| row | review_text | review_text_ja | review_text_ko |
|---:|---|---|---|
| 1 | 这个产品很好用 | この商品はとても使いやすいです | 이 제품은 사용하기 매우 좋습니다 |
| 2 | 发货很快 | 배송이 빨랐습니다 | 배송이 빨랐습니다 |

User can then:
- Download CSV
- Change target language
- Translate another column
- Retry failed rows

### Step 7: Export

The app creates a translated CSV with original and translated columns:

```text
id,review_text,rating,review_text_ja,review_text_ko
1,这个产品很好用,5,この商品はとても使いやすいです,이 제품은 사용하기 매우 좋습니다
```

## 7. Proposed Tech Stack

### Recommended Demo Stack

**Frontend / App Framework**
- Streamlit
- Reason: fastest for assessment demo, supports file upload, chat UI, data preview, progress bars, and download buttons.

**Backend Logic**
- Python
- Pandas for CSV parsing and output generation
- Pydantic for structured instruction parsing and validation

**LLM / Translation**
- OpenAI API
- Use structured output for intent extraction.
- Use batched translation calls for translation execution.

**Deployment**
- Streamlit Community Cloud, Render, Railway, or Hugging Face Spaces.
- API key should be stored as environment variable or app secret, never exposed in frontend code.

### Optional More Polished Stack

If building a custom web app:

**Frontend**
- Next.js + Tailwind CSS

**Backend**
- FastAPI

**Storage**
- Temporary local storage or object storage for large files

**Deployment**
- Vercel for frontend
- Render/Railway/Fly.io for backend
- Environment variable for OpenAI API key

For the assessment, Streamlit is likely the best choice because it allows faster delivery while still demonstrating product thinking.

## 8. System Architecture

```text
User
  |
  v
Streamlit Chat UI
  |
  |-- Upload CSV
  |-- Enter natural language instruction
  |
  v
CSV Parser + File Profiler
  |
  |-- Validate CSV
  |-- Detect candidate text columns
  |-- Show file summary
  |
  v
Instruction Parser Agent
  |
  |-- Extract target columns
  |-- Extract target languages
  |-- Resolve ambiguity
  |
  v
Sanity Check Layer
  |
  |-- Column validation
  |-- Language validation
  |-- Row count/file size validation
  |-- Empty cell handling
  |
  v
Translation Engine
  |
  |-- Batch rows
  |-- Translate selected cells
  |-- Retry failed batches
  |-- Preserve row alignment
  |
  v
Preview + Export Layer
  |
  |-- Show translated preview
  |-- Generate output CSV
  |-- Download translated file
```

## 9. Agent Responsibilities

The agent should not only translate. It should coordinate the workflow.

### Agent Role

The translation agent should:

1. Understand user intent from chat.
2. Identify selected source column(s).
3. Identify target language(s).
4. Confirm unclear instructions.
5. Trigger translation only after validation.
6. Explain errors in user-friendly language.
7. Provide preview and export options.

### Example Agent Messages

After upload:

```text
I detected 5 columns and 126 rows. The likely text columns are `title` and `description`.
Which column should I translate, and into what language?
```

After user instruction:

```text
Got it — I’ll translate `description` into Japanese and French.
I’ll create two new columns: `description_ja` and `description_fr`.
```

If ambiguous:

```text
I found multiple possible text columns: `title`, `description`, and `comment`.
Which one should I translate?
```

If successful:

```text
Translation completed. Please review the preview below before downloading the final CSV.
```

## 10. Data Processing Design

### CSV Loading

Use `pandas.read_csv()` with robust handling:

- Try UTF-8 first.
- Fall back to UTF-8-SIG or other common encodings if needed.
- Validate that file has headers.
- Reject empty files.
- Warn if row count is very large.

### Candidate Text Column Detection

Use simple heuristics:

- Column name contains keywords:
  - `text`
  - `content`
  - `comment`
  - `description`
  - `title`
  - `review`
  - `message`
- Cell values are mostly strings.
- Average text length is above a small threshold.
- Chinese character ratio is high.
- Column is not likely metadata:
  - `id`
  - `uuid`
  - `date`
  - `status`
  - `rating`
  - `price`

### Translation Output Naming

Recommended format:

```text
{source_column}_{language_code}
```

Examples:

```text
review_ja
review_fr
description_en
```

If the output column already exists, use:

```text
review_ja_v2
```

or ask user whether to overwrite.

## 11. Large File Handling

Even though the assessment only requires at least 100 rows, the system should be designed for larger files.

### Key Strategies

1. **Batch Translation**
   - Translate 20–50 rows per request.
   - Avoid sending the entire CSV to the model.

2. **Progress Tracking**
   - Show progress by batch.
   - Display completed rows and failed rows.

3. **Partial Failure Recovery**
   - If one batch fails, retry it.
   - If retry still fails, mark those rows as failed instead of stopping the entire job.

4. **Row Alignment**
   - Always preserve original row index.
   - Translation result should map back to the exact original row.

5. **Token/Size Guardrails**
   - Limit max characters per cell.
   - Truncate only with user warning, or skip overly long cells and flag them.

6. **Caching**
   - Optional: cache translations for repeated identical values.
   - Useful for product names, categories, or repeated survey answers.

7. **Memory Safety**
   - Avoid loading unnecessary copies of large DataFrames.
   - For very large files, consider chunk-based CSV processing.

## 12. Sanity Checks

### File-Level Checks

- File is uploaded.
- File extension is `.csv`.
- File is not empty.
- File has valid headers.
- File has at least one row.
- File has at least one likely text column.
- File size does not exceed configured limit.

### Instruction-Level Checks

- Target language is provided.
- Target language is supported or mappable.
- Selected columns exist.
- Selected columns contain non-empty values.
- User instruction is not contradictory.

### Translation-Level Checks

- Each translated batch returns the expected number of rows.
- Output JSON from LLM is parseable.
- Translated values are strings.
- Empty input cells remain empty.
- No original columns are deleted.
- Row count remains unchanged.

### Export-Level Checks

- Output CSV row count equals input CSV row count.
- Output contains original content and translated content.
- Output column names are unique.
- File encoding supports multilingual characters.

## 13. Error Handling

### CSV Parse Error

User-facing message:

```text
I couldn’t read this CSV. Please check that it is a valid CSV file with headers.
```

System behavior:
- Show technical reason in expandable debug area.
- Do not crash app.

### Missing Column

User-facing message:

```text
I couldn’t find a column named `review`. I found these columns instead: `review_text`, `rating`, `created_at`.
Did you mean `review_text`?
```

System behavior:
- Suggest closest matching columns.

### Missing Target Language

User-facing message:

```text
I can identify the column, but I don’t know which language to translate into.
Please specify a target language, such as Japanese, French, or English.
```

### Translation API Error

User-facing message:

```text
Translation failed for one batch. I retried it, but it still failed.
The failed rows are marked in the preview and can be retried.
```

System behavior:
- Retry with exponential backoff.
- Continue other batches if possible.
- Store failed row indexes.

### Large File Warning

User-facing message:

```text
This file has 25,000 rows, so translation may take longer.
I’ll process it in batches and show progress as it runs.
```

### Invalid Output From Model

System behavior:
- Retry with stricter prompt.
- Validate output schema.
- If still invalid, mark batch as failed.

## 14. Prompting Strategy

Use two LLM tasks:

### Task 1: Instruction Parsing

Input:
- User message
- CSV column names
- Candidate text columns

Output schema:

```json
{
  "columns": ["review_text"],
  "target_languages": ["Japanese", "French"],
  "language_codes": ["ja", "fr"],
  "needs_clarification": false,
  "clarification_question": null
}
```

### Task 2: Batch Translation

Input:
- Source language hint: Chinese
- Target language
- List of row IDs and source texts

Output schema:

```json
{
  "translations": [
    {
      "row_id": 0,
      "translated_text": "..."
    },
    {
      "row_id": 1,
      "translated_text": "..."
    }
  ]
}
```

Important prompt rules:
- Preserve meaning.
- Do not summarize.
- Do not add extra explanation.
- Keep proper nouns when appropriate.
- Return valid JSON only.
- Preserve row IDs exactly.

## 15. Codebase Structure

Recommended structure:

```text
translation-agent/
  README.md
  requirements.txt
  .env.example
  app.py

  src/
    config.py
    csv_loader.py
    column_detector.py
    intent_parser.py
    translator.py
    validators.py
    exporter.py
    ui_components.py
    errors.py

  tests/
    test_csv_loader.py
    test_column_detector.py
    test_intent_parser.py
    test_translator.py
    test_exporter.py

  sample_data/
    sample_chinese_reviews.csv
```

### File Responsibilities

#### `app.py`

Main Streamlit app:
- file upload
- chat interface
- session state
- preview table
- download button

#### `src/csv_loader.py`

Handles:
- reading CSV
- encoding fallback
- basic file profiling
- row/column summary

#### `src/column_detector.py`

Handles:
- candidate text column detection
- Chinese text ratio
- metadata column exclusion

#### `src/intent_parser.py`

Handles:
- natural language instruction parsing
- target language extraction
- column matching
- clarification detection

#### `src/translator.py`

Handles:
- batch translation
- LLM API calls
- retry logic
- response schema validation
- translation caching

#### `src/validators.py`

Handles:
- sanity checks
- file validation
- column validation
- target language validation
- output validation

#### `src/exporter.py`

Handles:
- translated column insertion
- output column naming
- CSV generation
- UTF-8/Excel-safe export

#### `src/ui_components.py`

Handles:
- file summary card
- progress indicator
- preview table
- error display

#### `src/errors.py`

Defines:
- user-friendly error classes
- recoverable vs. fatal errors

## 16. UI/Product Design Quality

The UI should feel like a guided workflow, not just a raw script.

### Recommended Layout

```text
Header:
  Multi-Language CSV Translation Agent

Left/Main Area:
  Chat interface
  File upload
  Agent responses

Right/Sidebar:
  File summary
  Detected columns
  Selected translation settings
  Progress status

Bottom:
  Preview table
  Download button
```

### Product Quality Details

- Use clear step labels:
  - 1. Upload
  - 2. Tell AI what to translate
  - 3. Preview
  - 4. Download
- Show selected translation plan before running.
- Show progress during translation.
- Show human-readable error messages.
- Make download button disabled until translation succeeds.
- Keep original and translated columns visually grouped in preview.
- Avoid exposing raw API errors to user unless inside debug mode.

## 17. Key Trade-Offs

### Streamlit vs. Custom Frontend

Decision:
- Use Streamlit for the assessment demo.

Reason:
- Faster implementation.
- Built-in upload, chat, table, progress, and download components.
- Best fit for 1–2 hour expected effort.

Trade-off:
- Less visual customization than Next.js.
- UI may feel less polished unless carefully structured.

### LLM Translation vs. Traditional Translation API

Decision:
- Use OpenAI API for both intent parsing and translation.

Reason:
- Natural language instruction handling is central to the agent experience.
- One model can handle both parsing and translation.

Trade-off:
- Higher cost and latency than dedicated translation APIs.
- Requires careful schema validation.

### Auto-Detect Columns vs. Ask User

Decision:
- Auto-detect likely text columns, but confirm when ambiguous.

Reason:
- Makes the product feel intelligent.
- Reduces user effort.

Trade-off:
- Incorrect detection can cause wrong translations, so validation and preview are important.

### Full Translation Before Preview vs. Sample Preview First

Recommended decision:
- For small files, translate all rows then preview.
- For large files, translate a small sample first and ask user to confirm before full run.

Reason:
- Reduces wasted API cost.
- Improves user trust.

## 18. Acceptance Criteria

The demo is successful if:

1. User can upload a CSV.
2. App displays a file summary.
3. User can instruct the agent through chat.
4. App correctly identifies target column(s) and target language(s).
5. App translates at least 100 rows.
6. App creates new translated columns.
7. App preserves original columns.
8. User can preview translated results before export.
9. User can download a translated CSV.
10. App handles common errors gracefully.
11. API key is kept server-side and never exposed to the browser.
12. The product summary clearly explains technical architecture and trade-offs.

## 19. Suggested Demo Script

1. Upload `sample_chinese_reviews.csv`.
2. Agent detects columns and asks what to translate.
3. User says:

```text
Translate the review_text column into Japanese and French.
```

4. Agent confirms:

```text
I will translate review_text into Japanese and French and create review_text_ja and review_text_fr.
```

5. Click translate.
6. Show progress.
7. Show preview table.
8. Download translated CSV.
9. Open exported CSV to show original and translated columns.

## 20. Summary

This product should demonstrate both AI product thinking and practical technical execution. The key is not only calling a translation model, but designing a reliable workflow around it: natural language instruction parsing, column detection, validation, batch processing, preview, export, and graceful error recovery.

For a 1–2 hour assessment, the recommended implementation is a Streamlit app with a clean guided workflow, Pandas-based CSV processing, OpenAI-powered intent parsing and translation, batch processing for scale, and careful sanity checks before export.
