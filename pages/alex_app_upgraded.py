"""
Alex, The Invincible  v3.1
━━━━━━━━━━━━━━━━━━━━━━━━━
Full Talabat PIM-compliant catalogue formatter:
  • Complete target schema (barcode → dimensions → descriptions)
  • Master Brand Scanner
  • numberOfUnits from multipack (10x50g → 10)
  • PIM-compliant contentsUnit (exact system strings)
  • Optional AR / KU translation with Iraq warning
  • Optional AI-generated descriptions (EN / AR / KU)
  • Optional AI-estimated dimensions & weight
  • Prohibited content scanner (tobacco + pork)
  • Nitro Batch Translation (<60s for 2000 rows)
"""

import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
import time

from deep_translator import GoogleTranslator
from smart_title_formatter import (
    format_title as smart_format_title,
    prepare_brands_list,
    scan_prohibited,
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Alex AI Wizard", page_icon="🤖", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 AUTH
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    st.warning("🛑 Access Denied. Please go to the main Login page.")
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
# MASTER BRANDS (cached per session)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_master_brands() -> list:
    try:
        brands_df = pd.read_csv("master_brands.csv", dtype=str)
        return prepare_brands_list(brands_df)
    except FileNotFoundError:
        return []
    except Exception:
        return []

master_brands = load_master_brands()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
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

# Exact PIM unit strings accepted by Talabat system
PIM_VALID_UNITS = {
    "bags", "bouquets - flowers", "boxes", "bunches", "capsules",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets",
    "sheets", "tablets", "units",
}

# ─────────────────────────────────────────────────────────────────────────────
# AI BATCH HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ai_batch_dimensions(titles: list[str], ai_client) -> list[dict]:
    """
    For a batch of product titles, ask AI to estimate physical dimensions.
    Returns list of dicts: {w, h, l, weight_g} — one per title, in order.
    Falls back to empty dicts on failure.
    """
    if not titles:
        return []

    prompt = (
        "You are a product data expert. For each product title below, estimate realistic "
        "physical dimensions (width, height, length in cm) and total weight in grams "
        "based on typical retail packaging for that product type.\n"
        "Return ONLY a valid JSON array with one object per product, in the same order.\n"
        "Each object must have exactly these keys: w, h, l, weight_g (all numbers).\n"
        "Use 0 if truly unknown. Do not add any text outside the JSON array.\n\n"
        "Titles:\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    )

    try:
        resp = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON arrays."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        result = json.loads(raw)
        if isinstance(result, list) and len(result) == len(titles):
            return result
    except Exception:
        pass

    return [{"w": 0, "h": 0, "l": 0, "weight_g": 0}] * len(titles)


def ai_batch_descriptions(
    titles: list[str],
    ai_client,
    need_en: bool = True,
    need_ar: bool = False,
    need_ku: bool = False,
) -> list[dict]:
    """
    Generate short product descriptions for a batch of titles.
    Returns list of dicts with requested language keys.
    """
    if not titles:
        return []

    langs = []
    if need_en:
        langs.append('"en": <1-2 sentence English description>')
    if need_ar:
        langs.append('"ar": <1-2 sentence Arabic description>')
    if need_ku:
        langs.append('"ku": <1-2 sentence Kurdish (Kurmanji) description>')

    lang_spec = ", ".join(langs)

    prompt = (
        "You are a product copywriter for a quick-commerce platform in the Middle East. "
        "Write a concise 1-2 sentence product description for each title below. "
        "Keep it factual, friendly, and informative.\n"
        f"Return ONLY a valid JSON array. Each object must have keys: {lang_spec}.\n"
        "One object per product, in the same order. No text outside the JSON array.\n\n"
        "Titles:\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    )

    try:
        resp = ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON arrays."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        result = json.loads(raw)
        if isinstance(result, list) and len(result) == len(titles):
            return result
    except Exception:
        pass

    empty = {}
    if need_en:
        empty["en"] = ""
    if need_ar:
        empty["ar"] = ""
    if need_ku:
        empty["ku"] = ""
    return [empty] * len(titles)


def nitro_translate(titles: list[str], target_lang: str, chunk: int = 30) -> list[str]:
    """
    Batch-translate a list of titles. Returns translated list (same length).
    Fills failed chunks with empty strings.
    """
    if not titles:
        return []
    translated: list[str] = []
    translator = GoogleTranslator(source="en", target=target_lang)

    for start in range(0, len(titles), chunk):
        batch = titles[start: start + chunk]
        safe  = [t if t and t != "N/A" else "." for t in batch]
        done  = False
        for attempt in range(3):
            try:
                result = translator.translate_batch(safe)
                # Restore placeholder dots back to blank
                result = ["" if r == "." else (r or "") for r in result]
                translated.extend(result)
                done = True
                break
            except Exception:
                time.sleep(1.0)
        if not done:
            translated.extend([""] * len(batch))

    return translated[: len(titles)]


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Task Setup")
    st.info("Fill all three fields to unlock processing.")

    case_id     = st.text_input("Case ID",     placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")
    country     = st.selectbox(
        "Country",
        options=["", "Egypt", "United Arab Emirates", "Kuwait",
                 "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"],
    )
    task_ready = bool(case_id.strip() and client_name.strip() and country)

    st.divider()
    st.subheader("🌍 Translation Options")
    need_ar = st.toggle("Arabic translation (productTitle::ar)", value=True)
    need_ku = st.toggle("Kurdish translation (productTitle::ku)", value=False)

    # Iraq + Kurdish warning
    if country == "Iraq" and not need_ku:
        st.warning(
            "⚠️ **Iraq selected** — Kurdish (KU) titles are typically required "
            "for Iraq listings. Please enable Kurdish translation above."
        )

    st.divider()
    st.subheader("🤖 AI Extras (optional)")
    need_desc_en = st.toggle("Generate EN descriptions", value=False)
    need_desc_ar = st.toggle("Generate AR descriptions", value=False)
    need_desc_ku = st.toggle("Generate KU descriptions", value=False)
    need_dims    = st.toggle("AI-estimate dimensions & weight", value=False)

    st.divider()
    brand_count = len(master_brands)
    st.metric("🏷️ Brands in Database", f"{brand_count:,}" if brand_count else "Not loaded")

    st.divider()
    st.subheader("📋 Target Schema")
    st.code(
        "pieceBarcode\nbrand_id\nproductTitle::en\nproductTitle::ar*\n"
        "productTitle::ku*\nimageUrls\nwidthInCm*\nheightInCm*\nlengthInCm*\n"
        "weightValue*\nweightUnit\ncontentsValue\ncontentsUnit\nnumberOfUnits\n"
        "productDescription::en*\nproductDescription::ar*\nproductDescription::ku*\n"
        "\n* = conditional / AI-generated",
        language="markdown",
    )

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v3.1")
display_name = st.session_state.get("user_name", "There").title()
st.markdown(
    f"Hello **{display_name}** ❤️, I am **Alex** — AI Assistant by **Mostafa Abdelaziz**.  \n"
    "Smart Title Engine · Brand Scanner · PIM Units · Nitro Translate · Prohibited Scanner ✨"
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

if st.session_state.last_uploaded_file != uploaded_file.name:
    st.session_state.ai_mapping = None
    st.session_state.last_uploaded_file = uploaded_file.name

try:
    raw_df = (
        pd.read_csv(uploaded_file, dtype=str)
        if uploaded_file.name.endswith(".csv")
        else pd.read_excel(uploaded_file, dtype=str)
    )
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
1. pieceBarcode  → EAN > GTIN > UPC > Barcode (12-14 digit global numbers).
2. productTitle::en → Most descriptive English title/name/description column.
3. contentsValue → Size, Weight, Volume, Net Weight, Qty.
   NEVER map Price, Cost, MSRP, RRP, or any currency column.
4. contentsUnit  → UOM, Unit, Measurement.
   NEVER map currency symbols ($, AED, EGP, SAR).
5. imageUrls     → URL, Link, Photo, Image, Media column.

Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}.
Omit any target field if no suitable client header exists.
"""
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Output strict JSON only."},
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
            "🚀 Step 3: Run Full Catalogue Processing", type="primary"
        )

if not submitted:
    st.stop()

# Iraq + KU final warning before processing
if country == "Iraq" and not need_ku:
    st.warning(
        "⚠️ You selected **Iraq** but Kurdish translation is not enabled. "
        "Kurdish (KU) columns are typically required for Iraq. "
        "Go back to the sidebar to enable it, or continue without it."
    )

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — FULL PROCESSING
# ─────────────────────────────────────────────────────────────────────────────
t_start  = time.time()
progress = st.progress(0, text="Starting…")

active_map = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}

# ── 3a. Build working DataFrame ───────────────────────────────────────────────
work_df = pd.DataFrame()
for col in TARGET_SCHEMA:
    src = active_map.get(col)
    work_df[col] = raw_df[src] if src and src in raw_df.columns else ""

# Add ALL output columns upfront
work_df.insert(1, "brand_id",              "")
work_df["productTitle::ar"]       = ""
work_df["productTitle::ku"]       = ""
work_df["widthInCm"]              = ""
work_df["heightInCm"]             = ""
work_df["lengthInCm"]             = ""
work_df["weightValue"]            = ""
work_df["weightUnit"]             = "g"          # always "g" per spec
work_df["numberOfUnits"]          = 1
work_df["productDescription::en"] = ""
work_df["productDescription::ar"] = ""
work_df["productDescription::ku"] = ""
work_df["_title_confidence"]      = ""
work_df["_title_changes"]         = ""
work_df["_prohibited_flag"]       = ""
work_df["Catalogue_Feedback"]     = ""

total   = len(work_df)
feedback: list[str]    = []
titles_for_translation: list[str] = []    # formatted EN titles for AR/KU translate
titles_for_dims:        list[int] = []    # row indices needing AI dimensions
titles_for_desc:        list[int] = []    # row indices needing AI descriptions

# ── 3b. Row-by-row core processing ───────────────────────────────────────────
progress.progress(0.05, text="Formatting titles & scanning brands…")

for idx, row in work_df.iterrows():
    doubts: list[str] = []

    # ── Barcode ───────────────────────────────────────────────────────────
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
        brands_list=master_brands,
    )

    formatted = title_res["formatted_title"]
    work_df.at[idx, "productTitle::en"]  = formatted
    work_df.at[idx, "brand_id"]          = title_res["brand_id"]
    work_df.at[idx, "_title_confidence"] = title_res["confidence"]
    work_df.at[idx, "numberOfUnits"]     = title_res["number_of_units"]

    if formatted and formatted != raw_title:
        work_df.at[idx, "_title_changes"] = f"{raw_title} → {formatted}"

    titles_for_translation.append(formatted if formatted else "N/A")

    # ── Prohibited content ────────────────────────────────────────────────
    if title_res["prohibited"]:
        flag_str = " | ".join(title_res["prohibited"])
        work_df.at[idx, "_prohibited_flag"] = flag_str
        doubts.append(f"🚫 PROHIBITED — {flag_str}")

    # ── Unbranded ─────────────────────────────────────────────────────────
    if "Unbranded - Audit Required" in title_res["issues"]:
        doubts.append("Unbranded - Audit Required")

    # ── contentsValue / contentsUnit (PIM-compliant) ──────────────────────
    pim_val  = title_res["pim_contents_value"]
    pim_unit = title_res["pim_contents_unit"]

    # Prefer vendor-supplied values if present
    if cv_raw and cv_raw not in ("0", "0.0"):
        work_df.at[idx, "contentsValue"] = cv_raw
    elif pim_val:
        work_df.at[idx, "contentsValue"] = pim_val

    if cu_raw and cu_raw.lower() in PIM_VALID_UNITS:
        work_df.at[idx, "contentsUnit"] = cu_raw.lower()
    elif pim_unit and pim_unit in PIM_VALID_UNITS:
        work_df.at[idx, "contentsUnit"] = pim_unit
    elif cu_raw:
        # Try to map vendor unit to PIM
        from smart_title_formatter import to_pim_unit as _to_pim
        mapped = _to_pim(cu_raw.lower())
        work_df.at[idx, "contentsUnit"] = mapped if mapped in PIM_VALID_UNITS else cu_raw.lower()

    # ── Validation ────────────────────────────────────────────────────────
    cv_final = str(work_df.at[idx, "contentsValue"]).strip()
    cu_final = str(work_df.at[idx, "contentsUnit"]).strip().lower()

    if not cv_final or cv_final in ("nan", ""):
        doubts.append("Missing Qty")
    if not cu_final or cu_final in ("nan", ""):
        doubts.append("Missing Unit")
    elif cu_final not in PIM_VALID_UNITS:
        doubts.append(f"Invalid Unit ({cu_final})")

    # ── Image URL ─────────────────────────────────────────────────────────
    raw_url = str(row.get("imageUrls", "")).strip().lower()
    if raw_url in ("", "nan", "none", "n/a"):
        doubts.append("Missing Image")
    elif not raw_url.startswith("http"):
        doubts.append("Invalid Image URL")

    # Track rows needing AI extras
    if need_dims:
        titles_for_dims.append(idx)
    if need_desc_en or need_desc_ar or need_desc_ku:
        titles_for_desc.append(idx)

    feedback.append(
        "✅ Ready for Catalogue" if not doubts else "⚠️ " + ", ".join(doubts)
    )

work_df["Catalogue_Feedback"] = feedback
progress.progress(0.35, text="Core processing done…")

# ── 3c. AI DIMENSIONS (optional) ─────────────────────────────────────────────
if need_dims and titles_for_dims:
    progress.progress(0.38, text="AI estimating dimensions…")
    DIM_CHUNK = 20
    dim_indices = titles_for_dims
    dim_titles  = [str(work_df.at[i, "productTitle::en"]) for i in dim_indices]

    for start in range(0, len(dim_titles), DIM_CHUNK):
        batch_idx    = dim_indices[start: start + DIM_CHUNK]
        batch_titles = dim_titles[start: start + DIM_CHUNK]
        results      = ai_batch_dimensions(batch_titles, ai_client)

        for row_idx, dims in zip(batch_idx, results):
            if isinstance(dims, dict):
                if dims.get("w"):
                    work_df.at[row_idx, "widthInCm"]  = round(float(dims["w"]), 1)
                if dims.get("h"):
                    work_df.at[row_idx, "heightInCm"] = round(float(dims["h"]), 1)
                if dims.get("l"):
                    work_df.at[row_idx, "lengthInCm"] = round(float(dims["l"]), 1)
                if dims.get("weight_g"):
                    work_df.at[row_idx, "weightValue"] = round(float(dims["weight_g"]), 1)

        frac = 0.38 + 0.12 * min(start + DIM_CHUNK, len(dim_titles)) / len(dim_titles)
        progress.progress(frac, text=f"Dimensions… {min(start+DIM_CHUNK, len(dim_titles))}/{len(dim_titles)}")

progress.progress(0.50, text="Dimensions complete…")

# ── 3d. AI DESCRIPTIONS (optional) ───────────────────────────────────────────
if (need_desc_en or need_desc_ar or need_desc_ku) and titles_for_desc:
    progress.progress(0.52, text="Generating descriptions with AI…")
    DESC_CHUNK = 10
    desc_indices = titles_for_desc
    desc_titles  = [str(work_df.at[i, "productTitle::en"]) for i in desc_indices]

    for start in range(0, len(desc_titles), DESC_CHUNK):
        batch_idx    = desc_indices[start: start + DESC_CHUNK]
        batch_titles = desc_titles[start: start + DESC_CHUNK]
        results      = ai_batch_descriptions(
            batch_titles, ai_client,
            need_en=need_desc_en,
            need_ar=need_desc_ar,
            need_ku=need_desc_ku,
        )
        for row_idx, desc in zip(batch_idx, results):
            if isinstance(desc, dict):
                if need_desc_en:
                    work_df.at[row_idx, "productDescription::en"] = desc.get("en", "")
                if need_desc_ar:
                    work_df.at[row_idx, "productDescription::ar"] = desc.get("ar", "")
                if need_desc_ku:
                    work_df.at[row_idx, "productDescription::ku"] = desc.get("ku", "")

        frac = 0.52 + 0.08 * min(start + DESC_CHUNK, len(desc_titles)) / len(desc_titles)
        progress.progress(frac, text=f"Descriptions… {min(start+DESC_CHUNK, len(desc_titles))}/{len(desc_titles)}")

progress.progress(0.60, text="Descriptions complete…")

# ── 3e. NITRO TRANSLATION — Arabic ───────────────────────────────────────────
if need_ar:
    progress.progress(0.62, text="Nitro-translating to Arabic…")
    ar_results = nitro_translate(titles_for_translation, "ar")
    work_df["productTitle::ar"] = ar_results[: len(work_df)]
    progress.progress(0.80, text="Arabic done…")

# ── 3f. NITRO TRANSLATION — Kurdish ──────────────────────────────────────────
if need_ku:
    progress.progress(0.82, text="Nitro-translating to Kurdish…")
    try:
        ku_results = nitro_translate(titles_for_translation, "ku")
        work_df["productTitle::ku"] = ku_results[: len(work_df)]
    except Exception as e:
        st.warning(f"Kurdish translation failed: {e}")
        work_df["productTitle::ku"] = ""
    progress.progress(0.95, text="Kurdish done…")

progress.progress(1.0, text="Done!")
elapsed = time.time() - t_start

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────
st.success(f"✅ Completed in **{elapsed:.1f}s**")

ready_df      = work_df[work_df["Catalogue_Feedback"] == "✅ Ready for Catalogue"]
error_df      = work_df[work_df["Catalogue_Feedback"].str.startswith("⚠️")]
prohibited_df = work_df[work_df["_prohibited_flag"] != ""]
changed_df    = work_df[work_df["_title_changes"] != ""].copy()

total_rows    = len(work_df)
ready_count   = len(ready_df)
error_count   = len(error_df)
prohib_count  = len(prohibited_df)
brand_matched = (work_df["brand_id"] != "").sum()
changed_count = len(changed_df)
quality_pct   = f"{(ready_count / total_rows * 100):.1f}%" if total_rows else "0%"

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("✅ Ready",           ready_count)
c2.metric("⚠️ Needs Review",    error_count)
c3.metric("🚫 Prohibited",       prohib_count)
c4.metric("🏷️ Brands Matched",  int(brand_matched))
c5.metric("✏️ Titles Fixed",    changed_count)
c6.metric("📊 Quality Score",    quality_pct)

if prohib_count:
    st.error(
        f"🚫 **{prohib_count} prohibited item(s) detected** (tobacco or pork). "
        "See the '🚫 Prohibited' tab and sheet — these must be removed before submission."
    )

conf = work_df["_title_confidence"].value_counts()
with st.expander("🔍 Title Confidence Breakdown"):
    st.write(
        f"**High:** {conf.get('high', 0)}  |  "
        f"**Medium:** {conf.get('medium', 0)}  |  "
        f"**Low:** {conf.get('low', 0)} *(manual review recommended)*"
    )

# ─────────────────────────────────────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────

# Build ordered export columns (no internal _ columns)
ORDERED_EXPORT = [
    "pieceBarcode", "brand_id", "productTitle::en", "productTitle::ar", "productTitle::ku",
    "imageUrls",
    "widthInCm", "heightInCm", "lengthInCm", "weightValue", "weightUnit",
    "contentsValue", "contentsUnit", "numberOfUnits",
    "productDescription::en", "productDescription::ar", "productDescription::ku",
    "Catalogue_Feedback",
]
# Keep only columns that are present in work_df
export_cols   = [c for c in ORDERED_EXPORT if c in work_df.columns]
export_ready  = ready_df[export_cols]
export_errors = error_df[export_cols]

output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    pd.DataFrame({
        "Case ID":            [case_id],
        "Client Name":        [client_name],
        "Country":            [country],
        "Total Rows":         [total_rows],
        "Ready":              [ready_count],
        "Needs Review":       [error_count],
        "Prohibited Items":   [prohib_count],
        "Brands Matched":     [int(brand_matched)],
        "Titles Fixed":       [changed_count],
        "Quality Score":      [quality_pct],
        "Processing Time (s)":[f"{elapsed:.1f}"],
        "AR Translation":     ["Yes" if need_ar else "No"],
        "KU Translation":     ["Yes" if need_ku else "No"],
        "AI Descriptions":    ["Yes" if (need_desc_en or need_desc_ar or need_desc_ku) else "No"],
        "AI Dimensions":      ["Yes" if need_dims else "No"],
    }).to_excel(writer, index=False, sheet_name="Summary")

    export_ready.to_excel(writer, index=False, sheet_name="Ready to Import")

    if error_count > 0:
        export_errors.to_excel(writer, index=False, sheet_name="Action Required")

    if prohib_count > 0:
        prohibited_df[export_cols + ["_prohibited_flag"]].to_excel(
            writer, index=False, sheet_name="Prohibited Items"
        )

    if changed_count > 0:
        changed_df[["productTitle::en", "_title_changes", "_title_confidence"]].to_excel(
            writer, index=False, sheet_name="Title Changes Log"
        )

output_bytes    = output.getvalue()
output_filename = f"{case_id} - {client_name} - {country}_Alex_v3.1.xlsx"

st.download_button(
    label=f"📥 Download Full Catalogue Report  ({output_filename})",
    data=output_bytes,
    file_name=output_filename,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    use_container_width=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# PREVIEW TABS
# ─────────────────────────────────────────────────────────────────────────────
tabs = [
    f"✅ Ready ({ready_count})",
    f"⚠️ Action Required ({error_count})",
    f"🚫 Prohibited ({prohib_count})",
    f"✏️ Title Changes ({changed_count})",
]
tab1, tab2, tab3, tab4 = st.tabs(tabs)

with tab1:
    st.dataframe(export_ready, use_container_width=True)

with tab2:
    if error_count:
        st.dataframe(export_errors, use_container_width=True)
    else:
        st.success("🎉 No errors! Perfect file.")

with tab3:
    if prohib_count:
        st.dataframe(
            prohibited_df[["productTitle::en", "_prohibited_flag", "Catalogue_Feedback"]],
            use_container_width=True,
        )
    else:
        st.success("✅ No prohibited products detected.")

with tab4:
    if changed_count:
        st.dataframe(
            changed_df[["productTitle::en", "_title_changes", "_title_confidence"]],
            use_container_width=True,
        )
    else:
        st.info("No titles were changed — vendor file was already well-formatted.")
