import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────────────────────────────────────
# Import Background Helper
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
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Task Setup")
    case_id     = st.text_input("Case ID",     placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")
    country = st.selectbox("Country", options=["", "Egypt", "United Arab Emirates", "Kuwait", "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"])
    task_ready = bool(case_id.strip() and client_name.strip() and country)
    
    st.divider()
    st.metric("Brands in Database", len(master_brands_list))
    st.caption("v3.0 Engine: Auto-Scanning titles against Master Database. Preserving Promotional Text (Value Pack, etc).")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v3.0")
display_name = st.session_state.get('user_name', 'There').title()
st.markdown(f"Hello **{display_name}** ❤️, I am **Alex**.\nAn AI Assistant Created By **Mostafa Abdelaziz**.")
st.divider()

uploaded_file = st.file_uploader("Drop the messy client file here (CSV or Excel)", type=["csv", "xlsx"])

# ─────────────────────────────────────────────────────────────────────────────
# ACCEPTABLE UNITS (Added Singulars)
# ─────────────────────────────────────────────────────────────────────────────
acceptable_units = [
    "bags", "bag", "bouquets - Flowers", "boxes", "box", "bunches", "bunch", "capsules", "capsule",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "packet", "pack", "packs", "pieces", "piece", "pc", "pcs", 
    "rolls", "roll", "sachets", "sachet", "sheets", "sheet", "tablets", "tablet", "units", "unit"
]

target_schema = ["pieceBarcode", "productTitle::en", "imageUrls", "contentsValue", "contentsUnit"]

# ─────────────────────────────────────────────────────────────────────────────
# PROCESS FILE
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_file:
    if st.session_state.last_uploaded_file != uploaded_file.name:
        st.session_state.ai_mapping = None
        st.session_state.last_uploaded_file = uploaded_file.name

    df = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
    
    with st.expander("👀 View Raw Client Data"):
        st.dataframe(df.head(5), use_container_width=True)

    headers = df.columns.tolist()
    sample  = df.head(3).to_dict(orient='records')

    if not task_ready:
        st.warning("🔒 **Action Required:** Please fill in the Case ID, Client Name, and Country.")
    else:
        if st.button("🧠 Step 1: Map Columns with Alex", type="primary"):
            with st.spinner("Alex is analysing headers..."):
                prompt = f"""Map headers to: {target_schema}. Client Headers: {headers}. Sample: {sample}. Return strict JSON {{"Target_Field": "Client_Header"}}. Omit if no match."""
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "You output strict JSON."}, {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                st.session_state.ai_mapping = json.loads(response.choices[0].message.content)

    if st.session_state.ai_mapping is not None:
        with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
            with st.form("manual_mapping_form"):
                final_mapping = {}
                options = ["--- Leave Blank ---"] + headers
                for col in target_schema:
                    ai_suggested = st.session_state.ai_mapping.get(col)
                    idx = options.index(ai_suggested) if ai_suggested in options else 0
                    final_mapping[col] = st.selectbox(f"Map '{col}':", options=options, index=idx)
                submitted = st.form_submit_button("🚀 Step 3: Run Master Cleanse & Translate", type="primary")

        if submitted:
            with st.spinner("🧠 Scanning Brands... Normalizing Units..."):
                active_mapping = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}
                
                cleaned_df = pd.DataFrame()
                for c in target_schema:
                    cleaned_df[c] = df[active_mapping[c]] if c in active_mapping and active_mapping[c] in df.columns else ""

                # Inject brand_id column at the front
                cleaned_df.insert(1, 'brand_id', "")
                cleaned_df['productTitle::ar'] = ""
                cleaned_df['_title_confidence'] = ""
                cleaned_df['_title_changes'] = ""

                translator_ar = GoogleTranslator(source='auto', target='ar')
                feedback_notes = []

                for index, row in cleaned_df.iterrows():
                    doubts = []

                    # 1. Barcode
                    raw_bc = str(row.get('pieceBarcode', '')).replace('.0', '').strip()
                    if raw_bc in ['', 'nan', 'none']: 
                        doubts.append("Missing Barcode")
                        cleaned_df.at[index, 'pieceBarcode'] = ""
                    else: 
                        cleaned_df.at[index, 'pieceBarcode'] = f"'{raw_bc.zfill(13)}"

                    # 2. Format Title & Extract Brand
                    raw_title = str(row.get('productTitle::en', '')).replace('nan', '').strip()
                    
                    title_result = smart_format_title(raw_title, brands_list=master_brands_list)
                    
                    cleaned_df.at[index, 'productTitle::en'] = title_result['formatted_title']
                    cleaned_df.at[index, 'brand_id'] = title_result['brand_id']
                    cleaned_df.at[index, '_title_confidence'] = title_result['confidence']
                    
                    if title_result['formatted_title'] != raw_title and raw_title:
                        cleaned_df.at[index, '_title_changes'] = f"{raw_title} → {title_result['formatted_title']}"

                    if "Unbranded - Audit Required" in title_result['issues']:
                        doubts.append("⚠️ Unbranded - Audit Required")

                    # 3. Translation
                    if title_result['formatted_title']:
                        try: cleaned_df.at[index, 'productTitle::ar'] = translator_ar.translate(title_result['formatted_title'])
                        except: cleaned_df.at[index, 'productTitle::ar'] = "Translation Failed"

                    # 4. Floating Unit & QTY Fix
                    cv_raw = str(row.get('contentsValue', '')).replace('nan', '').strip()
                    cu_raw = str(row.get('contentsUnit', '')).replace('nan', '').strip()
                    
                    val_missing = not cv_raw or cv_raw in ('0', '0.0')
                    unit_missing = not cu_raw

                    ext_size = title_result['extracted_size'].lower()
                    
                    # If we found a floating unit like "kg" or "piece" with no number
                    if ext_size and val_missing:
                        match = re.fullmatch(r'(?i)(\d+(?:\.\d+)?)?\s*(' + '|'.join(acceptable_units) + r')\b', ext_size)
                        if match:
                            num = match.group(1) or "1" # Auto assign 1 if no number
                            unit = match.group(2).lower()
                            cleaned_df.at[index, 'contentsValue'] = num
                            cleaned_df.at[index, 'contentsUnit'] = unit
                            val_missing, unit_missing = False, False

                    if val_missing: doubts.append("Missing Qty")
                    
                    u_val = str(cleaned_df.at[index, 'contentsUnit']).strip().lower()
                    if u_val not in [u.lower() for u in acceptable_units] and u_val != '':
                        doubts.append(f"Invalid Unit '{u_val}'")
                    elif u_val == '':
                        doubts.append("Missing Unit")

                    raw_url = str(row.get('imageUrls', '')).strip().lower()
                    if raw_url in ['', 'nan', 'none']: doubts.append("Missing Image")

                    feedback_notes.append("✅ Ready for Catalogue" if not doubts else " | ".join(doubts))

                cleaned_df['Catalogue_Feedback'] = feedback_notes

                # ── EXCEL BUILDER ──
                st.success("✅ Brand Scan, Formatting & Translations Complete!")
                
                ready_df = cleaned_df[cleaned_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"]
                error_df = cleaned_df[cleaned_df['Catalogue_Feedback'] != "✅ Ready for Catalogue"]
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("✅ Ready", len(ready_df))
                col2.metric("⚠️ Action Required", len(error_df))
                col3.metric("🏷️ Brands Identified", len(cleaned_df[cleaned_df['brand_id'] != ""]))
                col4.metric("Quality Score", f"{(len(ready_df)/len(cleaned_df))*100:.1f}%" if len(cleaned_df) > 0 else "0%")

                export_cols = [c for c in cleaned_df.columns if not c.startswith('_')]
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    ready_df[export_cols].to_excel(writer, index=False, sheet_name="✅ Ready to Import")
                    if len(error_df) > 0:
                        error_df[export_cols].to_excel(writer, index=False, sheet_name="⚠️ Action Required")
                
                out_name = f"{case_id}_{client_name}_v3.xlsx"
                st.download_button(f"📥 Download Excel ({out_name})", data=output.getvalue(), file_name=out_name, type="primary", use_container_width=True)

                st.dataframe(error_df if len(error_df) > 0 else ready_df, use_container_width=True)