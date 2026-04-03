import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
import time
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────────────────────────────────────
# Import the Smart Title Formatter
# ─────────────────────────────────────────────────────────────────────────────
from smart_title_formatter import format_title as smart_format_title

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 AUTHENTICATION CHECK
# ─────────────────────────────────────────────────────────────────────────────
if not st.session_state.get('authenticated', False):
    st.warning("🛑 Access Denied. Please go to the main Login page and enter the Master Key.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# SETUP THE AI BRAIN
# ─────────────────────────────────────────────────────────────────────────────
github_token = st.secrets["GITHUB_TOKEN"]
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=github_token
)

# ─────────────────────────────────────────────────────────────────────────────
# 📦 LOAD MASTER BRANDS (New Logic)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_master_brands():
    try:
        df = pd.read_csv("master_brands.csv")
        df = df.dropna(subset=['brand_id', 'brand::en'])
        # Sort by length descending to match longest phrases first (e.g. L'Oreal Paris before L'Oreal)
        brands = df[['brand_id', 'brand::en']].drop_duplicates(subset=['brand::en']).copy()
        brands['len'] = brands['brand::en'].astype(str).str.len()
        brands = brands.sort_values(by='len', ascending=False)
        return brands[['brand_id', 'brand::en']].to_dict('records')
    except:
        return []

master_brands_list = load_master_brands()

# ─────────────────────────────────────────────────────────────────────────────
# INITIALIZE SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if 'ai_mapping' not in st.session_state:
    st.session_state.ai_mapping = None
