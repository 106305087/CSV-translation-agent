import threading
import streamlit as st
import pandas as pd
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from src.csv_loader import load_csv
from src.column_detector import build_column_samples
from src.intent_parser import parse_intent, IntentResult, ColumnTarget
from src.translator import translate_column
from src.exporter import build_export_csv
from src.validators import validate_file, validate_columns, validate_languages
from src.errors import UserFacingError
from src.config import LANGUAGE_MAP

st.set_page_config(
    page_title="CSV Translation Agent",
    page_icon="🌐",
    layout="centered",
)

_WELCOME = (
    "Welcome to **CSV Translation Agent**!\n\n"
    "I can translate text columns in your CSV files into multiple languages. "
    "Here's how it works:\n\n"
    "1. **Upload** a CSV file below\n"
    "2. **Tell me** which column(s) to translate and into what language(s)\n"
    "3. **Adjust** the pre-filled dropdowns if needed, then confirm\n"
    "4. **Download** the translated CSV when done\n\n"
    "Upload your file to get started:"
)


# ── Session state ──────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "df": None,
        "profile": None,
        "chat_history": [],
        "intent": None,
        "translated_cols": {},
        "export_bytes": None,
        "translation_error": None,
        "awaiting_selection": False,
        "translating": False,
        "prefill_targets": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# Transfer NL prefills into widget keys before any widget is instantiated.
# Streamlit ignores `default` when a key already exists in session_state, so we
# write the values here — top of script, before widgets render. `prefill_targets`
# maps each column to its list of (display-name) languages.
if st.session_state.prefill_targets:
    targets = st.session_state.prefill_targets
    st.session_state["col_sel_widget"] = list(targets.keys())
    for col, langs in targets.items():
        st.session_state[f"lang_sel_{col}"] = langs
    st.session_state.prefill_targets = {}


# ── Translation runner ─────────────────────────────────────────────────────────
def _run_translation():
    intent = st.session_state.intent
    df = st.session_state.df
    new_cols: dict[str, pd.Series] = {}

    total_ops = sum(len(ct.language_codes) for ct in intent.column_targets)
    op_idx = 0
    overall_bar = st.progress(0.0, text="Starting translation…")
    status_text = st.empty()
    ctx = get_script_run_ctx()
    bar_pct = [0.0]

    for ct in intent.column_targets:
        col = ct.column
        for lang_code, lang_name in zip(ct.language_codes, ct.target_languages):
            op_idx += 1
            out_col = f"{col}_{lang_code}"

            def make_cb(op, total_op, col_name, lang):
                def cb(done, total, failed):
                    base = (op - 1) / total_op
                    frac = (done / total if total else 1.0) / total_op
                    bar_pct[0] = min(base + frac, 1.0)
                    overall_bar.progress(
                        bar_pct[0],
                        text=f"Translating `{col_name}` → {lang} ({op}/{total_op}) — {done}/{total} rows",
                    )
                    if failed:
                        status_text.caption(f"Failed rows: {failed}")
                return cb

            def make_start_cb(op, total_op, col_name, lang):
                def cb(started, total_batches):
                    add_script_run_ctx(threading.current_thread(), ctx)
                    overall_bar.progress(
                        bar_pct[0],
                        text=f"Translating `{col_name}` → {lang} ({op}/{total_op}) — {started}/{total_batches} batches running…",
                    )
                return cb

            try:
                series = translate_column(
                    df, col, lang_code, lang_name,
                    progress_cb=make_cb(op_idx, total_ops, col, lang_name),
                    on_batch_start=make_start_cb(op_idx, total_ops, col, lang_name),
                )
                new_cols[out_col] = series
            except UserFacingError as e:
                st.warning(str(e))

    overall_bar.progress(1.0, text="All translations complete!")
    status_text.empty()

    if new_cols:
        try:
            accumulated = {**st.session_state.translated_cols, **new_cols}
            export_bytes = build_export_csv(df, accumulated)
            st.session_state.translated_cols = accumulated
            st.session_state.export_bytes = export_bytes
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": (
                    f"Translation complete! Added {len(new_cols)} new column(s): "
                    + ", ".join(f"`{c}`" for c in new_cols)
                    + ". Download the updated CSV below."
                ),
            })
        except UserFacingError as e:
            st.error(str(e))


# ── Main UI ────────────────────────────────────────────────────────────────────
st.title("CSV Translation Agent")

# ── Welcome bubble (always first) — contains uploader when no file loaded ──────
with st.chat_message("assistant"):
    st.markdown(_WELCOME)
    if st.session_state.df is None:
        uploaded = st.file_uploader(
            "CSV file",
            type=["csv"],
            key="uploader",
            label_visibility="collapsed",
        )
    else:
        uploaded = None

# ── Upload handling ────────────────────────────────────────────────────────────
if uploaded is not None:
    file_bytes = uploaded.read()
    if (
        st.session_state.profile is None
        or st.session_state.profile.get("filename") != uploaded.name
        or st.session_state.profile.get("rows") is None
    ):
        try:
            df, profile = load_csv(file_bytes, filename=uploaded.name)
            validate_file(df)

            st.session_state.df = df
            st.session_state.profile = profile
            st.session_state.intent = None
            st.session_state.translated_cols = {}
            st.session_state.export_bytes = None
            st.session_state.translation_error = None
            st.session_state.awaiting_selection = False
            st.session_state.prefill_targets = {}
            for k in [k for k in st.session_state if k == "col_sel_widget" or k.startswith("lang_sel_")]:
                st.session_state.pop(k, None)

            greeting = (
                f"I loaded **{uploaded.name}** — "
                f"**{profile['rows']:,} rows**, **{profile['columns']} columns**.\n\n"
                "**Which column(s) would you like to translate, and into what language(s)?**"
            )
            st.session_state.chat_history = [{"role": "assistant", "content": greeting}]
            st.rerun()

        except UserFacingError as e:
            st.error(str(e))

