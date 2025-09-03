import streamlit as st
import google.generativeai as genai
import time
import re
import os
import tempfile
from PyPDF2 import PdfReader
from docx import Document
import pytesseract
from PIL import Image
import json
from io import BytesIO
import base64

# ------------------------------
# Gemini API Setup
# ------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")
genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------
# Page Config
# ------------------------------
st.set_page_config(page_title="EnviroCast AI", page_icon="🌎", layout="wide")

# ------------------------------
# Dark Theme & Styling
# ------------------------------
st.markdown("""
<style>
/* Main dark background */
body, .stApp, .css-1d391kg, .css-1d391kg * {
    background-color: #1b1b2f !important;
    color: #e0e0e0 !important;
}

/* Chat bubbles */
.stChatMessage {
    background-color: #2a2a3f !important;
    color: #e0e0e0 !important;
}

/* Buttons */
.stButton button {
    background-color: #4a4a8a !important;
    color: #ffffff !important;
    border-radius: 8px !important;
}

/* Inputs */
.stTextInput input, .stSelectbox select, .stTextArea textarea {
    background-color: #2a2a3f !important;
    color: #e0e0e0 !important;
    border: 1px solid #5555aa !important;
    border-radius: 5px !important;
}

/* Sidebar & expanders */
.stSidebar, .stExpander {
    background-color: #2a2a3f !important;
    border: 1px solid #5555aa !important;
    border-radius: 6px !important;
    padding: 5px !important;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------
# Session State Initialization
# ------------------------------
def initialize_session_state():
    if 'chat_model' not in st.session_state:
        st.session_state.chat_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
                "response_mime_type": "text/plain",
            },
            system_instruction="""
Name: Enviro
Focus on pollution, air quality, environmental science. Provide structured responses, citations, and examples. Mention EnviroCast resources when relevant. Be concise, accurate, and professional.
"""
        )
    if 'chat_session' not in st.session_state:
        st.session_state.chat_session = st.session_state.chat_model.start_chat(history=[])
    if 'messages' not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Welcome to EnviroCast AI! What would you like to learn about?"}]
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
    if 'camera_image' not in st.session_state:
        st.session_state.camera_image = None
    if 'clipboard_data' not in st.session_state:
        st.session_state.clipboard_data = None
    if 'custom_commands' not in st.session_state:
        st.session_state.custom_commands = {}
    if 'tts_enabled' not in st.session_state:
        st.session_state.tts_enabled = False
    if 'high_contrast' not in st.session_state:
        st.session_state.high_contrast = False
    if 'font_family' not in st.session_state:
        st.session_state.font_family = "Montserrat"
    if 'font_size' not in st.session_state:
        st.session_state.font_size = "medium"
    if 'current_command' not in st.session_state:
        st.session_state.current_command = None

initialize_session_state()

# ------------------------------
# Helper Functions
# ------------------------------
def apply_styles():
    size_map = {"small": "0.9rem", "medium": "1rem", "large": "1.2rem", "x-large": "1.4rem"}
    font_size = size_map.get(st.session_state.font_size, "1rem")
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family={st.session_state.font_family.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
    * {{
        font-family: '{st.session_state.font_family}', sans-serif !important;
        font-size: {font_size} !important;
    }}
    </style>
    """, unsafe_allow_html=True)

def process_response(text):
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r'(\n[*-] .+?)(\n[^*\n-])', r'\1\n\2', text)
    return text.strip()

def handle_chat_response(response, message_placeholder):
    full_response = "**Enviro:** "
    formatted_response = process_response(response.text)
    chunks = []
    for line in formatted_response.split('\n'):
        chunks.extend(line.split(' '))
        chunks.append('\n')
    for chunk in chunks:
        if chunk != '\n':
            full_response += chunk + ' '
        else:
            full_response += chunk
        time.sleep(0.01)
        message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
    message_placeholder.markdown(full_response, unsafe_allow_html=True)
    
    # TTS in browser
    if st.session_state.tts_enabled:
        tts_script = f"""
        <script>
        var msg = new SpeechSynthesisUtterance("{formatted_response.replace('"', '\\"')}");
        window.speechSynthesis.speak(msg);
        </script>
        """
        st.components.v1.html(tts_script)
    
    return full_response

def extract_text_from_file(uploaded_file):
    mime_type = uploaded_file.type
    if mime_type.startswith('application/pdf'):
        reader = PdfReader(uploaded_file)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']:
        doc = Document(uploaded_file)
        return "\n".join([p.text for p in doc.paragraphs])
    elif mime_type.startswith('image/'):
        img = Image.open(uploaded_file)
        return pytesseract.image_to_string(img)
    else:
        return uploaded_file.getvalue().decode(errors='ignore')

# ------------------------------
# Sidebar Groups
# ------------------------------
with st.sidebar:
    st.header("EnviroCast Controls")

    with st.expander("Settings & Preferences", expanded=True):
        available_fonts = [
            "Montserrat", "Orbitron", "DM Sans", "Calibri", 
            "Arial", "Times New Roman", "Roboto", "Open Sans",
            "Lato", "Poppins", "Ubuntu", "Playfair Display"
        ]
        st.session_state.font_family = st.selectbox("Font Family", available_fonts, index=available_fonts.index(st.session_state.font_family))
        st.session_state.font_size = st.selectbox("Text Size", ["small", "medium", "large", "x-large"], index=["small","medium","large","x-large"].index(st.session_state.font_size))
        st.session_state.high_contrast = st.checkbox("High Contrast Mode", value=st.session_state.high_contrast)
        if st.button("Apply Settings"):
            apply_styles()

    with st.expander("File Upload", expanded=False):
        st.markdown("Upload files (PDF, DOCX, Images, TXT)")
        uploaded_files = st.file_uploader("Upload files", type=['png','jpg','jpeg','pdf','doc','docx','txt'], accept_multiple_files=True)
        if uploaded_files:
            for f in uploaded_files:
                text = extract_text_from_file(f)
                st.session_state.uploaded_files.append({"name": f.name, "content": text})
            st.success(f"{len(uploaded_files)} file(s) processed.")

    with st.expander("Camera Input", expanded=False):
        camera_image = st.camera_input("Take a picture")
        if camera_image:
            st.session_state.camera_image = camera_image
            st.image(camera_image, caption="Captured Image")

    with st.expander("Voice & TTS", expanded=False):
        st.session_state.tts_enabled = st.checkbox("Enable Text-to-Speech", value=st.session_state.tts_enabled)

    with st.expander("Custom Commands", expanded=False):
        st.text_input("New Command Name", key="new_command_name")
        st.text_area("New Command Prompt", key="new_command_prompt")
        if st.button("Save Command"):
            name = st.session_state.new_command_name.strip()
            prompt = st.session_state.new_command_prompt.strip()
            if name and prompt:
                st.session_state.custom_commands[name] = prompt
                st.success(f"Saved command: {name}")

# ------------------------------
# Main Chat
# ------------------------------
apply_styles()
st.title("🌎 EnviroCast AI")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

prompt = st.chat_input("Ask a question about pollution or the environment...")
if prompt:
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("assistant") as placeholder:
        try:
            # Combine prompt with uploaded files or camera info
            input_parts = [prompt]
            if st.session_state.uploaded_files:
                input_parts.extend([f['content'] for f in st.session_state.uploaded_files])
            if st.session_state.camera_image:
                input_parts.append("Image provided for analysis.")
            
            response = st.session_state.chat_session.send_message(input_parts)
            handle_chat_response(response, placeholder)
        except Exception as e:
            st.error(f"Error: {e}")
