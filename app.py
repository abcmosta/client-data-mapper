import streamlit as st
from supabase import create_client, Client

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Alex AI - Login", page_icon="🔐", layout="centered")

# --- INITIALIZE SUPABASE ---
@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["URL"]
    key = st.secrets["supabase"]["KEY"]
    return create_client(url, key)

supabase = init_connection()

# --- SESSION STATE (Memory) ---
if 'user' not in st.session_state:
    st.session_state.user = None

# --- UI: LOGIN GATE ---
st.title("🔐 Welcome to Alex AI")
st.markdown("Please verify your identity to access the Enterprise Catalogue Wizard.")
st.divider()

if st.session_state.user is None:
    # 1. Email Input Form
    email = st.text_input("Enter your Work Email", placeholder="name@talabat.com")
    
    if st.button("Send Verification Code"):
        if email:
            with st.spinner("Dispatching secure code..."):
                try:
                    supabase.auth.sign_in_with_otp({"email": email})
                    st.success("Verification code sent! Please check your inbox.")
                except Exception as e:
                    st.error(f"Error communicating with database: {e}")
        else:
            st.error("Please enter an email address.")
            
    st.write("---")
    
    # 2. OTP Verification Form
    otp = st.text_input("Enter the 8-Digit Code", max_chars=8)
    
    if st.button("Unlock Alex AI", type="primary"):
        if email and otp:
            with st.spinner("Verifying..."):
                try:
                    # Check the code against Supabase
                    res = supabase.auth.verify_otp({"email": email, "token": otp, "type": "email"})
                    st.session_state.user = res.user
                    st.success("Access Granted! The app is unlocking...")
                    st.rerun() # Refreshes the app to show logged-in state
                except Exception as e:
                    st.error("Invalid or expired code. Please try again.")
else:
    # 3. Logged In State
    st.success(f"✅ Logged in securely as: **{st.session_state.user.email}**")
    st.info("👈 **Access Granted:** Please select the **Alex Wizard** from the sidebar menu to begin working.")
    
    if st.button("Log Out"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()