import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
from deep_translator import GoogleTranslator

# --- 🔒 AUTHENTICATION CHECK (THE BOUNCER) ---
if not st.session_state.get('authenticated', False):
    st.warning("🛑 Access Denied. Please go to the main Login page and enter the Master Key.")
    st.stop()

# --- SETUP THE AI BRAIN ---
github_token = st.secrets["GITHUB_TOKEN"]
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=github_token 
)

# ... (Keep all your initialization and sidebar code the same) ...

# --- MAIN APP HEADER ---
st.title("🤖 Alex, The Invincible")

display_name = st.session_state.get('user_name', 'There').title()

st.markdown(f"""
Hello **{display_name}** ❤️, I am **Alex**. 
An AI Assistant Created By **Mostafa Abdelaziz**. 
I am your window for more efficient data work. Just upload the raw vendor file and let me do my magic ✨.
""")
st.divider()

# ... (The rest of your Alex code stays exactly the same!) ...

# --- FILE UPLOADER ---
uploaded_file = st.file_uploader("Drop the messy client file here (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file:
    if st.session_state.last_uploaded_file != uploaded_file.name:
        st.session_state.ai_mapping = None
        st.session_state.last_uploaded_file = uploaded_file.name

    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, dtype=str)
        else:
            df = pd.read_excel(uploaded_file, dtype=str)
            
        with st.expander("👀 View Raw Client Data (Click to expand)"):
            st.dataframe(df.head(5), use_container_width=True)
            
        headers = df.columns.tolist()
        sample = df.head(3).to_dict(orient='records')
        
        target_schema = ["pieceBarcode", "brandName", "productTitle::en", "imageUrls", "contentsValue", "contentsUnit"]
        acceptable_units = ["bags", "bouquets - Flowers", "boxes", "bunches", "capsules", "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m", "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets", "sheets", "tablets", "units"]
        
        if not task_ready:
            st.warning("🔒 **Action Required:** Please fill in the Case ID, Client Name, and Country in the left sidebar to unlock Alex.")
            st.button("🧠 Step 1: Map Columns with Alex", disabled=True)
        else:
            # ==========================================
            # STEP 1: AI MAPPING
            # ==========================================
            if st.button("🧠 Step 1: Map Columns with Alex", type="primary"):
                with st.spinner("Alex is analyzing headers and patterns..."):
                    mapping_prompt = f"""
                    You are Alex, an elite Data Engineer. 
                    Map the client headers to our 'Target Schema': {target_schema}.
                    Client Headers: {headers}
                    Data Sample: {sample}

                    STRICT RULES:
                    1. 'pieceBarcode': Priority EAN > GTIN > UPC > Barcode > Item Code. 
                    2. 'productTitle::en': Priority Long Description > Title > Name.
                    3. 'contentsValue': 🚨 NEVER map Price, Cost, MSRP. Ignore financial columns.
                    4. 'contentsUnit': 🚨 NEVER map currency symbols.
                    5. 'imageUrls': Look for Link, URL, Photo.
                    6. 'brandName': Look for Vendor, Make, Brand.

                    Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}. 
                    If no valid match exists, omit it entirely.
                    """
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "You output strict JSON."}, {"role": "user", "content": mapping_prompt}],
                        response_format={ "type": "json_object" }
                    )
                    st.session_state.ai_mapping = json.loads(response.choices[0].message.content)

            # ==========================================
            # STEP 2: MANUAL OVERRIDE
            # ==========================================
            if st.session_state.ai_mapping is not None:
                with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
                    with st.form("manual_mapping_form"):
                        final_mapping = {}
                        options = ["--- Leave Blank ---"] + headers
                        for target_col in target_schema:
                            ai_suggested = st.session_state.ai_mapping.get(target_col)
                            default_idx = options.index(ai_suggested) if ai_suggested in options else 0
                            final_mapping[target_col] = st.selectbox(f"Map '{target_col}' to:", options=options, index=default_idx)
                        submitted = st.form_submit_button("🚀 Step 3: Run Master Cleanse & Translate", type="primary")

                # ==========================================
                # STEP 3: DEEP HYGIENE, TRANSLATION & VALIDATION
                # ==========================================
                if submitted:
                    with st.spinner("Washing data, translating titles (Ar/Ku), and building Excel Masterpiece..."):
                        active_mapping = {k: v for k, v in final_mapping.items() if v != "--- Leave Blank ---"}
                        cleaned_df = pd.DataFrame()
                        
                        for internal_name in target_schema:
                            if internal_name in active_mapping and active_mapping[internal_name] in df.columns:
                                cleaned_df[internal_name] = df[active_mapping[internal_name]]
                            else:
                                cleaned_df[internal_name] = "" 
                                
                        # Prepare the new Translation columns
                        cleaned_df['productTitle::ar'] = ""
                        cleaned_df['productTitle::ku'] = ""
                        
                        # Boot up the Translators (source='auto' lets it detect if the client gave us Arabic by mistake!)
                        translator_ar = GoogleTranslator(source='auto', target='ar')
                        translator_ku = GoogleTranslator(source='auto', target='ku')
                        
                        # --- THE CAR WASH (Deep Data Hygiene) ---
                        feedback_notes = []
                        
                        for index, row in cleaned_df.iterrows():
                            doubts = []
                            
                            # 1. Barcode Armor & Padding
                            raw_barcode = str(row.get('pieceBarcode', '')).replace('.0', '').strip()
                            if raw_barcode in ['', 'nan', 'none']:
                                doubts.append("Missing Barcode")
                                cleaned_df.at[index, 'pieceBarcode'] = ""
                            else:
                                clean_barcode = raw_barcode.zfill(13)
                                cleaned_df.at[index, 'pieceBarcode'] = f"'{clean_barcode}" 
                                
                            # 2. Title Whitespace Trim
                            title = str(row.get('productTitle::en', '')).replace('nan', '').strip()
                            title = re.sub(r'\s+', ' ', title).title() 
                            cleaned_df.at[index, 'productTitle::en'] = title
                            
                            # 3. Translation Engine
                            if title:
                                try:
                                    cleaned_df.at[index, 'productTitle::ar'] = translator_ar.translate(title)
                                    cleaned_df.at[index, 'productTitle::ku'] = translator_ku.translate(title)
                                except Exception:
                                    cleaned_df.at[index, 'productTitle::ar'] = "Translation Failed"
                                    cleaned_df.at[index, 'productTitle::ku'] = "Translation Failed"
                            
                            # 4. Smart Extraction
                            val_missing = pd.isna(row.get('contentsValue')) or str(row.get('contentsValue')).strip() in ['', 'nan']
                            unit_missing = pd.isna(row.get('contentsUnit')) or str(row.get('contentsUnit')).strip() in ['', 'nan']
                            
                            if val_missing or unit_missing:
                                unit_regex = '|'.join([u.lower() for u in acceptable_units])
                                match = re.search(r'(?i)(\d+(?:\.\d+)?)\s*(' + unit_regex + r')\b', title)
                                if match:
                                    if val_missing: 
                                        cleaned_df.at[index, 'contentsValue'] = match.group(1)
                                        val_missing = False
                                    if unit_missing: 
                                        cleaned_df.at[index, 'contentsUnit'] = match.group(2).lower()
                                        unit_missing = False

                            if val_missing: doubts.append("Missing Qty")
                            unit = str(cleaned_df.at[index, 'contentsUnit']).strip().lower()
                            if unit not in [u.lower() for u in acceptable_units] and unit not in ['', 'nan']: 
                                doubts.append(f"Invalid Unit '{unit}'")
                            elif unit in ['', 'nan']: 
                                doubts.append("Missing Unit")
                                
                            # 5. URL Sanity Check
                            raw_url = str(row.get('imageUrls', '')).strip().lower()
                            if raw_url in ['', 'nan', 'n/a', 'none']:
                                doubts.append("Missing Image")
                            elif not raw_url.startswith('http'):
                                doubts.append("Invalid Image URL Format")
                                
                            if not doubts: feedback_notes.append("✅ Ready for Catalogue")
                            else: feedback_notes.append("⚠️ " + ", ".join(doubts))
                                
                        cleaned_df['Catalogue_Feedback'] = feedback_notes
                        
                        # --- EXCEL MASTERPIECE BUILDER ---
                        st.success("Master Cleanse & Translations Complete!")
                        
                        ready_df = cleaned_df[cleaned_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"]
                        error_df = cleaned_df[cleaned_df['Catalogue_Feedback'].str.contains("⚠️")]
                        
                        total_rows = len(cleaned_df)
                        clean_rows = len(ready_df)
                        flagged_rows = len(error_df)
                        success_rate = f"{(clean_rows/total_rows)*100:.1f}%" if total_rows > 0 else "0%"
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("✅ Ready for Catalogue", clean_rows)
                        col2.metric("⚠️ Needing Attention", flagged_rows)
                        col3.metric("📊 Quality Score", success_rate)
                        st.write("---")
                        
                        summary_data = {
                            "Case ID": [case_id],
                            "Client Name": [client_name],
                            "Country": [country],
                            "Total Processed": [total_rows],
                            "Perfect Rows": [clean_rows],
                            "Rows Needing Fixes": [flagged_rows],
                            "Quality Score": [success_rate]
                        }
                        summary_df = pd.DataFrame(summary_data)
                        
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            summary_df.to_excel(writer, index=False, sheet_name="📊 Summary")
                            ready_df.to_excel(writer, index=False, sheet_name="✅ Ready to Import")
                            if flagged_rows > 0:
                                error_df.to_excel(writer, index=False, sheet_name="⚠️ Action Required")
                        excel_data = output.getvalue()
                        
                        output_filename = f"{case_id} - {client_name} - {country}_Content_Wizzard.xlsx"
                        
                        st.download_button(
                            label=f"📥 Download Enterprise Excel Report ({output_filename})", 
                            data=excel_data, 
                            file_name=output_filename, 
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                            type="primary",
                            use_container_width=True
                        )
                        
                        tab1, tab2 = st.tabs(["✅ Ready to Import", "⚠️ Action Required"])
                        with tab1:
                            st.dataframe(ready_df, use_container_width=True)
                        with tab2:
                            if flagged_rows > 0:
                                st.dataframe(error_df, use_container_width=True)
                            else:
                                st.success("No errors! Perfect file.")
                    
    except Exception as e:
        st.error(f"An error occurred: {e}")