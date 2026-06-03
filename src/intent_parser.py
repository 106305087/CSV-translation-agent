import json
from openai import OpenAI
from pydantic import BaseModel
from src.config import get_openai_api_key, LANGUAGE_MAP
from src.errors import UserFacingError


class IntentResult(BaseModel):
    columns: list[str]
    target_languages: list[str]
    language_codes: list[str]
    needs_clarification: bool
    clarification_question: str | None


_SYSTEM_PROMPT = """\
You are a translation assistant that extracts structured intent from a CSV translation conversation.

The user has uploaded a CSV file. Extract:
- which columns to translate (must be from the available columns)
- which target languages (map to ISO codes from the supported list)
- whether clarification is still needed

Available CSV columns: {col_names}
Candidate text columns (most likely to translate): {candidate_cols}
Supported languages and codes: {language_list}
{previous_context}
Rules:
- Only include columns that actually exist in the CSV.
- If user says "all text columns" or "Chinese columns", use the candidate columns.
- Map language names to ISO codes using the supported list.
- Use the FULL conversation history to resolve the intent — a short reply like "Japanese" or "review_text" is answering a previous question, not a standalone instruction.
- If columns are already known from the previous context or conversation, carry them forward. Do NOT ask for them again.
- If languages are already known from the previous context or conversation, carry them forward. Do NOT ask for them again.
- Only set needs_clarification=true if BOTH columns AND languages are still unknown after reading the full conversation.
- If a previous selection exists and the user implies continuity ("also", "add", "as well", "too"), merge: keep previous columns and languages and add the new ones.
- If the user explicitly replaces ("instead", "only", "change to"), use the new values only.
- Return valid JSON only — no explanation.

Output schema:
{{
  "columns": ["col_name"],
  "target_languages": ["Japanese"],
  "language_codes": ["ja"],
  "needs_clarification": false,
  "clarification_question": null
}}
"""


def parse_intent(
    user_message: str,
    col_names: list[str],
    candidate_cols: list[str],
    previous_intent: "IntentResult | None" = None,
    chat_history: list[dict] | None = None,
) -> IntentResult:
    client = OpenAI(api_key=get_openai_api_key())

    language_list = ", ".join(f"{name} ({code})" for name, code in LANGUAGE_MAP.items())
    previous_context = ""
    if previous_intent:
        parts = []
        if previous_intent.columns:
            parts.append(f"- Columns already specified: {', '.join(previous_intent.columns)}")
        if previous_intent.target_languages:
            parts.append(f"- Languages already specified: {', '.join(previous_intent.target_languages)}")
        if parts:
            previous_context = "Known so far:\n" + "\n".join(parts) + "\n"

    system = _SYSTEM_PROMPT.format(
        col_names=", ".join(col_names),
        candidate_cols=", ".join(candidate_cols) if candidate_cols else "(none detected)",
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
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return IntentResult(**data)
    except Exception as e:
        raise UserFacingError(
            f"I had trouble understanding your instruction. Please try rephrasing it. (Detail: {e})"
        )