# ── Chat history ───────────────────────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Persistent CSV preview (always in chat, right after file greeting) ──────────
if st.session_state.df is not None:
    with st.chat_message("assistant"):
        st.dataframe(st.session_state.df.head(5), use_container_width=True)

# ── Selection widget (shown only after NL response populates prefills) ──────────
if st.session_state.awaiting_selection and st.session_state.df is not None:
    profile = st.session_state.profile

    with st.chat_message("assistant"):
        col_sel = st.multiselect(
            "Columns to translate:",
            options=profile["col_names"],
            key="col_sel_widget",
        )
        lang_options = [lang.title() for lang in LANGUAGE_MAP.keys()]

        # One language picker per selected column, so each column maps to its own targets.
        per_col_langs: dict[str, list[str]] = {}
        for col in col_sel:
            per_col_langs[col] = st.multiselect(
                f"Target language(s) for `{col}`:",
                options=lang_options,
                key=f"lang_sel_{col}",
            )

        ready = bool(col_sel) and all(per_col_langs[c] for c in col_sel)
        if st.button("Start Translating", type="primary", disabled=not ready):
            try:
                validate_columns(col_sel, profile["col_names"])
                column_targets = []
                for col in col_sel:
                    lang_sel = per_col_langs[col]
                    lang_codes = [LANGUAGE_MAP[lang.lower()] for lang in lang_sel]
                    validate_languages(lang_codes)
                    column_targets.append(ColumnTarget(
                        column=col,
                        target_languages=lang_sel,
                        language_codes=lang_codes,
                    ))

                st.session_state.intent = IntentResult(
                    column_targets=column_targets,
                    needs_clarification=False,
                    clarification_question=None,
                )
                st.session_state.awaiting_selection = False
                st.session_state.translating = True
                st.rerun()  # rerun first so button is gone before translation starts

            except UserFacingError as e:
                st.error(str(e))

# ── Translation execution (runs after button disables itself via rerun) ─────────
if st.session_state.translating and st.session_state.intent is not None:
    with st.chat_message("assistant"):
        _run_translation()
    st.session_state.translating = False
    st.rerun()

# ── Chat input (always visible while a file is loaded) ─────────────────────────
if st.session_state.df is not None:
    user_input = st.chat_input("Type which column(s) and language(s) to translate…")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Understanding your instruction…"):
                try:
                    intent = parse_intent(
                        user_input,
                        st.session_state.profile["col_names"],
                        build_column_samples(st.session_state.df),
                        previous_intent=st.session_state.intent,
                        chat_history=st.session_state.chat_history,
                    )

                    if intent.needs_clarification:
                        reply = intent.clarification_question or "Could you clarify which column and language to translate into?"
                        st.markdown(reply)
                        st.session_state.chat_history.append({"role": "assistant", "content": reply})
                        st.session_state.intent = intent
                    else:
                        validate_columns(
                            [ct.column for ct in intent.column_targets],
                            st.session_state.profile["col_names"],
                        )
                        validate_languages(
                            [c for ct in intent.column_targets for c in ct.language_codes]
                        )

                        st.session_state.prefill_targets = {
                            ct.column: ct.target_languages for ct in intent.column_targets
                        }
                        st.session_state.awaiting_selection = True

                        reply = (
                            "Got it — I've pre-filled the selections below. "
                            "Adjust if needed, then click **Start Translating**."
                        )
                        st.markdown(reply)
                        st.session_state.chat_history.append({"role": "assistant", "content": reply})
                        st.rerun()

                except UserFacingError as e:
                    err_msg = str(e)
                    st.error(err_msg)
                    st.session_state.chat_history.append({"role": "assistant", "content": f"**Error:** {err_msg}"})

# ── Translation results, download, and start-over ─────────────────────────────
if st.session_state.translated_cols and st.session_state.export_bytes and not st.session_state.awaiting_selection:
    st.subheader("Preview (first 20 rows)")
    df = st.session_state.df
    intent = st.session_state.intent

    preview_cols = []
    for ct in intent.column_targets:
        col = ct.column
        if col in df.columns and col not in preview_cols:
            preview_cols.append(col)
        for lc in ct.language_codes:
            out = f"{col}_{lc}"
            if out in st.session_state.translated_cols and out not in preview_cols:
                preview_cols.append(out)

    base_cols = [c for c in preview_cols if c in df.columns]
    preview_df = df[base_cols].copy()
    for out_col in preview_cols:
        if out_col in st.session_state.translated_cols:
            preview_df[out_col] = st.session_state.translated_cols[out_col].values

    st.dataframe(preview_df.head(20), use_container_width=True)

    profile = st.session_state.profile
    download_name = profile["filename"].replace(".csv", "_translated.csv")
    st.download_button(
        label="Download Translated CSV",
        data=st.session_state.export_bytes,
        file_name=download_name,
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    st.divider()
    if st.button("Upload another document", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
