import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
import time
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────────────────────────────────────
# Import Background Helper
# ─────────────────────────────────────────────────────────────────────────────
from smart_title_formatter import format_title as smart_format_title

# ─────────────────────────────────────────────────────────────────────────────
# 🔒 AUTHENTICATION & SESSION MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
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
# MASTER BRANDS CACHE (Lightning Fast DB)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_master_brands():
    try:
        df = pd.read_csv("master_brands.csv")
        df = df.dropna(subset=['brand_id', 'brand::en'])
        # Sort by length descending to match longest phrases first
        brands = df[['brand_id', 'brand::en']].drop_duplicates(subset=['brand::en']).copy()
        brands['len'] = brands['brand::en'].astype(str).str.len()
        brands = brands.sort_values(by='len', ascending=False)
        return brands[['brand_id', 'brand::en']].to_dict('records')
    except Exception as e:
        st.sidebar.error("⚠️ master_brands.csv not found or invalid.")
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
# SIDEBAR & UI STYLING
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Alex AI Wizard", page_icon="🤖", layout="wide")

with st.sidebar:
    st.header("⚙️ Task Setup")
    case_id     = st.text_input("Case ID",     placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")
    country = st.selectbox("Country", options=["", "Egypt", "United Arab Emirates", "Kuwait", "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"])
    task_ready = bool(case_id.strip() and client_name.strip() and country)
    
    st.divider()
    st.metric("Brands in Database", f"{len(master_brands_list):,}")
    st.info("Alex v3.2: Turbo Translation & Master Brand Scanning Active.")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v3.2")
display_name = st.session_state.get('user_name', 'Mostafa').title()
st.markdown(f"Hello **{display_name}** ❤️, I am **Alex**.\nAn AI Assistant Created By **Mostafa Abdelaziz**.")
st.divider()

uploaded_file = st.file_uploader("Drop the messy client file here (CSV or Excel)", type=["csv", "xlsx"])

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA & UNITS
# ─────────────────────────────────────────────────────────────────────────────
target_schema = ["pieceBarcode", "productTitle::en", "imageUrls", "contentsValue", "contentsUnit"]
acceptable_units = [
    "bags", "bag", "bouquets - Flowers", "boxes", "box", "bunches", "bunch", "capsules", "capsule",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "packet", "pack", "packs", "pieces", "piece", "pc", "pcs", 
    "rolls", "roll", "sachets", "sachet", "sheets", "sheet", "tablets", "tablet", "units", "unit"
]

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS FILE
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_file:
    if st.session_state.last_uploaded_file != uploaded_file.name:
        st.session_state.ai_mapping = None
        st.session_state.last_uploaded_file = uploaded_file.name

    df = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
    
    with st.expander("👀 View Raw Client Data"):
        st.dataframe(df.head(10), use_container_width=True)

    headers = df.columns.tolist()
    sample  = df.head(3).to_dict(orient='records')

    if not task_ready:
        st.warning("🔒 **Action Required:** Please fill in the Case ID, Client Name, and Country in the sidebar.")
    else:
        if st.button("🧠 Step 1: Map Columns with Alex", type="primary"):
            with st.spinner("Alex is analysing headers and data patterns..."):
                mapping_prompt = f"""
                You are Alex, an elite Data Engineer. Map the client headers to our 'Target Schema': {target_schema}.
                Client Headers: {headers}
                Data Sample: {sample}
                STRICT RULES:
                1. 'pieceBarcode': Priority EAN > GTIN > UPC > Barcode.
                2. 'productTitle::en': Choose the MOST descriptive English title.
                3. 'contentsValue': Map Size/Weight/Volume. NEVER map Price.
                4. 'contentsUnit': Map UOM/Unit.
                5. 'imageUrls': Map URL/Link/Photo.
                Return ONLY JSON: {{"Target_Field": "Client_Header"}}
                """
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "You output strict JSON."}, {"role": "user", "content": mapping_prompt}],
                    response_format={"type": "json_object"},
                )
                st.session_state.ai_mapping = json.loads(response.choices[0].message.content)

    if st.session_state.ai_mapping is not None:
        with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
            with st.form("manual_mapping_form"):
                final_mapping = {}
                options = ["--- Leave Blank ---"] + headers
                cols = st.columns(len(target_schema))
                for idx, col in enumerate(target_schema):
                    ai_suggested = st.session_state.ai_mapping.get(col)
                    s_idx = options.index(ai_suggested) if ai_suggested in options else 0
                    final_mapping[col] = cols[idx].selectbox(f"Map '{col}':", options=options, index=s_idx)
                submitted = st.form_submit_button("🚀 Step 3: Run Master Cleanse & Turbo Translate", type="primary")

        if submitted:
            start_time = time.time()
            with st.spinner("🧠 Scanning Brands & Running Turbo Translation..."):
                active_mapping = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}
                
                cleaned_df = pd.DataFrame()
                for c in target_schema:
                    cleaned_df[c] = df[active_mapping[c]] if c in active_mapping and active_mapping[c] in df.columns else ""

                cleaned_df.insert(1, 'brand_id', "")
                cleaned_df['productTitle::ar'] = ""
                cleaned_df['_title_confidence'] = ""
                
                feedback_notes = []
                titles_to_translate = []

                # --- STEP A: LOGIC & BRAND SCANNING ---
                for index, row in cleaned_df.iterrows():
                    doubts = []
                    
                    # Barcode handling
                    raw_bc = str(row.get('pieceBarcode', '')).replace('.0', '').strip()
                    cleaned_df.at[index, 'pieceBarcode'] = f"'{raw_bc.zfill(13)}" if raw_bc not in ['', 'nan'] else ""
                    if not raw_bc or raw_bc == 'nan': doubts.append("Missing Barcode")

                    # Title & Brand
                    raw_title = str(row.get('productTitle::en', '')).replace('nan', '').strip()
                    title_res = smart_format_title(raw_title, brands_list=master_brands_list)
                    
                    cleaned_df.at[index, 'productTitle::en'] = title_res['formatted_title']
                    cleaned_df.at[index, 'brand_id'] = title_res['brand_id']
                    cleaned_df.at[index, '_title_confidence'] = title_res['confidence']
                    
                    titles_to_translate.append(title_res['formatted_title'] if title_res['formatted_title'] else "N/A")

                    if "Unbranded - Audit Required" in title_res['issues']:
                        doubts.append("⚠️ Unbranded - Audit Required")

                    # Qty & Unit Logic
                    cv_raw = str(row.get('contentsValue', '')).replace('nan', '').strip()
                    cu_raw = str(row.get('contentsUnit', '')).replace('nan', '').strip()
                    
                    # Fix for "1 Piece" / "kg" issues
                    if (not cv_raw or cv_raw == '0') and title_res['extracted_size']:
                        m = re.search(r'(\d+(?:\.\d+)?)?\s*([a-zA-Z]+)', title_res['extracted_size'])
                        if m:
                            cleaned_df.at[index, 'contentsValue'] = m.group(1) if m.group(1) else "1"
                            cleaned_df.at[index, 'contentsUnit'] = m.group(2).lower()
                    
                    curr_val = str(cleaned_df.at[index, 'contentsValue']).strip()
                    curr_unit = str(cleaned_df.at[index, 'contentsUnit']).strip().lower()

                    if not curr_val or curr_val == 'nan': doubts.append("Missing Qty")
                    if not curr_unit or curr_unit == 'nan': doubts.append("Missing Unit")
                    elif curr_unit not in [u.lower() for u in acceptable_units]: doubts.append(f"Invalid Unit ({curr_unit})")

                    if not str(row.get('imageUrls', '')).strip(): doubts.append("Missing Image")

                    feedback_notes.append("✅ Ready for Catalogue" if not doubts else " | ".join(doubts))

                # --- STEP B: TURBO BATCH TRANSLATION ---
                try:
                    # Chunks of 50 for max speed without hitting limits
                    batch_translator = GoogleTranslator(source='en', target='ar')
                    translated_list = batch_translator.translate_batch(titles_to_translate)
                    cleaned_df['productTitle::ar'] = translated_list
                except Exception as e:
                    cleaned_df['productTitle::ar'] = "Translation Failed"

                cleaned_df['Catalogue_Feedback'] = feedback_notes

                # --- UI RE-BUILDING ---
                st.success(f"✅ Processing Complete in {time.time() - start_time:.1f}s")
                
                ready_df = cleaned_df[cleaned_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"]
                error_df = cleaned_df[cleaned_df['Catalogue_Feedback'] != "✅ Ready for Catalogue"]
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("✅ Ready", len(ready_df))
                m2.metric("⚠️ Action Required", len(error_df))
                m3.metric("🏷️ Brands Identified", len(cleaned_df[cleaned_df['brand_id'] != ""]))
                m4.metric("Accuracy Score", f"{(len(ready_df)/len(cleaned_df))*100:.1f}%")

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    export_df = cleaned_df[[c for c in cleaned_df.columns if not c.startswith('_')]]
                    export_df[export_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"].to_excel(writer, index=False, sheet_name="✅ Ready")
                    export_df[export_df['Catalogue_Feedback'] != "✅ Ready for Catalogue"].to_excel(writer, index=False, sheet_name="⚠️ Review Required")
                
                st.download_button("📥 Download Final Catalogue", output.getvalue(), f"{case_id}_Alex_v3.2.xlsx", type="primary", use_container_width=True)
                st.dataframe(cleaned_df, use_container_width=True)