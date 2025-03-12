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

# Check for password in session state and persistent login

def initialize_font_preferences():
    if 'font_preferences' not in st.session_state:
        # Try to load from local storage
        placeholder_div = st.empty()
        placeholder_div.markdown(
            """
            <div id="load_font_preferences" style="display:none;"></div>
            <script>
                const prefDiv = document.getElementById('load_font_preferences');
                const savedPrefs = localStorage.getItem('onco_aide_font');
                if (savedPrefs) {
                    prefDiv.innerText = savedPrefs;
                } else {
                    prefDiv.innerText = JSON.stringify({
                        font_family: "Montserrat",
                        text_size: "medium"
                    });
                }
                setTimeout(() => {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: prefDiv.innerText,
                        dataType: 'string',
                        key: 'loaded_font_preferences'
                    }, '*');
                }, 100);
            </script>
            """,
            unsafe_allow_html=True
        )
        
        # Wait for the JavaScript to set the value
        if 'loaded_font_preferences' in st.session_state:
            placeholder_div.empty()
            try:
                st.session_state.font_preferences = json.loads(st.session_state.loaded_font_preferences)
            except:
                # Default preferences if loading fails
                st.session_state.font_preferences = {
                    "font_family": "Montserrat",
                    "text_size": "medium"
                }
        else:
            # Default preferences
            st.session_state.font_preferences = {
                "font_family": "Montserrat",
                "text_size": "medium"
            }

def save_font_preferences():
    prefs_json = json.dumps(st.session_state.font_preferences)
    st.markdown(
        f"""
        <script>
            localStorage.setItem('onco_aide_font', '{prefs_json}');
        </script>
        """,
        unsafe_allow_html=True
    )

