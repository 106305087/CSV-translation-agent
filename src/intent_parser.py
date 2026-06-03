import json
from openai import OpenAI
from pydantic import BaseModel
from src.config import get_openai_api_key, LANGUAGE_MAP
from src.errors import UserFacingError


class ColumnTarget(BaseModel):
    column: str
    target_languages: list[str]
    language_codes: list[str]


class IntentResult(BaseModel):
    column_targets: list[ColumnTarget]
    needs_clarification: bool
    clarification_question: str | None


_SYSTEM_PROMPT = """\
You are a translation assistant that extracts structured intent from a CSV translation conversation.

The user has uploaded a CSV file. Using the user's instruction and the sample data below, build a
PER-COLUMN mapping: for each column the user wants translated, list the target languages requested
FOR THAT SPECIFIC COLUMN.

Each candidate column is listed below with a numeric index and its real header name. Identify columns
by their CONTENT in the samples (the header names may be meaningless like "1", "2" or even blank):

{sample_block}

Supported languages and codes: {language_list}
{previous_context}
Rules:
- Refer to each column by its INDEX from the list above. NEVER invent a column name or index that is
  not in the list — only the indexes shown above are valid.
- Each entry in "column_targets" maps ONE column index to the languages requested for that column only.
- Do NOT cross-apply one column's language to another column. Example: "translate the reviews into
  Korean and also the product names into French" => the review column -> Korean ONLY, the product-name
  column -> French ONLY (NOT both columns into both languages).
- If the user gives one language for several columns ("translate the reviews and titles into Japanese"),
  give each of those columns that same single language.
- Decide which column the user means from the SAMPLE CONTENT (e.g. "the Chinese reviews" -> the index
  whose sample values are Chinese review sentences; "product names" -> the index whose samples are
  product names).
- Map each language name to its ISO code from the supported list (target_languages and language_codes
  must be the same length and in the same order, per column).
- Use the FULL conversation history to resolve intent — a short reply like "Korean" or an index is
  answering a previous question, not a standalone instruction.
- Carry forward mappings already known from previous context or the conversation; do NOT ask again.
- If the user adds more ("also", "add", "as well", "too"), MERGE: keep existing mappings and either add
  a language to an existing column's list or add a new column index entry.
- If the user explicitly replaces ("instead", "only", "change to"), use the new mapping only.
- Set needs_clarification=true only if NO column can be paired with at least one language after reading
  the full conversation (e.g. the user named a language but no column, or a column but no language). In
  that case still include any partially-known columns (with whatever languages are known, possibly an
  empty list) and ask a specific clarification_question.
- When needs_clarification=false, EVERY column_targets entry must have at least one language.
- Return valid JSON only — no explanation.

Output schema (column_index is an integer from the list above):
{{
  "column_targets": [
    {{"column_index": 2, "target_languages": ["French", "Korean"], "language_codes": ["fr", "ko"]}},
    {{"column_index": 4, "target_languages": ["French"], "language_codes": ["fr"]}}
  ],
  "needs_clarification": false,
  "clarification_question": null
}}
"""


def parse_intent(
    user_message: str,
    col_names: list[str],
    column_samples: dict[str, list[str]],
    previous_intent: "IntentResult | None" = None,
    chat_history: list[dict] | None = None,
) -> IntentResult:
    client = OpenAI(api_key=get_openai_api_key())

    language_list = ", ".join(f"{name} ({code})" for name, code in LANGUAGE_MAP.items())

    # Columns are referred to by index, so meaningless/numeric/blank headers can't be
    # confused with invented names. `sampled_cols[i]` is the real label for index i.
    sampled_cols = list(column_samples.keys())
    if sampled_cols:
        sample_block = "\n".join(
            f'[{i}] header "{col}": '
            + (", ".join(f'"{v}"' for v in column_samples[col]) + " ..." if column_samples[col] else "(empty)")
            for i, col in enumerate(sampled_cols)
        )
    else:
        sample_block = "(no text columns found)"

    col_index = {col: i for i, col in enumerate(sampled_cols)}
    previous_context = ""
    if previous_intent and previous_intent.column_targets:
        lines = []
        for ct in previous_intent.column_targets:
            idx = col_index.get(ct.column)
            label = f"index {idx}" if idx is not None else f'"{ct.column}"'
            langs = ", ".join(ct.target_languages) if ct.target_languages else "(no language yet)"
            lines.append(f"- {label} -> {langs}")
        previous_context = "Known so far (column -> languages):\n" + "\n".join(lines) + "\n"

    system = _SYSTEM_PROMPT.format(
        sample_block=sample_block,
        language_list=language_list,
        previous_context=previous_context,
    )

    # Build multi-turn messages so the LLM sees the full Q&A context
    messages: list[dict] = [{"role": "system", "content": system}]
    if chat_history:
        for msg in chat_history[-8:]:  # last 4 exchanges
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
    except Exception as e:
        raise UserFacingError(
            f"I had trouble understanding your instruction. Please try rephrasing it. (Detail: {e})"
        )

    # Map each returned column_index back to its real header label. Invalid/out-of-range
    # indexes are dropped so the model can never select a column that doesn't exist.
    targets: list[ColumnTarget] = []
    for t in data.get("column_targets", []):
        idx = t.get("column_index")
        col = None
        if isinstance(idx, int) and 0 <= idx < len(sampled_cols):
            col = sampled_cols[idx]
        elif t.get("column") in col_index:  # tolerate a verbatim, exact-match name
            col = t["column"]
        languages = t.get("target_languages", []) or []
        codes = t.get("language_codes", []) or []
        # Skip columns the model left without a language (spurious/partial entries) — the
        # raw conversation still carries the column, so it can be resolved on a later turn.
        if col is None or not codes:
            continue
        targets.append(ColumnTarget(
            column=col,
            target_languages=languages,
            language_codes=codes,
        ))

    return IntentResult(
        column_targets=targets,
        needs_clarification=bool(data.get("needs_clarification", False)),
        clarification_question=data.get("clarification_question"),
    )
