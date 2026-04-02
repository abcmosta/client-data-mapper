import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re

# --- UI PAGE CONFIGURATION ---
st.set_page_config(page_title="Content Wizard Optimizer", page_icon="🌀", layout="wide", initial_sidebar_state="expanded")

# --- SETUP THE AI BRAIN ---
github_token = st.secrets["GITHUB_TOKEN"]
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=github_token 
)

# --- SIDEBAR (Task Setup & Settings) ---
with st.sidebar:
    st.header("⚙️ Task Setup")
    st.info("⚠️ Required: Fill all fields to unlock data processing.")
    
    # 1. New Mandatory Input Fields
    case_id = st.text_input("Case ID", placeholder="e.g., CAS-12345")
    client_name = st.text_input("Client Name", placeholder="e.g., Carrefour")
    
    # 2. Strict Country Dropdown (Egypt + GCC)
    talabat_countries = ["", "Egypt", "United Arab Emirates", "Kuwait", "Qatar", "Bahrain", "Oman"]
    country = st.selectbox("Country", options=talabat_countries)
    
    # 3. The "Validation Lock" Logic
    task_ready = bool(case_id.strip() and client_name.strip() and country)
    
    st.divider()
    
    st.header("📋 System Rules")
    st.write("**Target Schema:**")
    st.code("""
- pieceBarcode
- brandName
- productTitle::en
- imageUrls
- contentsValue
- contentsUnit
    """, language="markdown")

# --- MAIN APP HEADER ---
st.title("📦 Catalogue Onboarding Assistant")
st.markdown("Automate data mapping, extract units, and validate catalogue readiness in seconds.")
st.divider()

# --- FILE UPLOADER ---
uploaded_file = st.file_uploader("Drop the messy client file here (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        with st.expander("👀 View Raw Client Data (Click to expand)"):
            st.dataframe(df.head(5), use_container_width=True)
            
        # --- NEW UI: Pre-Processing Metrics ---
        st.write("### 📊 Submission Details")
        st.metric("Total Products Submitted", len(df))
        st.divider()
        
        headers = df.columns.tolist()
        sample = df.head(3).to_dict(orient='records')
        
        target_schema = ["pieceBarcode", "brandName", "productTitle::en", "imageUrls", "contentsValue", "contentsUnit"]
        acceptable_units = ["bags", "bouquets - Flowers", "boxes", "bunches", "capsules", "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m", "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets", "sheets", "tablets", "units"]
        
        # --- THE VALIDATION LOCK ---
        if not task_ready:
            st.warning("🔒 **Action Required:** Please fill in the Case ID, Client Name, and Country in the left sidebar to unlock the AI mapping engine.")
            st.button("🧠 Map & Validate Catalogue", disabled=True)
        else:
            # If everything is filled, unlock the primary button!
            if st.button("🧠 Map & Validate Catalogue", type="primary"):
                with st.spinner("AI is mapping columns and extracting missing units..."):
                    
                    mapping_prompt = f"""
                    Map the client headers to this exact case-sensitive schema: {target_schema}.
                    Client Headers: {headers}
                    Sample Data: {sample}
                    Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You output strict JSON."},
                            {"role": "user", "content": mapping_prompt}
                        ],
                        response_format={ "type": "json_object" }
                    )
                    mapping_dict = json.loads(response.choices[0].message.content)
                    
                    cleaned_df = pd.DataFrame()
                    for internal_name in target_schema:
                        client_name = mapping_dict.get(internal_name)
                        if client_name and client_name in df.columns:
                            cleaned_df[internal_name] = df[client_name]
                        else:
                            cleaned_df[internal_name] = "" 
                    
                    if "productTitle::en" in cleaned_df.columns:
                        cleaned_df["productTitle::en"] = cleaned_df["productTitle::en"].astype(str).str.title().replace('Nan', '')
                        unit_regex = '|'.join([u.lower() for u in acceptable_units])
                        pattern = r'(?i)(\d+(?:\.\d+)?)\s*(' + unit_regex + r')\b'
                        
                        for index, row in cleaned_df.iterrows():
                            title = str(row['productTitle::en'])
                            val_missing = pd.isna(row.get('contentsValue')) or str(row.get('contentsValue')).strip() in ['', 'nan']
                            unit_missing = pd.isna(row.get('contentsUnit')) or str(row.get('contentsUnit')).strip() in ['', 'nan']
                            
                            if val_missing or unit_missing:
                                match = re.search(pattern, title)
                                if match:
                                    if val_missing: cleaned_df.at[index, 'contentsValue'] = match.group(1)
                                    if unit_missing: cleaned_df.at[index, 'contentsUnit'] = match.group(2).lower()
                    
                    feedback_notes = []
                    for index, row in cleaned_df.iterrows():
                        doubts = []
                        if pd.isna(row.get('pieceBarcode')) or str(row.get('pieceBarcode')).strip() in ['', 'nan']: doubts.append("Missing Barcode")
                        if pd.isna(row.get('contentsValue')) or str(row.get('contentsValue')).strip() in ['', 'nan']: doubts.append("Missing Qty")
                        
                        unit = str(row.get('contentsUnit')).strip().lower()
                        if unit not in [u.lower() for u in acceptable_units] and unit not in ['', 'nan']: doubts.append(f"Invalid Unit '{unit}'")
                        elif unit in ['', 'nan']: doubts.append("Missing Unit")
                            
                        if pd.isna(row.get('imageUrls')) or str(row.get('imageUrls')).strip() in ['', 'nan']: doubts.append("Missing Image")
                            
                        if not doubts: feedback_notes.append("✅ Ready for Catalogue")
                        else: feedback_notes.append("⚠️ " + ", ".join(doubts))
                            
                    cleaned_df['Catalogue_Feedback'] = feedback_notes
                    
                    st.success("Processing Complete!")
                    
                    total_rows = len(cleaned_df)
                    flagged_rows = cleaned_df['Catalogue_Feedback'].str.contains("⚠️").sum()
                    clean_rows = total_rows - flagged_rows
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("✅ Ready for Catalogue", clean_rows)
                    col2.metric("⚠️ Needing Attention", flagged_rows)
                    col3.metric("📊 Completion Rate", f"{(clean_rows/total_rows)*100:.1f}%")
                    
                    st.write("---")
                    
                    # --- NEW: Dynamic Output File Naming ---
                    output_filename = f"{case_id} - {client_name} - {country}_Content_Wizzard.csv"
                    
                    tab1, tab2 = st.tabs(["📊 Final Full Catalogue", "🚨 Needs Fixing (Filtered)"])
                    
                    with tab1:
                        st.dataframe(cleaned_df, use_container_width=True)
                        csv = cleaned_df.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Download Full CSV", data=csv, file_name=output_filename, mime="text/csv", type="primary")
                        
                    with tab2:
                        error_df = cleaned_df[cleaned_df['Catalogue_Feedback'].str.contains("⚠️")]
                        if len(error_df) > 0:
                            st.warning("These rows require manual review by a Catalogue Specialist.")
                            st.dataframe(error_df, use_container_width=True)
                            error_csv = error_df.to_csv(index=False).encode('utf-8')
                            
                            # Give the error file a slightly modified name so they don't get mixed up
                            error_filename = f"ERRORS_ONLY_{output_filename}"
                            st.download_button("📥 Download Only Errors", data=error_csv, file_name=error_filename, mime="text/csv")
                        else:
                            st.balloons()
                            st.success("Wow! No errors found. The whole file is perfect.")
                    
    except Exception as e:
        st.error(f"An error occurred: {e}")