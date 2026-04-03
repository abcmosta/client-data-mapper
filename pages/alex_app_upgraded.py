import streamlit as st
import pandas as pd
from openai import OpenAI
import json
import re
import io
from deep_translator import GoogleTranslator

# ─────────────────────────────────────────────────────────────────────────────
# Import the Smart Title Formatter (place smart_title_formatter.py
# in the same folder as this app file)
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

    st.divider()
    st.header("🧠 Title Engine v2.0")
    st.caption(
        "Trained on 19,000+ real Talabat titles across 7 product types. "
        "Handles weight (g/kg/mg), volume (ml/l/fl oz), "
        "multi-packs (6x90ml), dimensions (31x12x41cm), "
        "count (Tablets/Capsules/Pieces), ALL-CAPS brands, "
        "special tokens (SPF50+, pH, AHA, MK-7, USB-C…) "
        "and 28 canonical units."
    )

# ─────────────────────────────────────────────────────────────────────────────
# MAIN HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.title("🤖 Alex, The Invincible  v2.0")
display_name = st.session_state.get('user_name', 'There').title()
st.markdown(f"""
Hello **{display_name}** ❤️, I am **Alex**.  
An AI Assistant Created By **Mostafa Abdelaziz**.  
Now with a **Smart Title Engine** trained on 19,000+ real catalogue titles ✨
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
# ACCEPTABLE UNITS (for validation)
# ─────────────────────────────────────────────────────────────────────────────
acceptable_units = [
    "bags", "bouquets - Flowers", "boxes", "bunches", "capsules",
    "cl", "cm", "cm2", "cm3", "dl", "g", "kg", "l", "lb", "m",
    "mg", "ml", "oz", "packets", "pieces", "rolls", "sachets",
    "sheets", "tablets", "units",
]

# ─────────────────────────────────────────────────────────────────────────────
# TARGET SCHEMA
# ─────────────────────────────────────────────────────────────────────────────
target_schema = [
    "pieceBarcode", "brandName", "productTitle::en",
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
You are Alex, an elite Data Engineer.
Map the client headers to our 'Target Schema': {target_schema}.

Client Headers: {headers}
Data Sample: {sample}

STRICT RULES & TIE-BREAKERS:
1. 'pieceBarcode': Priority is EAN > GTIN > UPC > Barcode > Item Code > PLU.
   (Look for 12 to 14 digit global numbers).
2. 'productTitle::en': Choose the MOST descriptive English header.
   Priority: Long Description > Title > Name.
3. 'contentsValue': Look for Size, Weight, Volume, Net Weight, or Qty.
   🚨 CRITICAL RULE: NEVER map Price, Cost, MSRP, or RRP to contentsValue.
4. 'contentsUnit': Look for UOM, Unit, Measurement.
   🚨 CRITICAL RULE: NEVER map currency symbols ($, AED, EGP, SAR) to contentsUnit.
5. 'imageUrls': Look for Link, URL, Photo, Media.
6. 'brandName': Look for Vendor, Manufacturer, Make, Brand.

Return ONLY a JSON object: {{"Target_Field": "Client_Header"}}.
If no valid match exists for a field, omit it entirely.
"""
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "You output strict JSON."},
                            {"role": "user",   "content": mapping_prompt},
                        ],
                        response_format={"type": "json_object"},
                    )
                    st.session_state.ai_mapping = json.loads(
                        response.choices[0].message.content
                    )

        # ─── STEP 2: MANUAL OVERRIDE ───────────────────────────────────────
        if st.session_state.ai_mapping is not None:
            with st.expander("🛠️ Step 2: Review & Override Alex's Mapping", expanded=True):
                with st.form("manual_mapping_form"):
                    final_mapping = {}
                    options = ["--- Leave Blank ---"] + headers
                    for target_col in target_schema:
                        ai_suggested = st.session_state.ai_mapping.get(target_col)
                        default_idx  = (
                            options.index(ai_suggested)
                            if ai_suggested in options else 0
                        )
                        final_mapping[target_col] = st.selectbox(
                            f"Map '{target_col}' to:",
                            options=options,
                            index=default_idx,
                        )
                    submitted = st.form_submit_button(
                        "🚀 Step 3: Run Master Cleanse & Translate", type="primary"
                    )

            # ─── STEP 3: DEEP HYGIENE + SMART TITLE FORMAT + TRANSLATION ──
            if submitted:
                with st.spinner(
                    "🧠 Smart Title Engine running… translating… building Excel Masterpiece…"
                ):
                    active_mapping = {
                        k: v for k, v in final_mapping.items()
                        if v != "--- Leave Blank ---"
                    }

                    # Build raw cleaned dataframe
                    cleaned_df = pd.DataFrame()
                    for internal_name in target_schema:
                        if (
                            internal_name in active_mapping
                            and active_mapping[internal_name] in df.columns
                        ):
                            cleaned_df[internal_name] = df[active_mapping[internal_name]]
                        else:
                            cleaned_df[internal_name] = ""

                    cleaned_df['productTitle::ar'] = ""
                    cleaned_df['_title_confidence'] = ""
                    cleaned_df['_title_changes']    = ""

                    translator_ar = GoogleTranslator(source='auto', target='ar')

                    feedback_notes = []

                    for index, row in cleaned_df.iterrows():
                        doubts = []

                        # ── 1. Barcode Armor & Padding ────────────────────
                        raw_barcode = (
                            str(row.get('pieceBarcode', ''))
                            .replace('.0', '').strip()
                        )
                        if raw_barcode in ['', 'nan', 'none']:
                            doubts.append("Missing Barcode")
                            cleaned_df.at[index, 'pieceBarcode'] = ""
                        else:
                            clean_barcode = raw_barcode.zfill(13)
                            cleaned_df.at[index, 'pieceBarcode'] = f"'{clean_barcode}"

                        # ── 2. SMART TITLE FORMATTING (v2.0 Engine) ───────
                        raw_title    = str(row.get('productTitle::en', '')).replace('nan', '').strip()
                        brand_raw    = str(row.get('brandName', '')).replace('nan', '').strip()
                        cv_raw       = str(row.get('contentsValue', '')).replace('nan', '').strip()
                        cu_raw       = str(row.get('contentsUnit', '')).replace('nan', '').strip()

                        title_result = smart_format_title(
                            raw_title=raw_title,
                            brand_name=brand_raw,
                            contents_value=cv_raw,
                            contents_unit=cu_raw,
                        )

                        formatted_title = title_result['formatted_title']
                        confidence      = title_result['confidence']
                        title_issues    = title_result['issues']

                        # Record what changed
                        change_note = ""
                        if formatted_title != raw_title and raw_title:
                            change_note = f"{raw_title} → {formatted_title}"

                        cleaned_df.at[index, 'productTitle::en'] = formatted_title
                        cleaned_df.at[index, '_title_confidence'] = confidence
                        cleaned_df.at[index, '_title_changes']    = change_note

                        # Flag low-confidence titles for human review
                        if confidence == 'low':
                            doubts.append("⚠ Title needs review")
                        if title_issues:
                            for iss in title_issues:
                                if "mismatch" in iss.lower():
                                    doubts.append(f"Title: {iss[:60]}")

                        # ── 3. Arabic Translation ─────────────────────────
                        if formatted_title:
                            try:
                                cleaned_df.at[index, 'productTitle::ar'] = (
                                    translator_ar.translate(formatted_title)
                                )
                            except Exception:
                                cleaned_df.at[index, 'productTitle::ar'] = "Translation Failed"

                        # ── 4. Smart Size Extraction (fallback if still empty)
                        val_missing = (
                            not cv_raw or cv_raw in ('', 'nan', '0', '0.0')
                        )
                        unit_missing = not cu_raw or cu_raw in ('', 'nan')

                        if val_missing or unit_missing:
                            unit_regex = '|'.join(
                                [u.lower() for u in acceptable_units]
                            )
                            match = re.search(
                                r'(?i)(\d+(?:\.\d+)?)\s*(' + unit_regex + r')\b',
                                formatted_title
                            )
                            if match:
                                if val_missing:
                                    cleaned_df.at[index, 'contentsValue'] = match.group(1)
                                    val_missing = False
                                if unit_missing:
                                    cleaned_df.at[index, 'contentsUnit'] = match.group(2).lower()
                                    unit_missing = False

                        if val_missing:
                            doubts.append("Missing Qty")

                        unit_val = str(cleaned_df.at[index, 'contentsUnit']).strip().lower()
                        if unit_val not in [u.lower() for u in acceptable_units] and unit_val not in ['', 'nan']:
                            doubts.append(f"Invalid Unit '{unit_val}'")
                        elif unit_val in ['', 'nan']:
                            doubts.append("Missing Unit")

                        # ── 5. URL Sanity Check ───────────────────────────
                        raw_url = str(row.get('imageUrls', '')).strip().lower()
                        if raw_url in ['', 'nan', 'n/a', 'none']:
                            doubts.append("Missing Image")
                        elif not raw_url.startswith('http'):
                            doubts.append("Invalid Image URL Format")

                        if not doubts:
                            feedback_notes.append("✅ Ready for Catalogue")
                        else:
                            feedback_notes.append("⚠️ " + ", ".join(doubts))

                    cleaned_df['Catalogue_Feedback'] = feedback_notes

                    # ── EXCEL MASTERPIECE BUILDER ─────────────────────────
                    st.success("✅ Master Cleanse, Smart Formatting & Translations Complete!")

                    ready_df   = cleaned_df[cleaned_df['Catalogue_Feedback'] == "✅ Ready for Catalogue"]
                    error_df   = cleaned_df[cleaned_df['Catalogue_Feedback'].str.contains("⚠️")]
                    changed_df = cleaned_df[cleaned_df['_title_changes'] != ""].copy()

                    total_rows   = len(cleaned_df)
                    clean_rows   = len(ready_df)
                    flagged_rows = len(error_df)
                    changed_rows = len(changed_df)
                    success_rate = f"{(clean_rows/total_rows)*100:.1f}%" if total_rows > 0 else "0%"

                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("✅ Ready for Catalogue", clean_rows)
                    col2.metric("⚠️ Needing Attention",   flagged_rows)
                    col3.metric("✏️ Titles Corrected",    changed_rows)
                    col4.metric("📊 Quality Score",        success_rate)
                    st.write("---")

                    # Confidence breakdown
                    conf_counts = cleaned_df['_title_confidence'].value_counts()
                    with st.expander("🔍 Title Confidence Breakdown"):
                        st.write(f"**High confidence:** {conf_counts.get('high', 0)} titles")
                        st.write(f"**Medium confidence:** {conf_counts.get('medium', 0)} titles")
                        st.write(f"**Low confidence:** {conf_counts.get('low', 0)} titles (review recommended)")

                    summary_data = {
                        "Case ID":           [case_id],
                        "Client Name":       [client_name],
                        "Country":           [country],
                        "Total Processed":   [total_rows],
                        "Perfect Rows":      [clean_rows],
                        "Rows Needing Fixes":[flagged_rows],
                        "Titles Corrected":  [changed_rows],
                        "Quality Score":     [success_rate],
                    }
                    summary_df = pd.DataFrame(summary_data)

                    # Columns for export (hide internal debug columns)
                    export_cols = [
                        c for c in cleaned_df.columns
                        if not c.startswith('_')
                    ] + ['Catalogue_Feedback']
                    export_ready = ready_df[[c for c in export_cols if c in ready_df.columns]]
                    export_error = error_df[[c for c in export_cols if c in error_df.columns]]

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        summary_df.to_excel(writer, index=False, sheet_name="📊 Summary")
                        export_ready.to_excel(writer, index=False, sheet_name="✅ Ready to Import")
                        if flagged_rows > 0:
                            export_error.to_excel(writer, index=False, sheet_name="⚠️ Action Required")
                        if changed_rows > 0:
                            changed_df[['productTitle::en', '_title_changes', '_title_confidence', 'Catalogue_Feedback']].to_excel(
                                writer, index=False, sheet_name="✏️ Title Changes Log"
                            )
                    excel_data = output.getvalue()

                    output_filename = (
                        f"{case_id} - {client_name} - {country}_Content_Wizard_v2.xlsx"
                    )

                    st.download_button(
                        label=f"📥 Download Enterprise Excel Report ({output_filename})",
                        data=excel_data,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True,
                    )

                    tab1, tab2, tab3 = st.tabs([
                        "✅ Ready to Import",
                        "⚠️ Action Required",
                        "✏️ Title Changes",
                    ])
                    with tab1:
                        st.dataframe(export_ready, use_container_width=True)
                    with tab2:
                        if flagged_rows > 0:
                            st.dataframe(export_error, use_container_width=True)
                        else:
                            st.success("No errors! Perfect file.")
                    with tab3:
                        if changed_rows > 0:
                            st.dataframe(
                                changed_df[['productTitle::en', '_title_changes', '_title_confidence']],
                                use_container_width=True,
                            )
                        else:
                            st.info("No titles were changed — vendor file was already well formatted.")

    except Exception as e:
        st.error(f"An error occurred: {e}")