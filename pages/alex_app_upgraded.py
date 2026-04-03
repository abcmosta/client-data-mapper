"""
Alex, The Invincible  v3.0
━━━━━━━━━━━━━━━━━━━━━━━━━
Fast Catalogue Formatter with:
  • Master Brand Scanner (from master_brands.csv)
  • Smart Title Engine (19k-trained formatter)
  • Nitro Batch Translation (chunked, <60 s for 2000 rows)
  • 1 Piece / 1 Pack / count units fully supported
"""

import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
import time

from deep_translator import GoogleTranslator
from smart_title_formatter import format_title as smart_format_title, prepare_brands_list

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Alex AI Wizard", page_icon="🤖", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    st.warning("🛑 Access Denied. Please go to the main Login page and enter the Master Key.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# AI CLIENT
# ─────────────────────────────────────────────────────────────────────────────
github_token = st.secrets["GITHUB_TOKEN"]
ai_client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=github_token,
)

# ─────────────────────────────────────────────────────────────────────────────
# MASTER BRANDS LOADER  (cached — runs once per session)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_master_brands() -> list:
    """
    Load master_brands.csv from the app directory.
    Returns a list of dicts sorted longest-brand-name-first for scan accuracy.
    Falls back to empty list if file is missing (formatter still works, just
    won't do brand lookups).
    """
    try:
        brands_df = pd.read_csv("master_brands.csv", dtype=str)
        return prepare_brands_list(brands_df)
    except FileNotFoundError:
        st.sidebar.warning("⚠️ master_brands.csv not found — brand scanning disabled.")
        return []
    except Exception as e:
        st.sidebar.error(f"Brand file error: {e}")
        return []

