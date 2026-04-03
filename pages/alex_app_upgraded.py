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

# 🔒 AUTHENTICATION CHECK
if not st.session_state.get('authenticated', False):
    st.warning("🛑 Access Denied. Please login first.")
    st.stop()

# SETUP AI
github_token = st.secrets["GITHUB_TOKEN"]
client = OpenAI(base_url="https://models.inference.ai.azure.com", api_key=github_token)

@st.cache_data(show_spinner=False)
def load_master_brands():
    try:
        df = pd.read_csv("master_brands.csv")
        df = df.dropna(subset=['brand_id', 'brand::en'])
        brands = df[['brand_id', 'brand::en']].drop_duplicates(subset=['brand::en']).copy()
        brands['len'] = brands['brand::en'].astype(str).str.len()
        return brands.sort_values(by='len', ascending=False)[['brand_id', 'brand::en']].to_dict('records')
    except: return []

master_brands_list = load_master_brands()

if 'ai_mapping' not in st.session_state: st.session_state.ai_mapping = None

# SIDEBAR
with st.sidebar:
    st.header("⚙️ Task Setup")
    case_id = st.text_input("Case ID")
    client_name = st.text_input("Client Name")
    country = st.selectbox("Country", ["", "Egypt", "UAE", "Kuwait", "Qatar", "Bahrain", "Oman", "Iraq", "Jordan"])
    task_ready = bool(case_id and client_name and country)
    st.divider()
    st.metric("Brand DB Size", len(master_brands_list))

st.title("🤖 Alex Turbo v3.1")
uploaded_file = st.file_uploader("Upload Client File", type=["csv", "xlsx"])

target_schema = ["pieceBarcode", "productTitle::en", "imageUrls", "contentsValue", "contentsUnit"]
acceptable_units = ["g", "kg", "ml", "l", "piece", "pcs", "pack", "box", "sachet", "tablet", "roll"]

if uploaded_file:
    df = pd.read_csv(uploaded_file, dtype=str) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, dtype=str)
    headers = df.columns.tolist()

    if task_ready and st.button("🧠 Step 1: Map Columns"):
        mapping_prompt = f"Map {headers} to {target_schema}. Return JSON only."
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": mapping_prompt}],
            response_format={"type": "json_object"}
        )
        st.session_state.ai_mapping = json.loads(response.choices[0].message.content)

    if st.session_state.ai_mapping:
        with st.form("process_form"):
            final_mapping = {col: st.selectbox(f"Map {col}", ["---"] + headers, index=(headers.index(st.session_state.ai_mapping.get(col))+1 if st.session_state.ai_mapping.get(col) in headers else 0)) for col in target_schema}
            submitted = st.form_submit_button("🚀 Run Turbo Cleanse")

        if submitted:
            with st.spinner("Processing..."):
                active_map = {k: v for k, v in final_mapping.items() if v != "---"}
                cleaned_df = pd.DataFrame()
                for c in target_schema:
                    cleaned_df[c] = df[active_map[c]] if c in active_map else ""

                cleaned_df.insert(1, 'brand_id', "")
                feedback_notes = []
                titles_to_translate = []

                # Part 1: Fast Formatting & Brand Check
                for idx, row in cleaned_df.iterrows():
                    res = smart_format_title(str(row['productTitle::en']), master_brands_list)
                    cleaned_df.at[idx, 'productTitle::en'] = res['formatted_title']
                    cleaned_df.at[idx, 'brand_id'] = res['brand_id']
                    titles_to_translate.append(res['formatted_title'] if res['formatted_title'] else "Empty")
                    
                    # Logic for feedback (missing qty, unit, etc.)
                    doubts = []
                    if not res['brand_id']: doubts.append("⚠️ Unbranded")
                    if not str(row['pieceBarcode']).strip(): doubts.append("Missing Barcode")
                    feedback_notes.append("✅ Ready" if not doubts else " | ".join(doubts))

                # Part 2: TURBO BATCH TRANSLATION
                try:
                    # Translate in chunks of 50 to avoid timeout but stay fast
                    full_translated = GoogleTranslator(source='en', target='ar').translate_batch(titles_to_translate)
                    cleaned_df['productTitle::ar'] = full_translated
                except:
                    cleaned_df['productTitle::ar'] = "Translation Error"

                cleaned_df['Catalogue_Feedback'] = feedback_notes
                
                st.success("Done!")
                st.dataframe(cleaned_df)
                
                # Export
                output = io.BytesIO()
                cleaned_df.to_excel(output, index=False)
                st.download_button("📥 Download Results", output.getvalue(), f"{case_id}.xlsx", type="primary")