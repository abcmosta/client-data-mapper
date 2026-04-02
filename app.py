import streamlit as st
from supabase import create_client, Client

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Alex AI | Gateway", page_icon="⚡", layout="centered")

# --- HIDE SIDEBAR ON LOGIN PAGE ---
# This CSS hides the ugly default sidebar so it looks like a real landing page
st.markdown("""
    <style>
        [data-testid="collapsedControl"] {display: none;}
        [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

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
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'otp_sent' not in st.session_state:
    st.session_state.otp_sent = False
if 'login_email' not in st.session_state:
    st.session_state.login_email = ""

# --- UI: LOGIN GATE ---
if st.session_state.user is None:
    
    # Center the content using columns
    _, col2, _ = st.columns([1, 2, 1])
    
    with col2:
        st.title("⚡ Welcome to Alex")
        st.markdown("I am your AI Catalogue Assistant. Let's get to know each other before we start crunching data.")
        st.write("---")
        
        # STATE 1: Ask for Name and Email
        if not st.session_state.otp_sent:
            user_name = st.text_input("What would you like me to call you?", placeholder="e.g., Mostafa")
            email = st.text_input("Work Email", placeholder="name@talabat.com")
            
            st.write("") # Spacer
            if st.button("Send Verification Code", use_container_width=True):
                if user_name and email:
                    with st.spinner("Dispatching secure code to your inbox..."):
                        try:
                            supabase.auth.sign_in_with_otp({"email": email})
                            # Save their details to memory
                            st.session_state.user_name = user_name
                            st.session_state.login_email = email
                            st.session_state.otp_sent = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error communicating with database: {e}")
                else:
                    st.warning("Please tell me your name and email so we can proceed!")
                    
        # STATE 2: Enter the Code
        else:
            st.success(f"Code dispatched to **{st.session_state.login_email}**")
            otp = st.text_input("Enter the 6-Digit Code", max_chars=6)
            
            st.write("") # Spacer
            if st.button("Unlock Alex", type="primary", use_container_width=True):
                if otp:
                    with st.spinner("Verifying identity..."):
                        try:
                            res = supabase.auth.verify_otp({"email": st.session_state.login_email, "token": otp, "type": "email"})
                            st.session_state.user = res.user
                            st.success("Access Granted!")
                            st.rerun()
                        except Exception as e:
                            st.error("Invalid or expired code. Please try again.")

# --- UI: LOGGED IN STATE ---
else:
    # Fallback just in case they refresh the page and the name clears from memory
    display_name = st.session_state.user_name if st.session_state.user_name else st.session_state.user.email.split('@')[0].title()
    
    st.title(f"🎉 Welcome aboard, {display_name}!")
    st.markdown("Your identity is verified. Alex is booted up and waiting for your messy client files.")
    st.divider()
    
    # THE SEAMLESS ROUTING BUTTON
    # This magically teleports them to the hidden wizard page
    if st.button("🚀 Take me to Alex", type="primary", use_container_width=True):
        st.switch_page("pages/1_🤖_Alex_Wizard.py")
        
    st.write("---")
    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.otp_sent = False
        st.rerun()