master_brands = load_master_brands()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
for key, default in [("ai_mapping", None), ("last_uploaded_file", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
TARGET_SCHEMA = [
    "pieceBarcode",
    "productTitle::en",
    "imageUrls",
    "contentsValue",
    "contentsUnit",
]

ACCEPTABLE_UNITS = {
    "bag", "bags", "box", "boxes", "bunch", "bunches",
    "capsule", "capsules", "cl", "cm", "cm2", "cm3",
    "dl", "g", "kg", "l", "lb", "m", "mg", "ml", "oz",
    "pack", "packs", "packet", "packets", "pc", "pcs",
    "piece", "pieces", "roll", "rolls", "sachet", "sachets",
    "sheet", "sheets", "tablet", "tablets", "unit", "units",
}

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Task Setup")
    st.info("⚠️ Fill all three fields to unlock processing.")

    case_id     = st.text_input("Case ID",     placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")
    country     = st.selectbox(
        "Country",
        options=["", "Egypt", "United Arab Emirates", "Kuwait",
                 "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"],
    )

    task_ready = bool(case_id.strip() and client_name.strip() and country)

    st.divider()
    brand_count = len(master_brands)
    st.metric("🏷️ Brands in Database", f"{brand_count:,}" if brand_count else "Not loaded")

    st.divider()
    st.header("📋 Target Schema")
    st.code(
        "- pieceBarcode\n- brand_id\n- productTitle::en\n"
        "- productTitle::ar\n- imageUrls\n- contentsValue\n- contentsUnit",
        language="markdown",
    )
    st.caption("🧠 Title Engine v3 · Brand Scanner · Nitro Translate")

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v3.0")
display_name = st.session_state.get("user_name", "There").title()
st.markdown(
    f"Hello **{display_name}** ❤️, I am **Alex** — AI Assistant by **Mostafa Abdelaziz**.  \n"
    f"Smart Title Engine · Master Brand Scanner · Nitro Batch Translation ✨"
)
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# FILE UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Drop the messy client file here (CSV or Excel)",
    type=["csv", "xlsx"],
)

if not uploaded_file:
    st.stop()

# Reset mapping if a new file is uploaded
if st.session_state.last_uploaded_file != uploaded_file.name:
    st.session_state.ai_mapping = None
    st.session_state.last_uploaded_file = uploaded_file.name

# ─── Read file ────────────────────────────────────────────────────────────────
try:
    if uploaded_file.name.endswith(".csv"):
        raw_df = pd.read_csv(uploaded_file, dtype=str)
    else:
        raw_df = pd.read_excel(uploaded_file, dtype=str)
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

with st.expander("👀 Preview raw client data"):
    st.dataframe(raw_df.head(5), use_container_width=True)

st.metric("Total rows uploaded", len(raw_df))
st.divider()

headers = raw_df.columns.tolist()
sample  = raw_df.head(3).to_dict(orient="records")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — AI COLUMN MAPPING
# ─────────────────────────────────────────────────────────────────────────────
if not task_ready:
    st.warning("🔒 Fill in Case ID, Client Name, and Country in the sidebar first.")
    st.button("🧠 Step 1: Map Columns with Alex", disabled=True)
else:
    if st.button("🧠 Step 1: Map Columns with Alex", type="primary"):
        with st.spinner("Alex is analysing headers…"):
            prompt = f"""
You are Alex, an elite Data Engineer at Talabat.
Map these client headers to the Target Schema: {TARGET_SCHEMA}

Client headers: {headers}
Sample data: {sample}

RULES:
1. pieceBarcode  → EAN > GTIN > UPC > Barcode (12–14 digit global numbers).
2. productTitle::en → Most descriptive English title/name/description column.
3. contentsValue → Size, Weight, Volume, Net Weight, Qty.
   🚨 NEVER map Price, Cost, MSRP, RRP, or any currency column.
4. contentsUnit  → UOM, Unit, Measurement.
   🚨 NEVER map currency symbols ($, AED, EGP, SAR).
5. imageUrls     → URL, Link, Photo, Image, Media column.

Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}.
Omit any target field if no suitable client header exists.
"""
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Output strict JSON only, no explanation."},
                    {"role": "user",   "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            st.session_state.ai_mapping = json.loads(
                response.choices[0].message.content
            )

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — MANUAL OVERRIDE
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.ai_mapping is None:
    st.stop()

with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
    with st.form("mapping_form"):
        final_mapping = {}
        options = ["--- Leave Blank ---"] + headers
        for col in TARGET_SCHEMA:
            suggested = st.session_state.ai_mapping.get(col)
            idx = options.index(suggested) if suggested in options else 0
            final_mapping[col] = st.selectbox(f"Map '{col}' to:", options, index=idx)
        submitted = st.form_submit_button(
            "🚀 Step 3: Run Master Cleanse & Nitro Translate", type="primary"
        )

if not submitted:
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — PROCESS  (all heavy work happens here)
# ─────────────────────────────────────────────────────────────────────────────
t_start = time.time()

progress = st.progress(0, text="Starting…")

active_map = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}

# ── 3a. Build the working DataFrame ──────────────────────────────────────────
work_df = pd.DataFrame()
for col in TARGET_SCHEMA:
    src = active_map.get(col)
    work_df[col] = raw_df[src] if src and src in raw_df.columns else ""

# Add output columns
work_df.insert(1, "brand_id",        "")
work_df["productTitle::ar"]  = ""
work_df["_title_changes"]    = ""
work_df["_title_confidence"] = ""
work_df["Catalogue_Feedback"] = ""

total   = len(work_df)
feedback = []
titles_for_translation: list[str] = []

# ── 3b. Row-by-row: barcode, title format, brand scan, size ──────────────────
progress.progress(0.05, text="Formatting titles & scanning brands…")

for idx, row in work_df.iterrows():
    doubts = []

    # ── Barcode ──────────────────────────────────────────────────────────
    raw_bc = str(row.get("pieceBarcode", "")).replace(".0", "").strip()
    if raw_bc and raw_bc.lower() not in ("nan", "none", ""):
        work_df.at[idx, "pieceBarcode"] = f"'{raw_bc.zfill(13)}"
    else:
        work_df.at[idx, "pieceBarcode"] = ""
        doubts.append("Missing Barcode")

    # ── Smart Title + Brand Scanner ───────────────────────────────────────
    raw_title = str(row.get("productTitle::en", "")).replace("nan", "").strip()
    cv_raw    = str(row.get("contentsValue", "")).replace("nan", "").strip()
    cu_raw    = str(row.get("contentsUnit",  "")).replace("nan", "").strip()

    title_res = smart_format_title(
        raw_title=raw_title,
        contents_value=cv_raw,
        contents_unit=cu_raw,
        brands_list=master_brands,    # ← master brand scan
    )

    formatted = title_res["formatted_title"]
    work_df.at[idx, "productTitle::en"]  = formatted
    work_df.at[idx, "brand_id"]          = title_res["brand_id"]
    work_df.at[idx, "_title_confidence"] = title_res["confidence"]

    if formatted and formatted != raw_title:
        work_df.at[idx, "_title_changes"] = f"{raw_title} → {formatted}"

    # Queue for translation (empty string → placeholder to keep index alignment)
    titles_for_translation.append(formatted if formatted else "N/A")

    # Flag unbranded
    if "Unbranded - Audit Required" in title_res["issues"]:
        doubts.append("Unbranded - Audit Required")

    # ── Size fallback: fill contentsValue/Unit from extracted size ────────
    extracted = title_res["extracted_size"]
    cv_now = str(work_df.at[idx, "contentsValue"]).strip()
    cu_now = str(work_df.at[idx, "contentsUnit"]).strip().lower()
    cv_missing = not cv_now or cv_now in ("nan", "0", "0.0", "")
    cu_missing = not cu_now or cu_now in ("nan", "")

    if extracted and (cv_missing or cu_missing):
        # Parse out value and unit from e.g. "120ml", "3 Capsules", "5x1.3ml"
        size_m = re.search(
            r"(?:[\d.x×]+[x×])?(\d+(?:\.\d+)?)\s*([a-zA-Z ]+)$", extracted
        )
        if size_m:
            if cv_missing:
                work_df.at[idx, "contentsValue"] = size_m.group(1)
            if cu_missing:
                work_df.at[idx, "contentsUnit"]  = size_m.group(2).strip().lower()

    # Re-read after possible update
    cv_final  = str(work_df.at[idx, "contentsValue"]).strip()
    cu_final  = str(work_df.at[idx, "contentsUnit"]).strip().lower()

    if not cv_final or cv_final in ("nan", ""):
        doubts.append("Missing Qty")
    if not cu_final or cu_final in ("nan", ""):
        doubts.append("Missing Unit")
    elif cu_final not in ACCEPTABLE_UNITS:
        doubts.append(f"Invalid Unit ({cu_final})")

    # ── Image URL ─────────────────────────────────────────────────────────
    raw_url = str(row.get("imageUrls", "")).strip().lower()
    if raw_url in ("", "nan", "none", "n/a"):
        doubts.append("Missing Image")
    elif not raw_url.startswith("http"):
        doubts.append("Invalid Image URL")

    feedback.append(
        "✅ Ready for Catalogue" if not doubts else "⚠️ " + ", ".join(doubts)
    )

work_df["Catalogue_Feedback"] = feedback

# ── 3c. Nitro Batch Translation ───────────────────────────────────────────────
progress.progress(0.55, text="Nitro-translating to Arabic…")

CHUNK   = 30      # GoogleTranslator handles ~30 items per batch comfortably
RETRIES = 2

translated: list[str] = []

try:
    translator = GoogleTranslator(source="en", target="ar")

    for start in range(0, len(titles_for_translation), CHUNK):
        chunk = titles_for_translation[start : start + CHUNK]
        # Replace empty/N-A with a period so translator doesn't error on blank
        safe_chunk = [t if t and t != "N/A" else "." for t in chunk]

        success = False
        for attempt in range(RETRIES + 1):
            try:
                result = translator.translate_batch(safe_chunk)
                translated.extend(result)
                success = True
                break
            except Exception:
                if attempt == RETRIES:
                    # All retries exhausted — fill chunk with error marker
                    translated.extend(["خطأ في الترجمة"] * len(chunk))
                else:
                    time.sleep(1.0)

        # Restore "." translations back to blank
        for i in range(len(translated) - len(chunk), len(translated)):
            if translated[i] == ".":
                translated[i] = ""

        # Update progress during translation
        frac = 0.55 + 0.40 * min(start + CHUNK, len(titles_for_translation)) / len(titles_for_translation)
        progress.progress(frac, text=f"Translating… {min(start+CHUNK, len(titles_for_translation))}/{len(titles_for_translation)}")

    # Safety: pad if count is off
    while len(translated) < len(work_df):
        translated.append("")

    work_df["productTitle::ar"] = translated[: len(work_df)]

except Exception as e:
    st.warning(f"Translation error: {e} — Arabic column left blank.")
    work_df["productTitle::ar"] = ""

# ── 3d. Final bookkeeping ─────────────────────────────────────────────────────
progress.progress(1.0, text="Done!")
elapsed = time.time() - t_start

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS DISPLAY
# ─────────────────────────────────────────────────────────────────────────────
st.success(f"✅ Completed in **{elapsed:.1f}s**")

ready_df   = work_df[work_df["Catalogue_Feedback"] == "✅ Ready for Catalogue"]
error_df   = work_df[work_df["Catalogue_Feedback"].str.startswith("⚠️")]
changed_df = work_df[work_df["_title_changes"] != ""].copy()

total_rows    = len(work_df)
ready_count   = len(ready_df)
error_count   = len(error_df)
brand_matched = (work_df["brand_id"] != "").sum()
changed_count = len(changed_df)
quality_pct   = f"{(ready_count / total_rows * 100):.1f}%" if total_rows else "0%"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("✅ Ready",           ready_count)
c2.metric("⚠️ Needs Review",    error_count)
c3.metric("🏷️ Brands Matched", brand_matched)
c4.metric("✏️ Titles Fixed",    changed_count)
c5.metric("📊 Quality Score",   quality_pct)

# Confidence breakdown
conf = work_df["_title_confidence"].value_counts()
with st.expander("🔍 Title Confidence Breakdown"):
    st.write(
        f"**High:** {conf.get('high', 0)}  |  "
        f"**Medium:** {conf.get('medium', 0)}  |  "
        f"**Low:** {conf.get('low', 0)} *(needs review)*"
    )

# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────
# Columns to include in export (skip internal _debug columns)
export_cols = [c for c in work_df.columns if not c.startswith("_")]
export_ready  = ready_df[export_cols]
export_errors = error_df[export_cols]
export_changes = changed_df[["productTitle::en", "_title_changes", "_title_confidence", "Catalogue_Feedback"]]

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    # Summary sheet
    pd.DataFrame({
        "Case ID":            [case_id],
        "Client Name":        [client_name],
        "Country":            [country],
        "Total Rows":         [total_rows],
        "Ready":              [ready_count],
        "Needs Review":       [error_count],
        "Brands Matched":     [int(brand_matched)],
        "Titles Fixed":       [changed_count],
        "Quality Score":      [quality_pct],
        "Processing Time (s)":[f"{elapsed:.1f}"],
    }).to_excel(writer, index=False, sheet_name="📊 Summary")

    export_ready.to_excel(writer, index=False, sheet_name="✅ Ready to Import")

    if error_count > 0:
        export_errors.to_excel(writer, index=False, sheet_name="⚠️ Action Required")

    if changed_count > 0:
        export_changes.to_excel(writer, index=False, sheet_name="✏️ Title Changes Log")

output_bytes    = output.getvalue()
output_filename = f"{case_id} - {client_name} - {country}_Alex_v3.xlsx"

st.download_button(
    label=f"📥 Download Excel Report  ({output_filename})",
    data=output_bytes,
    file_name=output_filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    use_container_width=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# DATA PREVIEW TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    f"✅ Ready ({ready_count})",
    f"⚠️ Action Required ({error_count})",
    f"✏️ Title Changes ({changed_count})",
])

with tab1:
    st.dataframe(export_ready, use_container_width=True)

with tab2:
    if error_count:
        st.dataframe(export_errors, use_container_width=True)
    else:
        st.success("🎉 No errors! Perfect file.")

with tab3:
    if changed_count:
        st.dataframe(
            changed_df[["productTitle::en", "_title_changes", "_title_confidence"]],
            use_container_width=True,
        )
    else:
        st.info("No titles were changed — vendor file was already well-formatted.")