def apply_font_preferences():
    font_family = st.session_state.font_preferences.get("font_family", "Montserrat")
    text_size = st.session_state.font_preferences.get("text_size", "medium")
    
    # Map text size names to actual CSS values
    size_map = {
        "small": "0.9rem",
        "medium": "1rem",
        "large": "1.2rem",
        "x-large": "1.4rem"
    }
    
    font_size = size_map[text_size]
    
    # Apply CSS based on preferences
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family={font_family.replace(' ', '+')}:wght@300;400;500;600;700&display=swap');
        
        * {{
            font-family: '{font_family}', sans-serif !important;
            font-size: {font_size} !important;
        }}
        
        .stMarkdown, .stText, .stTitle, .stHeader {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stButton button {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stTextInput input {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        .stSelectbox select {{
            font-family: '{font_family}', sans-serif !important;
        }}
        
        /* Adjust heading sizes proportionally */
        h1 {{
            font-size: calc({font_size} * 2.0) !important;
        }}
        
        h2 {{
            font-size: calc({font_size} * 1.5) !important;
        }}
        
        h3 {{
            font-size: calc({font_size} * 1.3) !important;
        }}
    </style>
    """, unsafe_allow_html=True)


def initialize_custom_commands():
    if 'custom_commands' not in st.session_state:
        # Try to load from local storage
        placeholder_div = st.empty()
        placeholder_div.markdown(
            """
            <div id="load_commands" style="display:none;"></div>
            <script>
                const cmdDiv = document.getElementById('load_commands');
                const savedCmds = localStorage.getItem('onco_aide_custom_commands');
                if (savedCmds) {
                    cmdDiv.innerText = savedCmds;
                } else {
                    cmdDiv.innerText = JSON.stringify({});
                }
                setTimeout(() => {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: cmdDiv.innerText,
                        dataType: 'string',
                        key: 'loaded_commands'
                    }, '*');
                }, 100);
            </script>
            """,
            unsafe_allow_html=True
        )
        
        # Wait for the JavaScript to set the value
        if 'loaded_commands' in st.session_state:
            placeholder_div.empty()
            try:
                st.session_state.custom_commands = json.loads(st.session_state.loaded_commands)
            except:
                st.session_state.custom_commands = {}
        else:
            st.session_state.custom_commands = {}

def save_custom_commands():
    cmds_json = json.dumps(st.session_state.custom_commands)
    st.markdown(
        f"""
        <script>
            localStorage.setItem('onco_aide_custom_commands', '{cmds_json}');
        </script>
        """,
        unsafe_allow_html=True
    )

# Initialize Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)

# Page configuration
st.set_page_config(
    page_title="Onco-AIDE",
    page_icon="./favicon.ico",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap');

    * {
        font-family: 'Montserrat', sans-serif !important;
    }

    .stChatInputContainer {
        display: flex;
        align-items: center;
    }
    .back-button {
        width: 300px;
        margin-top: 20px;
        padding: 10px 20px;
        font-size: 18px;
        background-color: #0b1936;
        color: #5799f7;
        border: 2px solid #4a83d4;
        border-radius: 10px;
        cursor: pointer;
        transition: all 0.3s ease;
        font-family: 'Montserrat', sans-serif !important;
        text-transform: uppercase;
        letter-spacing: 2px;
        box-shadow: 0 0 15px rgba(74, 131, 212, 0.3);
        position: relative;
        overflow: hidden;
        display: inline-block;
    }
    .back-button:hover {
        background-color: #1c275c;
        color: #73abfa;
        transform: translateY(-2px);
        box-shadow: 0 6px 8px rgba(74, 131, 212, 0.2);
    }
    .back-button:hover:before {
        transform: translateY(-100%);
        color: #73abfa;
    }
    .file-preview {
        max-height: 200px;
        overflow: hidden;
        margin-bottom: 10px;
    }
    .file-preview img, .file-preview video, .file-preview audio {
        max-width: 100%;
        max-height: 200px;
        object-fit: contain;
    }

    .stMarkdown, .stText, .stTitle, .stHeader {
        font-family: 'Montserrat', sans-serif !important;
    }
    
    .stButton button {
        font-family: 'Montserrat', sans-serif !important;
    }
    
    .stTextInput input {
        font-family: 'Montserrat', sans-serif !important;
    }
    
    .stSelectbox select {
        font-family: 'Montserrat', sans-serif !important;
    }
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
                    window.parent.postMessage({
                        type: 'clipboard_paste',
                        data: base64data,
                        format: 'image'
                    }, '*');
                };
                reader.readAsDataURL(blob);
            } else if (item.type === 'text/plain') {
                item.getAsString(function(text) {
                    window.parent.postMessage({
                        type: 'clipboard_paste',
                        data: text,
                        format: 'text'
                    }, '*');
                });
            }
        }
    }
});
window.addEventListener('message', function(e) {
    if (e.data.type === 'clipboard_paste') {
        const args = {
            'data': e.data.data,
            'format': e.data.format
        };
        window.parent.postMessage({
            type: 'streamlit:set_widget_value',
            key: 'clipboard_data',
            value: args
        }, '*');
    }
});
</script>""", unsafe_allow_html=True)

generation_config = {
    "temperature": 0,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

SYSTEM_INSTRUCTION = """
Name: Your name is Onco-AIDE. Your name stands for Onco-AI Dialogue Engine

Behavioral Guidelines:
Be helpful and professional, ensuring accuracy in every response.
Maintain a friendly, approachable tone while providing precise and concise answers.
Keep all discussions focused around cancer studies.
After every message, put a new line and type out Citations: in bold, and provide any relevant links online to helpful sources as a citation of sorts.

"""

def extract_pdf_text(file):
    try:
        # Try using PyMuPDF (fitz) first for better PDF extraction
        try:
            pdf_document = fitz.open(stream=file.read(), filetype="pdf")
            text = ""
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                text += page.get_text()
            return text
        except:
            # Fall back to PyPDF2 if PyMuPDF fails
            file.seek(0)  # Reset file pointer
            pdf = PdfReader(file)
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
            return text
    except Exception as e:
        return f"Error extracting PDF text: {str(e)}"

def extract_docx_text(file):
    try:
        doc = Document(file)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])
    except Exception as e:
        return f"Error extracting DOCX text: {str(e)}"