if 'last_uploaded_file' not in st.session_state:
    st.session_state.last_uploaded_file = None

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — Task Setup
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Task Setup")
    st.info("⚠️ Required: Fill all fields to unlock data processing.")

    case_id     = st.text_input("Case ID",     placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")

    talabat_countries = [
        "", "Egypt", "United Arab Emirates", "Kuwait",
        "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"
    ]
    country = st.selectbox("Country", options=talabat_countries)

    task_ready = bool(case_id.strip() and client_name.strip() and country)
    
    st.divider()
    st.metric("Brands in Database", f"{len(master_brands_list):,}") # Added Metric
    
    st.header("📋 System Rules")
    st.write("**Target Schema:**")
    st.code("""
- pieceBarcode
- brand_id
- productTitle::en
- imageUrls
- contentsValue
- contentsUnit
    """, language="markdown")

    st.divider()
    st.header("🧠 Title Engine v3.3") # Updated Version
    st.caption(
        "Now features Nitro-Batch Translation and Master Brand ID matching. "
        "Handles weight (g/kg/mg), volume (ml/l/fl oz), "
        "multi-packs (6x90ml), singulars (1 Piece), "
        "and auto-audit for unbranded items."
    )

# ─────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v3.3")
display_name = st.session_state.get('user_name', 'There').title()
st.markdown(f"""
Hello **{display_name}** ❤️, I am **Alex**.  
An AI Assistant Created By **Mostafa Abdelaziz**.  
Now with **Nitro-Batch Translation** and **Master Brand Scanning** ✨
""")
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# FILE UPLOADER
# ─────────────────────────────────────────────────────────────────────────────
uploaded_file = st.file_uploader(
    "Drop the messy client file here (CSV or Excel)",
    type=["csv", "xlsx"]
)

# ─────────────────────────────────────────────────────────────────────────────
# ACCEPTABLE UNITS
# ─────────────────────────────────────────────────────────────────────────────
acceptable_units = [
    "bags", "bag", "bouquets - Flowers", "boxes", "box", "bunches", "bunch", "capsules", "capsule",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "packet", "pack", "packs", "pieces", "piece", "pc", "pcs", 
    "rolls", "roll", "sachets", "sachet", "sheets", "sheet", "tablets", "tablet", "units", "unit"
]

# ─────────────────────────────────────────────────────────────────────────────
# TARGET SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
target_schema = [
    "pieceBarcode", "productTitle::en",
    "imageUrls", "contentsValue", "contentsUnit",
]

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS FILE
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_file:
    if st.session_state.last_uploaded_file != uploaded_file.name:
        st.session_state.ai_mapping   = None
        st.session_state.last_uploaded_file = uploaded_file.name

    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)

        with st.expander("👀 View Raw Client Data (Click to expand)"):
            st.dataframe(df.head(5), use_container_width=True)

        st.write("### 📊 Submission Details")
        st.metric("Total Products Submitted", len(df))
        st.divider()

        headers = df.columns.tolist()
        sample  = df.head(3).to_dict(orient='records')

        # ─── STEP 1: AI COLUMN MAPPING ────────────────────────────────────
        if not task_ready:
            st.warning("🔒 **Action Required:** Please fill in the Case ID, Client Name, and Country in the sidebar.")
            st.button("🧠 Step 1: Map Columns with Alex", disabled=True)
        else:
            if st.button("🧠 Step 1: Map Columns with Alex", type="primary"):
                with st.spinner("Alex is analysing headers and patterns..."):
                    mapping_prompt = f"""
Map the client headers to our 'Target Schema': {target_schema}.
Client Headers: {headers}
Data Sample: {sample}

STRICT RULES:
1. 'pieceBarcode': Priority EAN > GTIN > UPC > Barcode.
2. 'productTitle::en': Choose descriptive English header.
3. 'contentsValue': Map Size/Weight/Volume. NEVER map Price.
4. 'contentsUnit': Map UOM/Unit.
5. 'imageUrls': Map URL/Link.
Return ONLY JSON: {{"Target_Field": "Client_Header"}}
"""
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You output strict JSON."},
                            {"role": "user",   "content": mapping_prompt},
                        ],
                        response_format={"type": "json_object"},
                    )
                    st.session_state.ai_mapping = json.loads(response.choices[0].message.content)

        # ─── STEP 2: MANUAL OVERRIDE ───────────────────────────────────────
        if st.session_state.ai_mapping is not None:
            with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
                with st.form("manual_mapping_form"):
                    final_mapping = {}
                    options = ["--- Leave Blank ---"] + headers
                    for target_col in target_schema:
                        ai_suggested = st.session_state.ai_mapping.get(target_col)
                        default_idx  = options.index(ai_suggested) if ai_suggested in options else 0
                        final_mapping[target_col] = st.selectbox(f"Map '{target_col}' to:", options=options, index=default_idx)
                    submitted = st.form_submit_button("🚀 Step 3: Run Master Cleanse & Nitro Translate", type="primary")

            # ─── STEP 3: DEEP HYGIENE + SMART TITLE FORMAT + TRANSLATION ──
            if submitted:
                start_time = time.time()
                with st.spinner("🧠 Running Master Cleanse & Nitro-Batch Translation..."):
                    active_mapping = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}

                    cleaned_df = pd.DataFrame()
                    for internal_name in target_schema:
                        cleaned_df[internal_name] = df[active_mapping[internal_name]] if internal_name in active_mapping and active_mapping[internal_name] in df.columns else ""

                    # Re-insert Brand ID and Setup tracking
                    cleaned_df.insert(1, 'brand_id', "")
                    cleaned_df['productTitle::ar'] = ""
                    cleaned_df['_title_confidence'] = ""
                    cleaned_df['_title_changes']    = ""

                    feedback_notes = []
                    titles_to_translate = []

                    for index, row in cleaned_df.iterrows():
                        doubts = []

                        # ── 1. Barcode ────────────────────
                        raw_barcode = str(row.get('pieceBarcode', '')).replace('.0', '').strip()
                        if raw_barcode in ['', 'nan', 'none']:
                            doubts.append("Missing Barcode")
                            cleaned_df.at[index, 'pieceBarcode'] = ""
                        else:
                            cleaned_df.at[index, 'pieceBarcode'] = f"'{raw_barcode.zfill(13)}"

                        # ── 2. SMART TITLE FORMATTING (v3.0 DB Logic) ───────
                        raw_title = str(row.get('productTitle::en', '')).replace('nan', '').strip()
                        
                        # Pass master brands list to the formatter
                        title_result = smart_format_title(raw_title, brands_list=master_brands_list)

                        formatted_title = title_result['formatted_title']
                        confidence      = title_result['confidence']
                        
                        cleaned_df.at[index, 'productTitle::en'] = formatted_title
                        cleaned_df.at[index, 'brand_id'] = title_result['brand_id']
                        cleaned_df.at[index, '_title_confidence'] = confidence
                        titles_to_translate.append(formatted_title if formatted_title else "N/A")

                        if formatted_title != raw_title and raw_title:
                            cleaned_df.at[index, '_title_changes'] = f"{raw_title} → {formatted_title}"

                        if "Unbranded - Audit Required" in title_result['issues']:
                            doubts.append("⚠️ Unbranded - Audit Required")

                        # ── 3. FALLBACK SIZE EXTRACTION ─────────────────────────
                        cv_raw = str(row.get('contentsValue', '')).replace('nan', '').strip()
                        cu_raw = str(row.get('contentsUnit', '')).replace('nan', '').strip()
                        
                        if (not cv_raw or cv_raw in ('0', '0.0')) and title_result['extracted_size']:
                            m = re.search(r'(\d+(?:\.\d+)?)?\s*([a-zA-Z]+)', title_result['extracted_size'])
                            if m:
                                cleaned_df.at[index, 'contentsValue'] = m.group(1) if m.group(1) else "1"
                                cleaned_df.at[index, 'contentsUnit'] = m.group(2).lower()

                        # Validation
                        val_now = str(cleaned_df.at[index, 'contentsValue']).strip()
                        unit_now = str(cleaned_df.at[index, 'contentsUnit']).strip().lower()

                        if not val_now or val_now == 'nan': doubts.append("Missing Qty")
                        if not unit_now or unit_now == 'nan': doubts.append("Missing Unit")
                        elif unit_now not in [u.lower() for u in acceptable_units]: doubts.append(f"Invalid Unit '{unit_now}'")

                        # ── 4. URL Sanity Check ───────────────────────────
                        raw_url = str(row.get('imageUrls', '')).strip().lower()
                        if raw_url in ['', 'nan', 'none']: doubts.append("Missing Image")

                        feedback_notes.append("✅ Ready for Catalogue" if not doubts else "⚠️ " + ", ".join(doubts))

                    # ── 5. NITRO BATCH TRANSLATION (Fast Fix) ─────────────────────────
                    try:
                        translator = GoogleTranslator(source='en', target='ar')
                        # Process in chunks of 30 to prevent timeouts/errors
                        chunk_size = 30
                        translated_final = []
                        for i in range(0, len(titles_to_translate), chunk_size):
                            chunk = titles_to_translate[i : i + chunk_size]
                            translated_final.extend(translator.translate_batch(chunk))
                        cleaned_df['productTitle::ar'] = translated_final
                    except:
                        cleaned_df['productTitle::ar'] = "Translation Batch Error"

                    cleaned_df['Catalogue_Feedback'] = feedback_notes

                    # ── EXCEL MASTERPIECE BUILDER ─────────────────────────
                    st.success(f"✅ Processing Complete in {time.time() - start_time:.1f}s")

                    ready_df   = cleaned_df[cleaned_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"]
                    error_df   = cleaned_df[cleaned_df['Catalogue_Feedback'].str.contains("⚠️")]
                    changed_df = cleaned_df[cleaned_df['_title_changes'] != ""].copy()

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("✅ Ready for Catalogue", len(ready_df))
                    col2.metric("⚠️ Needing Attention",   len(error_df))
                    col3.metric("🏷️ Brands ID Identified", len(cleaned_df[cleaned_df['brand_id'] != ""]))
                    col4.metric("📊 Accuracy Rate", f"{(len(ready_df)/len(cleaned_df))*100:.1f}%" if len(cleaned_df) > 0 else "0%")
                    
                    st.write("---")
                    
                    # Excel Generation
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        export_cols = [c for c in cleaned_df.columns if not c.startswith('_')]
                        cleaned_df[export_cols].to_excel(writer, index=False, sheet_name="Master Catalogue")
                        ready_df[export_cols].to_excel(writer, index=False, sheet_name="✅ Ready")
                        if len(error_df) > 0:
                            error_df[export_cols].to_excel(writer, index=False, sheet_name="⚠️ Review Required")

                    st.download_button(
                        label=f"📥 Download Enterprise Excel Report",
                        data=output.getvalue(),
                        file_name=f"{case_id}_{client_name}_Nitro_v3.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True,
                    )

                    st.dataframe(cleaned_df, use_container_width=True)

    except Exception as e:
        st.error(f"An error occurred: {e}")