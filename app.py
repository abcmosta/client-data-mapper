import streamlit as st

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Alex AI | Gateway", page_icon="⚡", layout="centered")

# --- HIDE SIDEBAR ON LOGIN PAGE ---
st.markdown("""
    <style>
        [data-testid="collapsedControl"] {display: none;}
        [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE (Memory) ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_name' not in st.session_state:
    st.session_state.user_name = ""
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""

# --- UI: LOGIN GATE ---
if not st.session_state.authenticated:
    
    _, col2, _ = st.columns([1, 2, 1])
    
    with col2:
        st.title("⚡ Welcome to Alex")
        st.markdown("I am your AI Catalogue Assistant. Please sign in with the Company Master Key to proceed.")
        st.write("---")
        
        with st.form("login_form"):
            user_name = st.text_input("What would you like me to call you?", placeholder="e.g., Mostafa")
            user_email = st.text_input("Work Email", placeholder="name@talabat.com")
            password = st.text_input("Master Key", type="password", placeholder="Enter the company password")
            
            submitted = st.form_submit_button("Unlock Alex", use_container_width=True, type="primary")
            
            if submitted:
                if not user_name or not user_email:
                    st.warning("Please tell me your name and email so we can proceed!")
                elif password != st.secrets["MASTER_PASSWORD"]:
                    st.error("Incorrect Master Key. Please try again.")
                else:
                    # Success!
                    st.session_state.user_name = user_name
                    st.session_state.user_email = user_email
                    st.session_state.authenticated = True
                    st.rerun()

# --- UI: LOGGED IN STATE ---
else:
    st.title(f"🎉 Welcome aboard, {st.session_state.user_name.title()}!")
    st.markdown("Your identity is verified. Alex is booted up and waiting for your messy client files.")
    st.divider()
    
    if st.button("🚀 Take me to Alex", type="primary", use_container_width=True):
        st.switch_page("pages/1_🤖_Alex_Wizard.py")
        
    st.write("---")
    if st.button("Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_name = ""
        st.session_state.user_email = ""
        st.rerun()