def extract_image_text(file):
    try:
        image = Image.open(file)
        return pytesseract.image_to_string(image)
    except Exception as e:
        return f"Error extracting image text: {str(e)}"

def process_structured_data(file, mime_type):
    try:
        if mime_type == 'text/csv':
            df = pd.read_csv(file)
            return df.to_string()
        elif mime_type == 'application/json':
            return json.dumps(json.load(file), indent=2)
        elif mime_type == 'application/xml':
            tree = ET.parse(file)
            return ET.tostring(tree.getroot(), encoding='unicode', method='xml')
        return file.read().decode('utf-8')
    except Exception as e:
        return f"Error processing structured data: {str(e)}"

def process_response(text):
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        if re.match(r'^\d+\.', line.strip()):
            processed_lines.append('\n' + line.strip())
        elif line.strip().startswith('*') or line.strip().startswith('-'):
            processed_lines.append('\n' + line.strip())
        else:
            processed_lines.append(line)
    
    text = '\n'.join(processed_lines)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    text = re.sub(r'(\n[*-] .+?)(\n[^*\n-])', r'\1\n\2', text)
    
    return text.strip()

# Add this function to handle clipboard data
def handle_clipboard_data():
    if 'clipboard_data' not in st.session_state:
        return
        
    clipboard_data = st.session_state.get('clipboard_data')
    if clipboard_data:
        try:
            if clipboard_data['format'] == 'image':
                img_data = base64.b64decode(clipboard_data['data'].split(',')[1])
                file = BytesIO(img_data)
                file.name = f'pasted_image_{int(time.time())}.png'
                return file
            elif clipboard_data['format'] == 'text':
                file = BytesIO(clipboard_data['data'].encode())
                file.name = f'pasted_text_{int(time.time())}.txt'
                return file
        finally:
            st.session_state.clipboard_data = None
    return None

def save_accessibility_preferences():
    prefs_json = json.dumps(st.session_state.accessibility)
    st.markdown(
        f"""
        <script>
            localStorage.setItem('onco_aide_accessibility', '{prefs_json}');
        </script>
        """,
        unsafe_allow_html=True
    )

def apply_accessibility_settings():
    if 'accessibility' not in st.session_state:
        # Try to load from local storage
        placeholder_div = st.empty()
        placeholder_div.markdown(
            """
            <div id="load_accessibility" style="display:none;"></div>
            <script>
                const accDiv = document.getElementById('load_accessibility');
                const savedPrefs = localStorage.getItem('onco_aide_accessibility');
                if (savedPrefs) {
                    accDiv.innerText = savedPrefs;
                } else {
                    accDiv.innerText = JSON.stringify({
                        high_contrast: false,
                        reduce_motion: false
                    });
                }
                setTimeout(() => {
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: accDiv.innerText,
                        dataType: 'string',
                        key: 'loaded_accessibility'
                    }, '*');
                }, 100);
            </script>
            """,
            unsafe_allow_html=True
        )
        
        # Wait for the JavaScript to set the value
        if 'loaded_accessibility' in st.session_state:
            placeholder_div.empty()
            try:
                st.session_state.accessibility = json.loads(st.session_state.loaded_accessibility)
            except:
                # Default preferences if loading fails
                st.session_state.accessibility = {
                    "high_contrast": False,
                    "reduce_motion": False
                }
        else:
            # Default preferences
            st.session_state.accessibility = {
                "high_contrast": False,
                "reduce_motion": False
            }
    
    # Apply accessibility settings
    high_contrast = st.session_state.accessibility.get('high_contrast', False)
    reduce_motion = st.session_state.accessibility.get('reduce_motion', False)
    
    css = []
    
    if high_contrast:
        css.append("""
        * {
            color: white !important;
            background-color: black !important;
        }
        a, button, .stButton button {
            color: yellow !important;
            border-color: yellow !important;
        }
        .stTextInput input, .stSelectbox select {
            color: white !important;
            background-color: #333 !important;
            border: 2px solid yellow !important;
        }
        """)
    
    if reduce_motion:
        css.append("""
        * {
            animation: none !important;
            transition: none !important;
        }
        """)
    
    if css:
        st.markdown(f"<style>{''.join(css)}</style>", unsafe_allow_html=True)

