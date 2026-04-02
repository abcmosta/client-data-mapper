import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re

# --- SETUP THE AI BRAIN ---
# Using GitHub Models (GPT-4o-mini)
# --- SETUP THE AI BRAIN ---
# Securely fetching the key from Streamlit Secrets
github_token = st.secrets["GITHUB_TOKEN"]

client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=github_token 
)
# --- UI SETTINGS ---
st.set_page_config(page_title="Hitler", layout="wide")
st.title("Hello, I am Hitler🥸")
st.write("I am not a cruel person as people may think!🥹 Today, I am just your AI assistant. " \
"I am here to help you do the job more effiently, Upload any messy client spreadsheet, and the I will format it to talabat's standard schema.")

# --- THE APP LOGIC ---
uploaded_file = st.file_uploader("Upload Client Spreadsheet", type=["csv", "xlsx"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.write("### 📄 Original Client Data Preview")
        st.dataframe(df.head())
        
        headers = df.columns.tolist()
        sample = df.head(3).to_dict(orient='records')
        
        # --- NEW: Strict Business Rules ---
        target_schema = [
            "pieceBarcode", "brandName", "productTitle::en", 
            "imageUrls", "contentsValue", "contentsUnit"
        ]
        
        acceptable_units = [
            "bags", "bouquets - Flowers", "boxes", "bunches", "capsules",
            "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m", 
            "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets", 
            "sheets", "tablets", "units"
        ]
        
        if st.button("🧠 Map & Validate for Catalogue"):
            with st.spinner("AI is analyzing and validating data..."):
                
                # 1. AI Mapping Prompt
                mapping_prompt = f"""
                Map the client headers to this exact case-sensitive schema: {target_schema}.
                Client Headers: {headers}
                Sample Data: {sample}
                
                Rules:
                - Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}
                - If the client doesn't have a field (like brandName), do not include it in the JSON.
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
                
                # 2. Build the Cleaned DataFrame
                cleaned_df = pd.DataFrame()
                
                for internal_name in target_schema:
                    client_name = mapping_dict.get(internal_name)
                    if client_name and client_name in df.columns:
                        cleaned_df[internal_name] = df[client_name]
                    else:
                        cleaned_df[internal_name] = "" # Leave blank if missing so the AI Feedback catches it
                
                # 3. Formatting Rules & SMART EXTRACTION
                if "productTitle::en" in cleaned_df.columns:
                    # Clean up the title formatting first
                    cleaned_df["productTitle::en"] = cleaned_df["productTitle::en"].astype(str).str.title().replace('Nan', '')
                    
                    # Build a "Detective Pattern" based on your acceptable units
                    # This tells Python to look for a number, optional decimals, a space, and a valid unit (e.g. "500 g" or "1.5 l")
                    unit_regex = '|'.join([u.lower() for u in acceptable_units])
                    pattern = r'(?i)(\d+(?:\.\d+)?)\s*(' + unit_regex + r')\b'
                    
                    # Scan every row to fill in missing blanks
                    for index, row in cleaned_df.iterrows():
                        title = str(row['productTitle::en'])
                        
                        val_missing = pd.isna(row.get('contentsValue')) or str(row.get('contentsValue')).strip() in ['', 'nan']
                        unit_missing = pd.isna(row.get('contentsUnit')) or str(row.get('contentsUnit')).strip() in ['', 'nan']
                        
                        # If the client forgot the quantity or unit, search the title for it
                        if val_missing or unit_missing:
                            match = re.search(pattern, title)
                            
                            if match: # If Python finds "125 G" in the title
                                extracted_qty = match.group(1)
                                extracted_unit = match.group(2).lower() # standardizes to lowercase
                                
                                if val_missing:
                                    cleaned_df.at[index, 'contentsValue'] = extracted_qty
                                if unit_missing:
                                    cleaned_df.at[index, 'contentsUnit'] = extracted_unit
                                    
                # 4. Catalogue Specialist AI Feedback Engine (The "Doubts")
                feedback_notes = []
                
                # We check every single row against your strict rules
                for index, row in cleaned_df.iterrows():
                    doubts = []
                    
                    # Check Barcode
                    if pd.isna(row.get('pieceBarcode')) or str(row.get('pieceBarcode')).strip() in ['', 'nan']:
                        doubts.append("Missing Barcode")
                        
                    # --- BRAND CHECK REMOVED ---
                    # We no longer penalize or flag missing brands, as this requires 
                    # specialist domain knowledge to extract from the title.
                        
                    # Check Quantity
                    if pd.isna(row.get('contentsValue')) or str(row.get('contentsValue')).strip() in ['', 'nan']:
                        doubts.append("Missing Quantity")
                        
                    # Strict Unit Validation
                    unit = str(row.get('contentsUnit')).strip().lower()
                    if unit not in [u.lower() for u in acceptable_units] and unit not in ['', 'nan']:
                        doubts.append(f"Invalid Unit '{unit}'")
                    elif unit in ['', 'nan']:
                        doubts.append("Missing Unit")
                        
                    # Check Image
                    if pd.isna(row.get('imageUrls')) or str(row.get('imageUrls')).strip() in ['', 'nan']:
                        doubts.append("Missing Image")
                        
                    # Apply final status
                    if not doubts:
                        feedback_notes.append("✅ Ready for Catalogue")
                    else:
                        feedback_notes.append("⚠️ " + ", ".join(doubts))
                        
                cleaned_df['Catalogue_Feedback'] = feedback_notes
                
                # 5. Display & Download
                st.success("Mapping & Validation Complete!")
                
                st.write("### 📋 Final Catalogue File")
                st.dataframe(cleaned_df)
                
                csv = cleaned_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download Processed Catalogue (CSV)", data=csv, file_name="catalogue_ready.csv", mime="text/csv")
                
    except Exception as e:
        st.error(f"An error occurred: {e}")