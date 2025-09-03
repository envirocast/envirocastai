import streamlit as st
import google.generativeai as genai
import time
import re
import os
import mimetypes
import tempfile
import speech_recognition as sr
import hashlib
from PyPDF2 import PdfReader
from docx import Document
import pytesseract
from PIL import Image
import pandas as pd
import json
import xml.etree.ElementTree as ET
from io import BytesIO
import base64
from datetime import datetime, timedelta
import pyttsx3  # For TTS

# ------------------------------
# Utility functions
# ------------------------------
def initialize_font_preferences():
    if 'font_preferences' not in st.session_state:
        st.session_state.font_preferences = {"font_family": "Montserrat", "text_size": "medium"}

def save_font_preferences():
    prefs_json = json.dumps(st.session_state.font_preferences)
    st.markdown(
        f"<script>localStorage.setItem('enviro_font', '{prefs_json}');</script>", unsafe_allow_html=True
    )

def apply_font_preferences():
    font_family = st.session_state.font_preferences.get("font_family", "Montserrat")
    text_size = st.session_state.font_preferences.get("text_size", "medium")
    size_map = {"small": "0.9rem", "medium": "1rem", "large": "1.2rem", "x-large": "1.4rem"}
    font_size = size_map[text_size]
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family={font_family.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
        * {{ font-family: '{font_family}', sans-serif !important; font-size: {font_size} !important; }}
        .stMarkdown, .stText, .stTitle, .stHeader {{ font-family: '{font_family}', sans-serif !important; }}
        .stButton button {{ font-family: '{font_family}', sans-serif !important; }}
        .stTextInput input {{ font-family: '{font_family}', sans-serif !important; }}
        .stSelectbox select {{ font-family: '{font_family}', sans-serif !important; }}
        h1 {{ font-size: calc({font_size} * 2.0) !important; }}
        h2 {{ font-size: calc({font_size} * 1.5) !important; }}
        h3 {{ font-size: calc({font_size} * 1.3) !important; }}
    </style>""", unsafe_allow_html=True)

def initialize_custom_commands():
    if 'custom_commands' not in st.session_state:
        st.session_state.custom_commands = {}

def save_custom_commands():
    cmds_json = json.dumps(st.session_state.custom_commands)
    st.markdown(f"<script>localStorage.setItem('enviro_custom_commands', '{cmds_json}');</script>", unsafe_allow_html=True)

# ------------------------------
# Gemini API Setup
# ------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")
genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------
# Page Configuration
# ------------------------------
st.set_page_config(page_title="Meet Enviro", page_icon="./favicon.ico", layout="wide")

# ------------------------------
# CSS & Clipboard
# ------------------------------
st.markdown("""
<style>
    .stChatInputContainer { display: flex; align-items: center; }
</style>
<script>
document.addEventListener('paste', function(e) {
    if (document.activeElement.tagName !== 'TEXTAREA' && document.activeElement.tagName !== 'INPUT') {
        e.preventDefault();
        const items = e.clipboardData.items;
        for (const item of items) {
            if (item.type.indexOf('image') !== -1) {
                const blob = item.getAsFile();
                const reader = new FileReader();
                reader.onload = function(e) {
                    const base64data = e.target.result;
                    window.parent.postMessage({ type: 'clipboard_paste', data: base64data, format: 'image' }, '*');
                };
                reader.readAsDataURL(blob);
            } else if (item.type === 'text/plain') {
                item.getAsString(function(text) {
                    window.parent.postMessage({ type: 'clipboard_paste', data: text, format: 'text' }, '*');
                });
            }
        }
    }
});
window.addEventListener('message', function(e) {
    if (e.data.type === 'clipboard_paste') {
        window.parent.postMessage({ type: 'streamlit:set_widget_value', key: 'clipboard_data', value: {data: e.data.data, format: e.data.format} }, '*');
    }
});
</script>
""", unsafe_allow_html=True)

# ------------------------------
# Gemini Generation Config
# ------------------------------
generation_config = {
    "temperature": 0,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

SYSTEM_INSTRUCTION = """
Name: Enviro
Focus on pollution, air quality, environmental science. Provide structured responses, citations, and examples. Mention EnviroCast resources when relevant. Be concise, accurate, and professional.
"""

# ------------------------------
# Session State Initialization
# ------------------------------
def initialize_session_state():
    if 'chat_model' not in st.session_state:
        st.session_state.chat_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION,
        )
    if 'chat_session' not in st.session_state:
        st.session_state.chat_session = st.session_state.chat_model.start_chat(history=[])
    if 'messages' not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Welcome to EnviroCast AI! What would you like to learn about?"}]
    if 'uploaded_files' not in st.session_state: st.session_state.uploaded_files = []
    if 'camera_image' not in st.session_state: st.session_state.camera_image = None
    if 'clipboard_data' not in st.session_state: st.session_state.clipboard_data = None
    if 'show_custom_cmd_form' not in st.session_state: st.session_state.show_custom_cmd_form = False
    if 'tts_enabled' not in st.session_state: st.session_state.tts_enabled = False
    initialize_custom_commands()
    initialize_font_preferences()

# ------------------------------
# Helper Functions
# ------------------------------
def process_response(text):
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r'(\n[*-] .+?)(\n[^*\n-])', r'\1\n\2', text)
    return text.strip()

def handle_chat_response(response, message_placeholder, command_message=""):
    full_response = f"**Enviro:** " + command_message + "\n\n" if command_message else "**Enviro:** "
    formatted_response = process_response(response.text)
    chunks = []
    for line in formatted_response.split('\n'):
        chunks.extend(line.split(' '))
        chunks.append('\n')
    for chunk in chunks:
        if chunk != '\n': full_response += chunk + ' '
        else: full_response += chunk
        time.sleep(0.01)
        message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
    message_placeholder.markdown(full_response, unsafe_allow_html=True)
    
    # Text-to-Speech
    if st.session_state.tts_enabled:
        engine = pyttsx3.init()
        engine.say(formatted_response)
        engine.runAndWait()
    
    return full_response

# ------------------------------
# Main App
# ------------------------------
def main():
    initialize_session_state()
    apply_font_preferences()

    st.title("🌎 EnviroCast AI")
    
    # Sidebar for all features
    with st.sidebar:
        st.header("Settings & Features")
        st.checkbox("Enable Camera", key="camera_enabled")
        st.checkbox("Enable TTS Audio Replies", key="tts_enabled")
        
        st.subheader("Font Settings")
        st.selectbox("Font", ["Montserrat", "Roboto", "Arial", "Times New Roman"], key="font_preferences")
        st.selectbox("Text Size", ["small", "medium", "large", "x-large"], key="font_preferences_size")
        
        st.subheader("Custom Commands")
        st.text_input("Command Name", key="new_command_name")
        st.text_area("Command Prompt", key="new_command_prompt")
        if st.button("Save Custom Command"):
            name = st.session_state.new_command_name.strip()
            prompt = st.session_state.new_command_prompt.strip()
            if name and prompt:
                st.session_state.custom_commands[name] = {"prompt": prompt}
                save_custom_commands()
                st.success(f"Custom command '{name}' saved!")
        
        st.markdown("---")
        st.subheader("Chat History")
        if st.button("Download Chat History"):
            history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])
            b64 = base64.b64encode(history_str.encode()).decode()
            href = f'<a href="data:file/text;base64,{b64}" download="enviro_chat.txt">Download Chat History</a>'
            st.markdown(href, unsafe_allow_html=True)

    # Display chat messages in main area
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    # Chat input
    prompt = st.chat_input("What would you like to learn about?")
    if prompt:
        input_parts = [prompt]
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            try:
                response = st.session_state.chat_session.send_message(input_parts)
                full_response = handle_chat_response(response, message_placeholder)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            except Exception as e:
                st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