def detect_file_type(uploaded_file):
    filename = uploaded_file.name
    file_ext = os.path.splitext(filename)[1].lower()
    
    mime_mappings = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg', 
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.tiff': 'image/tiff',
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo', 
        '.mov': 'video/quicktime',
        '.mkv': 'video/x-matroska',
        '.webm': 'video/webm',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.json': 'application/json',
        '.xml': 'application/xml'
    }
    
    if file_ext in mime_mappings:
        return mime_mappings[file_ext]
    
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'
    
def initialize_session_state():
    # Initialize font preferences
    initialize_font_preferences()
    apply_font_preferences()
    apply_accessibility_settings()
    
    if 'chat_model' not in st.session_state:
        st.session_state.chat_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            system_instruction=SYSTEM_INSTRUCTION,
        )

    if 'chat_session' not in st.session_state:
        st.session_state.chat_session = st.session_state.chat_model.start_chat(history=[])

    if 'messages' not in st.session_state:
        initial_message = """Welcome to the Onco-AI Dialogue Engine. What would you like to learn about?"""
        st.session_state.messages = [
            {"role": "assistant", "content": initial_message}
        ]
    
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = []
        
    if 'processed_audio_hashes' not in st.session_state:
        st.session_state.processed_audio_hashes = set()
        
    if 'camera_image' not in st.session_state:
        st.session_state.camera_image = None
        
    if 'camera_enabled' not in st.session_state:
        st.session_state.camera_enabled = False

    if 'clipboard_data' not in st.session_state:
        st.session_state.clipboard_data = None
        
    if 'file_upload_expanded' not in st.session_state:
        st.session_state.file_upload_expanded = False
    initialize_custom_commands()
    
    # For custom command form
    if 'show_custom_cmd_form' not in st.session_state:
        st.session_state.show_custom_cmd_form = False

def get_audio_hash(audio_data):
    return hashlib.md5(audio_data.getvalue()).hexdigest()

def convert_audio_to_text(audio_file):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            return text
    except sr.UnknownValueError:
        raise Exception("Speech recognition could not understand the audio")
    except sr.RequestError as e:
        raise Exception(f"Could not request results from speech recognition service; {str(e)}")

def save_audio_file(audio_data):
    audio_bytes = audio_data.getvalue()
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmpfile:
        tmpfile.write(audio_bytes)
        return tmpfile.name

def handle_chat_response(response, message_placeholder, command_message=""):
    full_response = ""
    
    # First display command message if it exists
    if command_message:
        full_response = f"{command_message}\n\n"
        message_placeholder.markdown(full_response)
    
    # Process and format the AI response
    formatted_response = process_response(response.text)
    
    # Split into chunks for streaming effect
    chunks = []
    for line in formatted_response.split('\n'):
        chunks.extend(line.split(' '))
        chunks.append('\n')
    
    # Stream the response chunks with typing effect
    for chunk in chunks:
        if chunk != '\n':
            full_response += chunk + ' '
        else:
            full_response += chunk
        time.sleep(0.02)
        message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
    
    # Display final response without cursor
    message_placeholder.markdown(full_response, unsafe_allow_html=True)
    return full_response
    
