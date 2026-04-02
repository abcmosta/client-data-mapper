import streamlit as st
import pandas as pd
from openai import OpenAI
import json

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
uploaded_file = st.file_uploader("Upload Client Spreadsheet (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file:
    # 1. Read the file
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.write("### 📄 Original Client Data Preview")
        st.dataframe(df.head())
        
        # 2. Extract the "DNA" (Headers and a tiny sample)
        headers = df.columns.tolist()
        sample = df.head(2).to_dict(orient='records')
        
        # Define what YOUR company needs
        target_schema = ["Product_Name", "SKU_Number", "Unit_Price", "Brand_Vendor"]
        
        st.write("---")
        st.write(f"**Target Schema:** `{target_schema}`")
        
        # 3. The Mapping Button
        if st.button("🧠 Auto-Map Columns"):
            with st.spinner("AI is analyzing headers and sample data..."):
                
                # The Prompt
                mapping_prompt = f"""
                You are a data engineer mapping client files to our internal schema.
                Target Schema: {target_schema}
                Client Headers: {headers}
                Client Data Sample: {sample}
                
                Match the client headers to our Target Schema based on the names and sample data context.
                Return ONLY a raw JSON object where the key is the Target Schema field and the value is the Client Header.
                Example: {{"Product_Name": "Item Title", "SKU_Number": "UPC"}}
                """
                
                # Call the AI
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You output strict JSON. No markdown, no explanations."},
                        {"role": "user", "content": mapping_prompt}
                    ],
                    response_format={ "type": "json_object" }
                )
                
                # 4. Parse the AI's JSON Map
                mapping_dict = json.loads(response.choices[0].message.content)
                
                st.success("Mapping Complete!")
                st.write("**AI Generated Map:**", mapping_dict)
                
                # 5. Transform and Clean the bulk data
                cleaned_df = pd.DataFrame()
                audit_trail = [] # List to track our changes
                
                for internal_name, client_name in mapping_dict.items():
                    if client_name in df.columns:
                        # Grab the raw data
                        raw_data = df[client_name].astype(str)
                        
                        # CLEANING RULE: Strip extra spaces and fix capitalization (Title Case)
                        clean_data = raw_data.str.strip().str.title()
                        
                        cleaned_df[internal_name] = clean_data
                        
                        # AUDIT TRAIL LOGIC: Compare raw vs clean row by row
                        for i in range(len(raw_data)):
                            if raw_data.iloc[i] != clean_data.iloc[i]:
                                audit_trail.append({
                                    "Row": i + 1,
                                    "Column": internal_name,
                                    "Original": raw_data.iloc[i],
                                    "Cleaned": clean_data.iloc[i],
                                    "Action": "Standardized Text Formatting"
                                })
                    else:
                        cleaned_df[internal_name] = "Not Found"
                        
                st.write("### ✨ Processed Output")
                st.dataframe(cleaned_df)
                
                # --- NEW: Display the Audit Trail ---
                if audit_trail:
                    st.write("### 🔍 'What Changed' Audit Log")
                    audit_df = pd.DataFrame(audit_trail)
                    st.dataframe(audit_df)
                else:
                    st.success("Data was already perfectly clean! No changes made.")
                
                
                # 6. Allow Download
                csv = cleaned_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Cleaned Data (CSV)",
                    data=csv,
                    file_name="cleaned_client_data.csv",
                    mime="text/csv",
                )
                
    except Exception as e:
        st.error(f"An error occurred: {e}")