def show_file_preview(uploaded_file):
    mime_type = detect_file_type(uploaded_file)
    
    if mime_type.startswith('image/'):
        st.sidebar.image(uploaded_file, use_container_width=True)
    elif mime_type.startswith('video/'):
        st.sidebar.video(uploaded_file)
    elif mime_type.startswith('audio/'):
        st.sidebar.audio(uploaded_file)
    else:
        st.sidebar.info(f"Uploaded: {uploaded_file.name} (Type: {mime_type})")

def prepare_chat_input(prompt, files):
    input_parts = []
    
    for file in files:
        mime_type = detect_file_type(file)
        content = None
        
        try:
            if mime_type.startswith('application/pdf'):
                content = extract_pdf_text(file)
            elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                content = extract_docx_text(file)
            elif mime_type.startswith('image/'):
                content = extract_image_text(file)
            elif mime_type in ['text/csv', 'application/json', 'application/xml', 'text/plain']:
                content = process_structured_data(file, mime_type)
            
            if content:
                input_parts.append({
                    'type': mime_type,
                    'content': content,
                    'name': file.name
                })
        except Exception as e:
            st.error(f"Error processing {file.name}: {str(e)}")
            continue
    
    input_parts.append(prompt)
    return input_parts

def main():
    initialize_session_state()

    st.title("💬 Onco-AIDE")

    # Sign Out Button and Settings
    with st.sidebar:
        st.link_button("Back to OncoAI", "https://oncoai.org/")
        with st.expander("**Settings & Preferences**", expanded=False):
            # Font selection
            available_fonts = [
                "Montserrat", "DM Sans", "Calibri", 
                "Arial", "Times New Roman", "Roboto", "Open Sans",
                "Lato", "Poppins", "Ubuntu", "Orbitron", "Playfair Display"
            ]
            
            # Font search/filter
            font_search = st.text_input("Search Fonts", key="font_search")
            filtered_fonts = [f for f in available_fonts if font_search.lower() in f.lower()] if font_search else available_fonts
            
            font_family = st.selectbox(
                "Font Family",
                filtered_fonts,
                index=filtered_fonts.index(st.session_state.font_preferences["font_family"]) if st.session_state.font_preferences["font_family"] in filtered_fonts else 0,
                key="font_family_select"
            )
            
            text_size = st.selectbox(
                "Text Size",
                ["Small", "Medium", "Large", "X-Large"],
                index=["small", "medium", "large", "x-large"].index(st.session_state.font_preferences.get("text_size", "medium")),
                key="text_size_select"
            )
            
            # Font selection and application button
            if st.button("Apply Font", key="apply_font"):
                st.session_state.font_preferences = {
                    "font_family": font_family
                }
                save_font_preferences()
                st.rerun()
            
            # Add accessibility options directly (not in another expander)
            st.markdown("---")
            st.markdown("**Accessibility Options**")
            
            # Initialize accessibility state if needed
            if 'accessibility' not in st.session_state:
                st.session_state.accessibility = {
                    'high_contrast': False,
                    'reduce_motion': False
                }
            
            # High contrast mode
            high_contrast = st.checkbox(
                "High Contrast Mode", 
                value=st.session_state.accessibility.get('high_contrast', False),
                key="high_contrast",
                help="Increases color contrast for better visibility"
            )
            
            # Reduce motion
            reduce_motion = st.checkbox(
                "Reduce Motion", 
                value=st.session_state.accessibility.get('reduce_motion', False),
                key="reduce_motion",
                help="Reduces animations and transitions"
            )
            
            # Apply settings button
            if st.button("Apply Settings", key="apply_accessibility"):
                st.session_state.accessibility = {
                    'high_contrast': high_contrast,
                    'reduce_motion': reduce_motion
                }
                save_accessibility_preferences()
                st.rerun()

    # File Upload Section
    with st.sidebar:
        with st.expander("**File Upload**", expanded=False):
            st.markdown("**ALWAYS** upload one file at a time.")
            clipboard_file = handle_clipboard_data()
            if clipboard_file:
                st.session_state.uploaded_files.append(clipboard_file)
            uploaded_files = st.file_uploader(
                "Upload files to analyze", 
                type=[
                    'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff',
                    'mp4', 'avi', 'mov', 'mkv', 'webm',
                    'mp3', 'wav', 'ogg', 'm4a',
                    'pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'json', 'xml'
                ],
                accept_multiple_files=True
            )

            if uploaded_files:
                oversized_files = []
                valid_files = []
                
                for file in uploaded_files:
                    if file.size > 20 * 1024 * 1024:  # 20MB limit
                        oversized_files.append(file.name)
                    else:
                        valid_files.append(file)
                
                if oversized_files:
                    st.warning(f"Files exceeding 20MB limit: {', '.join(oversized_files)}")
                
                st.session_state.uploaded_files = valid_files

    # Prebuilt Commands Section
    with st.sidebar:
        with st.expander("**FAQ**", expanded=False):
            if 'current_command' not in st.session_state:
                st.session_state.current_command = None
            
            for cmd, info in PREBUILT_COMMANDS.items():
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    button_active = st.session_state.current_command == cmd
                    if st.button(
                        info["title"],
                        key=f"cmd_{cmd}",
                        type="primary" if button_active else "secondary"
                    ):
                        if st.session_state.current_command == cmd:
                            st.session_state.current_command = None
                        else:
                            st.session_state.current_command = cmd
                        st.rerun()
                
                with col2:
                    help_key = f"help_{cmd}"
                    if help_key not in st.session_state:
                        st.session_state[help_key] = False
                    
                    button_text = "×" if st.session_state[help_key] else "?"
                    if st.button(button_text, key=f"help_btn_{cmd}"):
                        st.session_state[help_key] = not st.session_state[help_key]
                        st.rerun()
                
                if st.session_state[help_key]:
                    st.info(info["description"])

    # Display messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)

    # Chat input handling
    prompt = st.chat_input("What can I help you with?")

    if prompt:
        final_prompt = prompt
        command_suffix = ""
        command_message = ""
        
        if hasattr(st.session_state, 'current_command') and st.session_state.current_command:
            command = st.session_state.current_command
            
            # Check if it's a built-in command or custom command
            if command in PREBUILT_COMMANDS:
                command_prompt = PREBUILT_COMMANDS[command]["prompt"]
                command_suffix = f" **[{command}]**"
                command_message = PREBUILT_COMMANDS[command].get("message_text", "")
            elif command in st.session_state.custom_commands:
                command_prompt = st.session_state.custom_commands[command]["prompt"]
                command_suffix = f" **[{command}]**"
                command_message = st.session_state.custom_commands[command].get("message_text", "")
            
            final_prompt = f"{command_prompt}\n{prompt}"
            st.session_state.current_command = None

        input_parts = []
        
        if st.session_state.uploaded_files:
            for file in st.session_state.uploaded_files:
                input_parts.append({
                    'mime_type': detect_file_type(file),
                    'data': file.getvalue()
                })
        
        if st.session_state.camera_image:
            input_parts.append({
                'mime_type': 'image/jpeg',
                'data': st.session_state.camera_image.getvalue()
            })

        input_parts.append(final_prompt)

        st.chat_message("user").markdown(prompt + command_suffix)
        st.session_state.messages.append({"role": "user", "content": prompt + command_suffix})
        
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            
            try:
                response = st.session_state.chat_session.send_message(input_parts)
                full_response = handle_chat_response(response, message_placeholder)
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response
                })
                
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                if "rate_limit" in str(e).lower():
                    st.warning("The API rate limit has been reached. Please wait a moment before trying again.")
                else:
                    st.warning("Please try again in a moment.")

        if st.session_state.camera_image and not st.session_state.camera_enabled:
            st.session_state.camera_image = None

if __name__ == "__main__":
    main()
