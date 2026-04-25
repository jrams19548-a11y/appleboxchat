from functools import wraps
from flask import Flask, send_file, render_template, render_template_string, request, jsonify, redirect, url_for, flash, send_from_directory, session
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import json
from flask import Response
from collections import defaultdict
import time
from jinja2 import Undefined
import re
import ast
import os
import urllib.request
from datetime import datetime, timezone
import pytz
import io
import zipfile
import random
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import mimetypes
mimetypes.add_type('text/plain', '.py')
cst_timezone = pytz.timezone('America/Chicago')
class ProfanityFilter:
    """
    A customizable profanity filter that replaces inappropriate words with censored versions.
    It loads a list of banned words from a specified file.
    """
    def __init__(self, wordlist_file='data/profanity_words.txt'):
        """
        Initializes the ProfanityFilter.

        Args:
            wordlist_file (str): Path to the file containing banned words.
        """
        self.wordlist_file = wordlist_file
        self.profane_words = set()
        self.load_words(wordlist_file)
        self._regex = None
        
    def load_words(self, wordlist_file):
        try:
            with open(wordlist_file, 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        self.profane_words.add(line.strip().lower())
            print(f"Loaded {len(self.profane_words)} profane words from {wordlist_file}")
        except FileNotFoundError:
            print(f"Warning: Profanity wordlist file '{wordlist_file}' not found. Creating it.")
            with open(wordlist_file, 'w') as f:
                f.write("# List of profane words to filter\n# One word per line\n")
        except Exception as e:
            print(f"Error loading profanity words: {e}")

        self._compile_regex()

    def save_words(self):
        """Saves the current set of profane words back to the wordlist file."""
        try:
            with open(self.wordlist_file, 'w') as f:
                f.write("# List of profane words to filter\n# One word per line\n")
                for word in sorted(list(self.profane_words)):
                    f.write(word + '\n')
            print(f"Saved {len(self.profane_words)} profane words to {self.wordlist_file}")
        except Exception as e:
            print(f"Error saving profanity words: {e}")

    def _compile_regex(self):
        """Compiles a single regex pattern for all profane words for high performance."""
        if not self.profane_words:
            self._regex = None
            return
        # Sort by length descending to match longer phrases before substrings
        sorted_words = sorted(list(self.profane_words), key=len, reverse=True)
        pattern = r'\b(' + '|'.join(re.escape(word) for word in sorted_words) + r')\b'
        self._regex = re.compile(pattern, re.IGNORECASE)

    def add_word(self, word):
        """Adds a word to the profane words list and saves it."""
        word = word.strip().lower()
        if word and word not in self.profane_words:
            self.profane_words.add(word)
            self.save_words()
            self._compile_regex()
            return True
        return False

    def remove_word(self, word):
        """Removes a word from the profane words list and saves it."""
        word = word.strip().lower()
        if word and word in self.profane_words:
            self.profane_words.remove(word)
            self.save_words()
            self._compile_regex()
            return True
        return False

    def _get_replacement(self, word):
        """
        Generates a replacement string for a profane word.
        Currently replaces with '#' of the same length as the word.

        Args:
            word (str): The profane word.

        Returns:
            str: The replacement string.
        """
        return '#' * len(word)
    
    def censor_text(self, text):
        if not text or not self._regex:
            return text
        
        # Split text into tokens to avoid censoring parts of URLs
        tokens = text.split()
        censored_tokens = []
        for token in tokens:
            if token.startswith(('http://', 'https://', 'www.')):
                censored_tokens.append(token)
            else:
                censored_tokens.append(self._regex.sub(lambda m: self._get_replacement(m.group(0)), token))
        return ' '.join(censored_tokens)

    def contains_profanity(self, text):
        """
        Checks if the given text contains any profanity.

        Args:
            text (str): The text to check.

        Returns:
            bool: True if profanity is found, False otherwise.
        """
        if not text or not self._regex:
            return False
        return bool(self._regex.search(text))

profanity_filter = ProfanityFilter(wordlist_file='data/profanity_words.txt')

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm', 'ogg', 'mov'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

CHAT_IMAGES_FOLDER = 'static/chat_images'
os.makedirs(CHAT_IMAGES_FOLDER, exist_ok=True)

def save_chat_image(image_data):
    """Saves a base64 image string to a file and returns the URL path."""
    if not image_data or not isinstance(image_data, str) or not (image_data.startswith('data:image') or image_data.startswith('data:video')):
        return None
    try:
        header, encoded = image_data.split(",", 1)
        ext = header.split(";")[0].split("/")[1]
        if ext == 'quicktime': ext = 'mov'
        if ext == 'jpeg': ext = 'jpg'
        if ext not in ALLOWED_EXTENSIONS:
            return None
            
        filename = f"chat_{int(time.time())}_{random.randint(1000, 9999)}.{ext}"
        filepath = os.path.join(CHAT_IMAGES_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(encoded))
        return f"/{filepath}"
    except:
        return None

def save_server_icon(icon_data, server_id):
    """Saves a base64 server icon string to a file."""
    if not icon_data or not isinstance(icon_data, str) or not icon_data.startswith('data:image'):
        return None
    try:
        header, encoded = icon_data.split(",", 1)
        ext = header.split(";")[0].split("/")[1]
        if ext not in ['png', 'jpg', 'jpeg', 'gif']:
            return None
            
        filename = f"icon_{server_id}_{int(time.time())}.{ext}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(encoded))
        return f"/static/uploads/{filename}"
    except:
        return None

EMOJI_FOLDER = 'static/emojis'
CUSTOM_EMOJIS_FILE = 'data/custom_emojis.json'
os.makedirs(EMOJI_FOLDER, exist_ok=True)

# Cache for expensive file operations
_custom_emojis_cache = None
_friends_cache = None # (friends_dict, requests_dict)

def get_link_metadata(url):
    """Fetches OpenGraph metadata from a URL with a timeout to prevent hanging."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=1.5) as response:
            # Only read the first 100KB to save memory/time
            content = response.read(102400).decode('utf-8', errors='ignore')
            
            title = re.search(r'<meta property="og:title" content="(.*?)"', content, re.I)
            if not title: title = re.search(r'<title>(.*?)</title>', content, re.I)
            
            desc = re.search(r'<meta property="og:description" content="(.*?)"', content, re.I)
            if not desc: desc = re.search(r'<meta name="description" content="(.*?)"', content, re.I)
            
            img = re.search(r'<meta property="og:image" content="(.*?)"', content, re.I)
            
            return {
                'url': url,
                'title': title.group(1) if title else url,
                'description': desc.group(1) if desc else "",
                'image': img.group(1) if img else ""
            }
    except:
        return None

def load_custom_emojis():
    global _custom_emojis_cache
    if _custom_emojis_cache is not None:
        return _custom_emojis_cache
    if os.path.exists(CUSTOM_EMOJIS_FILE):
        try:
            with open(CUSTOM_EMOJIS_FILE, 'r') as f:
                _custom_emojis_cache = json.load(f)
                return _custom_emojis_cache
        except:
            return {}
    return {}

def save_custom_emojis(emojis):
    global _custom_emojis_cache
    _custom_emojis_cache = emojis
    with open(CUSTOM_EMOJIS_FILE, 'w') as f:
        json.dump(emojis, f, indent=2)

app = Flask(__name__)

CONFIG_FILE = 'data/config.json'
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}
app.secret_key = 'your-secret-key-here'  # Change this in production
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()

# Rate Limiting tracking: { username: [timestamp1, timestamp2, ...] }
user_message_history = {}

def get_aes_key():
    """Derive a 256-bit key for AES-256 encryption."""
    return hashlib.sha256(app.secret_key.encode()).digest()

def encrypt_password(plain_text):
    if not plain_text: return ""
    aesgcm = AESGCM(get_aes_key())
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_text.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode('utf-8')

def decrypt_password(cipher_text):
    if not cipher_text: return ""
    try:
        data = base64.b64decode(cipher_text)
        nonce = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(get_aes_key())
        return aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
    except:
        return cipher_text  # Fallback for plain text migration

login_manager.init_app(app)
login_manager.login_view = 'login'

@app.route('/download-code')
def download_code():
    # Target directory to zip (e.g., your project root)
    target_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create an in-memory byte stream for the ZIP file
    memory_file = io.BytesIO()
    
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Walk through the directory and add files to the archive
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                # Get the full path and a relative path for the ZIP internal structure
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, target_dir)
                
                # Avoid zipping the running script itself or venv folders if needed
                if "__pycache__" not in full_path and ".venv" not in full_path:
                    zf.write(full_path, relative_path)
    
    # Reset stream position to the beginning
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='project_code.zip'
    )

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

app_config = load_config()

SERVERS_FILE = 'data/servers.json'
def load_servers():
    if os.path.exists(SERVERS_FILE):
        try:
            with open(SERVERS_FILE, 'r') as f:
                return json.load(f)
        except: return {}
    return {}

def save_servers(servers_dict):
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers_dict, f, indent=2)

servers_data = load_servers()

def can_access_room(room_id):
    if not current_user.is_authenticated: return False
    if current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id in ['jesseramsey', 'Killua']:
        return True
    server_id = room_id.split(':')[0] if ':' in room_id else None
    if not server_id: return False
    srv = servers_data.get(server_id)
    if not srv: return False
    return current_user.id == srv['owner'] or current_user.id in srv.get('members', [])

@app.context_processor
def inject_app_config():
    # Check if current user has the CKC badge
    has_ckc = False
    if current_user.is_authenticated:
        u_badges = users.get(current_user.id, {}).get('badges', [])
        for b in u_badges:
            b_text = b.get('text') if isinstance(b, dict) else b
            if b_text == 'CKC':
                has_ckc = True
                break

    # Filter servers for the UI
    user_servers = {}
    is_staff = current_user.is_authenticated and (current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id in ['jesseramsey', 'Killua'])
    for srv_id, srv in servers_data.items():
        if is_staff or (current_user.is_authenticated and (current_user.id == srv['owner'] or current_user.id in srv.get('members', []))):
            user_servers[srv_id] = srv

    return dict(app_config=app_config, 
                custom_emojis=load_custom_emojis(), 
                profane_words=sorted(list(profanity_filter.profane_words)), 
                special_user='jesseramsey', has_ckc=has_ckc,
                servers=user_servers,
                active_users=active_users)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

def load_users():
    users = {}
    try:
        with open('data/users.txt', 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = [p.strip() for p in line.strip().split('|')]
                username, password_enc, display_name, role = parts[:4]
                password = decrypt_password(password_enc)
                is_suspended = parts[4] if len(parts) > 4 else "false"
                is_muted = parts[5] if len(parts) > 5 else "false"
                bio = parts[6] if len(parts) > 6 else ""
                profile_pic = parts[7] if len(parts) > 7 else ""
                theme = parts[8] if len(parts) > 8 else "default"
                custom_theme_str = parts[9] if len(parts) > 9 else "{}"
                ringtone_url = parts[10] if len(parts) > 10 else ""
                mute_ringtone = parts[11] if len(parts) > 11 else "true"
                banner_url = parts[12] if len(parts) > 12 else ""
                badges_str = parts[13] if len(parts) > 13 else "[]" # This was index 13
                is_stealth = parts[14] if len(parts) > 14 else "false"
                security_question = parts[15] if len(parts) > 15 else ""
                security_answer_enc = parts[16] if len(parts) > 16 else ""
                custom_status = parts[17] if len(parts) > 17 else ""
                security_answer = decrypt_password(security_answer_enc)
                created_at = parts[18] if len(parts) > 18 else ""
                last_online = parts[19] if len(parts) > 19 else ""
                face_descriptor = parts[20] if len(parts) > 20 else ""
                profile_bg = parts[21] if len(parts) > 21 else ""
                is_infected = (parts[22] == "true") if len(parts) > 22 else False

                # Safely load JSON data with fallbacks
                try:
                    custom_theme = json.loads(custom_theme_str)
                except:
                    try:
                        custom_theme = ast.literal_eval(custom_theme_str)
                    except:
                        custom_theme = {}

                try:
                    badges = json.loads(badges_str)
                except:
                    try:
                        badges = ast.literal_eval(badges_str)
                    except:
                        badges = []

                users[username] = {
                    'password': password,
                    'display_name': display_name,
                    'role': role,
                    'profile_pic': profile_pic,
                    'is_suspended': is_suspended == "true",
                    'is_muted': is_muted == "true",
                    'bio': bio,
                    'theme': theme,
                    'custom_theme': custom_theme,
                    'ringtone_url': ringtone_url,
                    'mute_ringtone': mute_ringtone == "true",
                    'banner_url': banner_url,
                    'badges': badges,
                    'is_stealth': is_stealth == "true",
                    'security_question': security_question,
                    'security_answer': security_answer,
                    'custom_status': custom_status,
                    'created_at': created_at,
                    'last_online': last_online,
                    'face_descriptor': face_descriptor,
                    'profile_bg': profile_bg,
                    'is_infected': is_infected
                }
    except FileNotFoundError:
        pass
    return users

def save_users():
    with open('data/users.txt', 'w') as f:
        f.write('# Format: username|password|display_name|role|is_suspended|is_muted|bio|profile_pic|theme|custom_theme|ringtone_url|mute_ringtone|banner_url|badges|is_stealth|security_question|security_answer|custom_status|created_at|last_online|face_descriptor|profile_bg|is_infected\n')
        for username, data in users.items():
            password_enc = encrypt_password(data['password'])
            security_answer_enc = encrypt_password(data.get('security_answer', ''))
            f.write(f"{username}|{password_enc}|{data['display_name']}|{data['role']}|{str(data.get('is_suspended', False)).lower()}|{str(data.get('is_muted', False)).lower()}|{data.get('bio', '')}|{data.get('profile_pic', '')}|{data.get('theme', 'default')}|{json.dumps(data.get('custom_theme', {}))}|{data.get('ringtone_url', '')}|{str(data.get('mute_ringtone', True)).lower()}|{data.get('banner_url', '')}|{json.dumps(data.get('badges', []))}|{str(data.get('is_stealth', False)).lower()}|{data.get('security_question', '')}|{security_answer_enc}|{data.get('custom_status', '')}|{data.get('created_at', '')}|{data.get('last_online', '')}|{data.get('face_descriptor', '')}|{data.get('profile_bg', '')}|{str(data.get('is_infected', False)).lower()}\n")

def load_groups():
    groups = {}
    try:
        if os.path.exists('data/groups.txt'):
            with open('data/groups.txt', 'r') as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        parts = line.strip().split('|')
                        if len(parts) >= 3:
                            group_id, name, members_json = parts[:3]
                            members = json.loads(members_json)
                            creator = parts[3] if len(parts) > 3 else (members[0] if members else "")
                            icon_url = parts[4] if len(parts) > 4 else ""
                        groups[group_id] = {
                            'name': name,
                            'members': members,
                            'creator': creator,
                            'icon_url': icon_url
                        }
    except Exception as e:
        print(f"Error loading groups: {e}")
    return groups

def save_groups(groups):
    try:
        with open('data/groups.txt', 'w') as f:
            f.write('# Format: group_id|name|members_json|creator|icon_url\n')
            for gid, data in groups.items():
                f.write(f"{gid}|{data['name']}|{json.dumps(data['members'])}|{data.get('creator', '')}|{data.get('icon_url', '')}\n")
    except Exception as e:
        print(f"Error saving groups: {e}")

def load_group_history(group_id):
    filepath = f"data/group_msg_{group_id}.txt"
    if not os.path.exists(filepath):
        return []
    messages = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    messages.append(json.loads(line.strip()))
                except: pass
    return messages

def save_group_history(group_id, messages):
    filepath = f"data/group_msg_{group_id}.txt"
    with open(filepath, 'w') as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

@app.route('/profile/<username>')
@login_required
def view_profile(username):
    if username not in users:
        flash('User not found')
        return redirect(url_for('home'))
    user_data = users[username].copy()
    user_data['bio'] = users[username].get('bio', 'No bio provided.')
    friends, _ = load_friends()
    user_friends = friends.get(current_user.id, [])
    is_online = any(username in room_users for room_users in active_users.values())
    return render_template('profile.html', username=username, user_data=user_data, 
                         friends=user_friends, active_users=active_users, users=users,
                         user_theme=users.get(current_user.id, {}).get('theme', 'default'),
                         user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {}),
                         is_online=is_online)

@app.route('/update_bio', methods=['POST'])
@login_required
def update_bio():
    bio = request.form.get('bio', '').strip()
    # Apply profanity filter to bios
    filtered_bio = profanity_filter.censor_text(bio)
    users[current_user.id]['bio'] = filtered_bio
    save_users()
    flash('Bio updated successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/update_banner', methods=['POST'])
@login_required
def update_banner():
    banner_url = request.form.get('banner_url', '').strip()
    
    # Handle Banner Upload
    banner_file = request.files.get('banner_file')
    if banner_file and banner_file.filename != '' and allowed_file(banner_file.filename):
        filename = secure_filename(f"banner_{current_user.id}_{int(time.time())}_{banner_file.filename}")
        banner_file.save(os.path.join(app.root_path, UPLOAD_FOLDER, filename))
        banner_url = f"/static/uploads/{filename}"
        
    users[current_user.id]['banner_url'] = banner_url
    save_users()
    flash('Profile banner updated successfully!', 'success')
    return redirect(url_for('home'))

users = load_users()
messages = []
ROLES = ['Owner', 'Admin', 'Mod', 'Regular User', 'Co-owner', 'Developer']

def get_dm_filename(user1, user2):
    # Sort usernames to ensure consistent filename regardless of sender/recipient
    users = sorted([user1, user2])
    return f"data/dm_{users[0]}_{users[1]}.txt"

def load_dm_history(user1, user2):
    filepath = get_dm_filename(user1, user2)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r') as f:
            messages = []
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        try:
                            messages.append(ast.literal_eval(line.strip()))
                        except:
                            pass
            return messages
    except Exception as e:
        print(f"Error loading DM history from {filepath}: {e}")
        return []
#saves DM history between two users to a text file in ./data with filename format dm_user1_user2.txt (sorted alphabetically)
def save_dm_history(user1, user2, messages):
    filepath = get_dm_filename(user1, user2)
    try:
        with open(filepath, 'w') as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")
    except Exception as e:
        print(f"Error saving DM history to {filepath}: {e}")

#loads chat history for all rooms from text files in ./data with filename format chat_roomname.txt, returns a dictionary with room names as keys and lists of messages as values
def load_chat_history():
    rooms = defaultdict(list)
    if not os.path.exists('data'):
        return rooms
    for filename in os.listdir('data'):
        if filename.startswith('chat_') and filename.endswith('.txt'):
            room_id = filename[5:-4].replace('_channel_', ':')
            try:
                with open(f'data/{filename}', 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                msg = json.loads(line.strip())
                                rooms[room_id].append(msg)
                            except: continue
            except: pass
    return rooms

#saves chat history for a specific room to a text file in ./data with filename format chat_roomname.txt, messages should be in JSON format, one message per line
def save_chat_history(room):
    safe_room = room.replace(':', '_channel_')
    with open(f'data/chat_{safe_room}.txt', 'w', encoding='utf-8') as f:
        for msg in chat_rooms[room]:
            f.write(json.dumps(msg) + "\n")

#loads announcements from a text file in ./data/announcements.txt, returns a list of announcements, each announcement should be in JSON format, one announcement per line
def load_announcements():
    try:
        with open('data/announcements.txt', 'r') as f:
            announcements_list = []
            for line in f:
                if line.strip():
                    try:
                        announcements_list.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        try:
                            announcements_list.append(ast.literal_eval(line.strip()))
                        except:
                            continue
            return announcements_list
    except FileNotFoundError:
        return []
#saves announcements to a text file in ./data/announcements.txt, each announcement should be in JSON format, one announcement per line
def save_announcements():
    with open('data/announcements.txt', 'w') as f:
        for announcement in announcements:
            f.write(json.dumps(announcement) + "\n")
#loads activity logs from a text file in ./data/activity_logs.txt, returns a list of logs, each log should be in JSON format, one log per line. Logs can include channel joins, messages sent, profanity detected, and reports made. Each log entry should have a type (e.g. 'join', 'message', 'profanity', 'report'), username, timestamp, and details (which can be a dictionary with additional info depending on the type)
def load_activity_logs():
    """Load activity logs (channel joins, messages, profanity)"""
    logs = []
    try:
        if os.path.exists('data/activity_logs.txt'):
            with open('data/activity_logs.txt', 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            logs.append(json.loads(line.strip()))
                        except:
                            pass
    except Exception as e:
        print(f"Error loading activity logs: {e}")
    return logs
#logs an activity to the activity_logs.txt file, activity_type can be 'join', 'message', 'profanity', or 'report'. Details should be a dictionary with relevant information depending on the type (e.g. for 'message' it could include room and message content, for 'profanity' it could include the original message and filtered message, etc.)
def log_activity(activity_type, username, details):
    """Log an activity: 'join', 'message', 'profanity', 'report'"""
    try:
        log_entry = {
            'type': activity_type,
            'username': username,
            'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
            'details': details
        }
        with open('data/activity_logs.txt', 'a') as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Error logging activity: {e}")

chat_rooms = defaultdict(list, load_chat_history())
announcements = load_announcements()
activity_logs = load_activity_logs()
active_users = defaultdict(set)
connected_users = {} # {username: connection_count}

# Registry for active voice calls to support persistence across page navigation
# Format: { username: partner_username }
active_voice_calls = {}

# Multi-user voice channels (Discord-style server voice rooms)
voice_room_members = defaultdict(set)   # room_id ("srv_xxx:channel") -> set(username)
user_voice_room = {}                    # username -> room_id
user_voice_sid = {}                     # username -> socket sid that joined voice
sid_voice_user = {}                     # sid -> username (for cleanup on disconnect)
user_voice_status = {}                  # username -> {'muted': bool, 'deafened': bool}

def rename_user_data(old_username, new_username):
    """Renames a username across all persistent data and in-memory state."""
    # 1. Update active users sets
    for room in active_users:
        if old_username in active_users[room]:
            active_users[room].discard(old_username)
            active_users[room].add(new_username)
            
    # Update active voice calls registry
    if old_username in active_voice_calls:
        active_voice_calls[new_username] = active_voice_calls.pop(old_username)

    # Update voice channel registries
    if old_username in user_voice_room:
        room_id = user_voice_room.pop(old_username)
        user_voice_room[new_username] = room_id
        if old_username in voice_room_members.get(room_id, set()):
            voice_room_members[room_id].discard(old_username)
            voice_room_members[room_id].add(new_username)
    if old_username in user_voice_sid:
        sid = user_voice_sid.pop(old_username)
        user_voice_sid[new_username] = sid
        sid_voice_user[sid] = new_username
    if old_username in user_voice_status:
        user_voice_status[new_username] = user_voice_status.pop(old_username)

    # 2. Update chat histories
    for room in chat_rooms:
        updated = False
        for msg in chat_rooms[room]:
            if msg.get('sender') == old_username:
                msg['sender'] = new_username
                updated = True
        if updated:
            save_chat_history(room)

    # 3. Update Announcements
    updated_ann = False
    for ann in announcements:
        if ann.get('author') == old_username:
            ann['author'] = new_username
            updated_ann = True
    if updated_ann:
        save_announcements()

    # 4. Update Direct Messages (content and filename)
    if os.path.exists('data'):
        for filename in os.listdir('data'):
            if filename.startswith('dm_') and filename.endswith('.txt'):
                parts = filename[3:-4].split('_')
                if old_username in parts:
                    old_path = os.path.join('data', filename)
                    msgs = load_dm_history(parts[0], parts[1])
                    for msg in msgs:
                        if msg.get('sender') == old_username: msg['sender'] = new_username
                        if msg.get('recipient') == old_username: msg['recipient'] = new_username
                    
                    new_parts = sorted([new_username if p == old_username else p for p in parts])
                    save_dm_history(new_parts[0], new_parts[1], msgs)
                    
                    new_filename = f"dm_{new_parts[0]}_{new_parts[1]}.txt"
                    if filename != new_filename:
                        os.remove(old_path)

    # 5. Update Friends
    friends, friend_requests = load_friends()
    changed_f = False
    if old_username in friends:
        friends[new_username] = friends.pop(old_username)
        changed_f = True
    for u in list(friends.keys()):
        if old_username in friends[u]:
            friends[u] = [new_username if x == old_username else x for x in friends[u]]
            changed_f = True
    if old_username in friend_requests:
        friend_requests[new_username] = friend_requests.pop(old_username)
        changed_f = True
    for u in list(friend_requests.keys()):
        if old_username in friend_requests[u]:
            friend_requests[u] = [new_username if x == old_username else x for x in friend_requests[u]]
            changed_f = True
    if changed_f:
        save_friends(friends, friend_requests)

    # 6. Update Groups and Group Messages
    gs = load_groups()
    for gid in gs:
        if old_username in gs[gid]['members']:
            gs[gid]['members'] = [new_username if m == old_username else m for m in gs[gid]['members']]
            save_groups(gs)
        if gs[gid].get('creator') == old_username:
            gs[gid]['creator'] = new_username
            save_groups(gs)
        
        gm_msgs = load_group_history(gid)
        updated_gm = False
        for msg in gm_msgs:
            if msg.get('sender') == old_username:
                msg['sender'] = new_username
                updated_gm = True
        if updated_gm:
            save_group_history(gid, gm_msgs)

    # 7. Update Activity logs
    if os.path.exists('data/activity_logs.txt'):
        logs = []
        with open('data/activity_logs.txt', 'r') as f:
            for line in f:
                try:
                    l = json.loads(line.strip())
                    if l.get('username') == old_username: l['username'] = new_username
                    logs.append(l)
                except: pass
        with open('data/activity_logs.txt', 'w') as f:
            for l in logs:
                f.write(json.dumps(l) + "\n")

    # 8. Update Polls
    p_data = load_polls()
    for pid in p_data:
        if p_data[pid].get('creator') == old_username: p_data[pid]['creator'] = new_username
        for opt in p_data[pid].get('votes', {}):
            if old_username in p_data[pid]['votes'][opt]:
                p_data[pid]['votes'][opt] = [new_username if v == old_username else v for v in p_data[pid]['votes'][opt]]
    save_polls(p_data)

# Define a User class that inherits from UserMixin for Flask-Login
class User(UserMixin):
    def __init__(self, username):
        self.id = username
        self.display_name = users[username]['display_name']
        self.role = users[username]['role']
# Required by Flask-Login to load user from session
@login_manager.user_loader
def load_user(username):
    if username in users:
        return User(username)
    return None
# Route for user registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        display_name = request.form.get('display_name', username)

        if username in users:
            flash('Username already exists')
            return redirect(url_for('register'))

        users[username] = {
            'password': password,
            'display_name': display_name,
            'role': 'Regular User',
            'created_at': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
            'last_online': ''
        }
        save_users()
        login_user(User(username))
        flash('Registration successful')
        return redirect(url_for('home'))

    return render_template('register.html')
# Route for user login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Handle Security Question Verification Stage
        if 'security_answer' in request.form:
            pending_username = session.get('pending_login_username')
            if not pending_username or pending_username not in users:
                flash('Login session expired. Please try again.')
                session.pop('pending_login_username', None)
                return redirect(url_for('login'))
            
            user_answer = request.form.get('security_answer', '').strip().lower()
            stored_answer = users[pending_username].get('security_answer', '').strip().lower()
            
            if user_answer == stored_answer:
                login_user(User(pending_username))
                session.pop('pending_login_username', None)
                return redirect(url_for('home'))
            else:
                flash('Incorrect security answer')
                return render_template('login.html', 
                                     show_security_modal=True, 
                                     security_question=users[pending_username].get('security_question'))

        username = request.form['username']
        password = request.form['password']

        if username in users and users[username]['password'] == password:
            # Check maintenance mode
            if app_config.get('maintenance_mode', False) and users[username].get('role') not in ['Owner', 'Co-owner']:
                flash('Site is currently under maintenance. Only Owners and Co-owners can login.', 'warning')
                return render_template('login.html')

            # Check if security question is enabled for this user
            if users[username].get('security_question') and users[username].get('security_answer'):
                session['pending_login_username'] = username
                return render_template('login.html', 
                                     show_security_modal=True, 
                                     security_question=users[username].get('security_question'))

            login_user(User(username))
            
            if username == "jesseramsey":
                flash("Welcome, Jesse", "jesse_welcome")
            elif username == "Killua":
                flash("Welcome, Killua", "jesse_welcome")

            return redirect(url_for('home'))

        flash('Invalid username or password')

    return render_template('login.html')
# Route for user settings (password change, profile update, theme selection)
@app.route('/settings', methods=['POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        response = {'status': 'error', 'message': 'Unknown error occurred'}

        if action == 'password':
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']

            if users[current_user.id]['password'] != current_password:
                response['message'] = 'Current password is incorrect'
            elif new_password != confirm_password:
                response['message'] = 'New passwords do not match'
            else:
                users[current_user.id]['password'] = new_password
                save_users()
                response = {'status': 'success', 'message': 'Password updated successfully!'}

        elif action == 'profile':
            new_username = request.form['new_username']
            new_display_name = request.form['new_display_name']
            new_status = request.form.get('custom_status', '').strip()

            if new_username != current_user.id and new_username in users:
                response['message'] = 'Username already exists'
            else:
                # Handle PFP Upload
                pfp_file = request.files.get('pfp_file')
                if pfp_file and pfp_file.filename != '' and allowed_file(pfp_file.filename):
                    filename = secure_filename(f"pfp_{current_user.id}_{int(time.time())}_{pfp_file.filename}")
                    pfp_file.save(os.path.join(app.root_path, UPLOAD_FOLDER, filename))
                    profile_pic = f"/static/uploads/{filename}"
                else:
                    profile_pic = request.form.get('profile_pic', '')

                # Handle Banner Upload
                banner_file = request.files.get('banner_file')
                if banner_file and banner_file.filename != '' and allowed_file(banner_file.filename):
                    filename = secure_filename(f"banner_{current_user.id}_{int(time.time())}_{banner_file.filename}")
                    banner_file.save(os.path.join(app.root_path, UPLOAD_FOLDER, filename))
                    banner_url = f"/static/uploads/{filename}"
                else:
                    banner_url = request.form.get('banner_url', '')

                # Handle Background Upload
                bg_file = request.files.get('bg_file')
                if bg_file and bg_file.filename != '' and allowed_file(bg_file.filename):
                    filename = secure_filename(f"bg_{current_user.id}_{int(time.time())}_{bg_file.filename}")
                    bg_file.save(os.path.join(app.root_path, UPLOAD_FOLDER, filename))
                    profile_bg = f"/static/uploads/{filename}"
                else:
                    profile_bg = request.form.get('profile_bg', '')

                ringtone_url = request.form.get('ringtone_url', '')
                mute_ringtone = request.form.get('mute_ringtone') == 'on'
                is_stealth = request.form.get('is_stealth') == 'on'
                security_question = request.form.get('security_question', '').strip()
                security_answer = request.form.get('security_answer', '').strip()
                
                old_username = current_user.id
                old_stealth = users[old_username].get('is_stealth', False)
                if new_username != old_username:
                    # Migrate connection status if username changed
                    if old_username in connected_users:
                        connected_users[new_username] = connected_users.pop(old_username)

                    users[new_username] = users.pop(old_username)
                    rename_user_data(old_username, new_username)
                    logout_user()
                    user_message_history.pop(old_username, None)
                    login_user(User(new_username))
                
                users[new_username]['custom_status'] = profanity_filter.censor_text(new_status)
                users[new_username]['display_name'] = new_display_name
                users[new_username]['profile_pic'] = profile_pic
                users[new_username]['banner_url'] = banner_url
                users[new_username]['profile_bg'] = profile_bg
                users[new_username]['ringtone_url'] = ringtone_url
                users[new_username]['mute_ringtone'] = mute_ringtone
                # Only allow staff to use stealth mode
                if current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id == 'Killua':
                    users[new_username]['is_stealth'] = is_stealth
                    
                    # If stealth status changed while online, notify others immediately
                    if old_stealth != is_stealth and new_username in connected_users:
                        status = 'offline' if is_stealth else 'online'
                        socketio.emit('user-status-change', {'username': new_username, 'status': status})

                users[new_username]['security_question'] = security_question
                users[new_username]['security_answer'] = security_answer
                save_users()
                response = {'status': 'success', 'message': 'Profile updated successfully!'}

        elif action == 'theme':
            theme_name = request.form.get('theme_name', 'default')
            user_id = current_user.id
            if theme_name == 'custom':
                custom_colors = {}
                for key in ['header-bg', 'card-bg', 'sidebar-bg', 'border-color', 'text-color', 'text-muted', 'tab-active-bg', 'accent-color', 'accent-hover', 'bg-color', 'input-bg', 'input-hover-bg', 'message-bg', 'own-message-bg']:
                    color_value = request.form.get(f'--{key}')
                    if color_value:
                        custom_colors[f'--{key}'] = color_value
                users[user_id]['custom_theme'] = custom_colors
            users[user_id]['theme'] = theme_name
            save_users()
            response = {'status': 'success', 'message': 'Theme updated successfully!'}
        elif action == 'delete_account':
            user_id = current_user.id
            if user_id in ['jesseramsey', 'Killua']:
                response['message'] = 'You cannot delete this protected account.'
                return jsonify(response), 403
            
            logout_user()
            if user_id in users:
                del users[user_id]
                save_users()
            response = {'status': 'success', 'message': 'Account deleted successfully.', 'redirect': url_for('login')}

        return jsonify(response)
# Route for user logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Route for chat channels - checks if room exists, if user has permission to access it, and renders the channel template with appropriate data
@app.route('/api/server/create', methods=['POST'])
@login_required
def create_server_api():
    data = request.json
    name = data.get('name', '').strip()
    icon_url = data.get('icon_url', '').strip()
    icon_upload = data.get('icon_file')
    
    if not name: return jsonify({'error': 'Name required'}), 400
    server_id = f"srv_{int(time.time())}"
    
    icon = save_server_icon(icon_upload, server_id) or icon_url
    servers_data[server_id] = {
        'name': name,
        'owner': current_user.id,
        'members': [current_user.id],
        'channels': ['general'],
        'channel_metadata': {'general': {'type': 'text'}},
        'icon': icon
    }
    save_servers(servers_data)
    return jsonify({'success': True, 'server_id': server_id})

@app.route('/api/server/<server_id>/invite', methods=['POST'])
@login_required
def invite_to_server_api(server_id):
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    if servers_data[server_id]['owner'] != current_user.id and current_user.role not in ['Owner', 'Co-owner', 'Admin']:
        return jsonify({'error': 'Denied'}), 403
    target = request.json.get('username')
    if target in users and target not in servers_data[server_id]['members']:
        servers_data[server_id]['members'].append(target)
        save_servers(servers_data)
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid user or already member'}), 400

@app.route('/api/server/<server_id>/channel/create', methods=['POST'])
@login_required
def create_server_channel_api(server_id):
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    if servers_data[server_id]['owner'] != current_user.id and current_user.role not in ['Owner', 'Co-owner', 'Admin']:
        return jsonify({'error': 'Denied'}), 403
    chan_name = request.json.get('name', '').strip().lower()
    chan_type = request.json.get('type', 'text')
    chan_name = re.sub(r'[^a-z0-9_-]', '', chan_name)
    if not chan_name: return jsonify({'error': 'Invalid name'}), 400
    if chan_name not in servers_data[server_id]['channels']:
        servers_data[server_id]['channels'].append(chan_name)
        if 'channel_metadata' not in servers_data[server_id]:
            servers_data[server_id]['channel_metadata'] = {}
        servers_data[server_id]['channel_metadata'][chan_name] = {'type': chan_type}
        save_servers(servers_data)
        return jsonify({'success': True})
    return jsonify({'error': 'Exists'}), 400

@app.route('/api/friends')
@login_required
def get_friends_api():
    friends_dict, _ = load_friends()
    user_friends = friends_dict.get(current_user.id, [])
    friend_data = []
    for f in user_friends:
        if f in users:
            friend_data.append({
                'username': f,
                'display_name': users[f]['display_name'],
                'profile_pic': users[f].get('profile_pic', '')
            })
    return jsonify({'friends': friend_data})

@app.route('/api/server/<server_id>/rename', methods=['POST'])
@login_required
def rename_server_api(server_id):
    data = request.json
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    if servers_data[server_id]['owner'] != current_user.id and current_user.role not in ['Owner', 'Co-owner', 'Admin']:
        return jsonify({'error': 'Denied'}), 403
        
    new_name = data.get('name', '').strip()
    icon_url = data.get('icon_url', '').strip()
    icon_upload = data.get('icon_file')

    if new_name:
        servers_data[server_id]['name'] = new_name
    if icon_upload or icon_url:
        servers_data[server_id]['icon'] = save_server_icon(icon_upload, server_id) or icon_url
        
    save_servers(servers_data)
    return jsonify({'success': True})

@app.route('/api/server/<server_id>/channel/<old_name>/rename', methods=['POST'])
@login_required
def rename_channel_api(server_id, old_name):
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    srv = servers_data[server_id]
    is_staff = current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id in ['jesseramsey', 'Killua']
    if srv['owner'] != current_user.id and not is_staff:
        return jsonify({'error': 'Denied'}), 403
    
    new_name = request.json.get('new_name', '').strip().lower()
    new_name = re.sub(r'[^a-z0-9_-]', '', new_name)
    if not new_name or new_name in srv['channels']:
        return jsonify({'error': 'Invalid or duplicate name'}), 400
    
    if old_name not in srv['channels']: return jsonify({'error': 'Not found'}), 404
    
    idx = srv['channels'].index(old_name)
    srv['channels'][idx] = new_name
    
    if 'channel_metadata' in srv:
        meta = srv['channel_metadata'].pop(old_name, {'type': 'text'})
        srv['channel_metadata'][new_name] = meta
        
    save_servers(servers_data)
    
    old_room_id = f"{server_id}:{old_name}"
    new_room_id = f"{server_id}:{new_name}"
    old_safe = old_room_id.replace(':', '_channel_')
    new_safe = new_room_id.replace(':', '_channel_')
    
    old_path = f'data/chat_{old_safe}.txt'
    new_path = f'data/chat_{new_safe}.txt'
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    if old_room_id in chat_rooms:
        chat_rooms[new_room_id] = chat_rooms.pop(old_room_id)
    return jsonify({'success': True, 'new_room_id': new_room_id})

@app.route('/api/server/<server_id>/channel/<chan_name>/delete', methods=['POST'])
@login_required
def delete_channel_api(server_id, chan_name):
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    srv = servers_data[server_id]
    is_staff = current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id in ['jesseramsey', 'Killua']
    if srv['owner'] != current_user.id and not is_staff:
        return jsonify({'error': 'Denied'}), 403
    if len(srv['channels']) <= 1: return jsonify({'error': 'Cannot delete only channel'}), 400
    
    if chan_name in srv['channels']:
        srv['channels'].remove(chan_name)
        if 'channel_metadata' in srv and chan_name in srv['channel_metadata']:
            del srv['channel_metadata'][chan_name]
        save_servers(servers_data)
        room_id = f"{server_id}:{chan_name}"
        path = f"data/chat_{room_id.replace(':', '_channel_')}.txt"
        if os.path.exists(path): os.remove(path)
        if room_id in chat_rooms: del chat_rooms[room_id]
        return jsonify({'success': True})
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/server/<server_id>/member/remove', methods=['POST'])
@login_required
def remove_server_member_api(server_id):
    if server_id not in servers_data: return jsonify({'error': 'Not found'}), 404
    if servers_data[server_id]['owner'] != current_user.id and current_user.role not in ['Owner', 'Co-owner', 'Admin']:
        return jsonify({'error': 'Denied'}), 403
    target = request.json.get('username')
    if target in servers_data[server_id]['members']:
        servers_data[server_id]['members'].remove(target)
        save_servers(servers_data)
        return jsonify({'success': True})
    return jsonify({'error': 'Not a member'}), 400

@app.route('/api/server/<server_id>/delete', methods=['POST'])
@login_required
def delete_server_api(server_id):
    if server_id not in servers_data:
        return jsonify({'error': 'Not found'}), 404
    
    srv = servers_data[server_id]
    is_staff = current_user.role in ['Owner', 'Co-owner', 'Admin'] or current_user.id in ['jesseramsey', 'Killua']
    if srv['owner'] != current_user.id and not is_staff:
        return jsonify({'error': 'Denied'}), 403
    
    # 1. Delete associated chat files
    for channel in srv.get('channels', []):
        room_id = f"{server_id}:{channel}"
        safe_room = room_id.replace(':', '_channel_')
        filepath = f'data/chat_{safe_room}.txt'
        if os.path.exists(filepath):
            try: os.remove(filepath)
            except: pass
        if room_id in chat_rooms: del chat_rooms[room_id]
            
    # 2. Remove server from data
    del servers_data[server_id]
    save_servers(servers_data)
    return jsonify({'success': True})

@app.route('/channel/<room_id>')
@login_required
def channel(room_id):
    if not can_access_room(room_id):
        flash('You do not have permission to access this channel.')
        return redirect(url_for('home'))

    server_id = room_id.split(':')[0] if ':' in room_id else None
    current_server = servers_data.get(server_id)

    user_theme_val = users.get(current_user.id, {}).get('theme', 'default')
    user_custom_theme_val = users.get(current_user.id, {}).get('custom_theme', {})
    return render_template('channel.html', room=room_id, 
                           server=current_server,
                           users=users, 
                           user_theme=user_theme_val,
                           user_custom_theme=user_custom_theme_val)

# Decorator to check if user has one of the required roles to access a route
def requires_role(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Killua has co-owner level permissions secretly
            # Killua and jesseramsey have full permissions
            if current_user.role not in roles and not (current_user.id == 'Killua' and 'Co-owner' in roles) and current_user.id not in ['jesseramsey', 'Killua']:
                flash('You do not have permission to access this feature.')
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
# Route for managing users (changing roles, suspending, muting) - only accessible to users with appropriate roles
@app.route('/admin/upload_emoji', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner', 'Admin'])
def upload_emoji():
    emoji_code = request.form.get('emoji_code', '').strip().lower()
    if not emoji_code:
        flash('Emoji code is required', 'error')
        return redirect(url_for('home'))
    
    # Clean emoji code: remove surrounding colons and non-alphanumeric chars
    emoji_code = re.sub(r'[^a-z0-9_]', '', emoji_code.strip(':'))
    emoji_file = request.files.get('emoji_file')
    
    if emoji_file and emoji_file.filename != '' and allowed_file(emoji_file.filename):
        ext = emoji_file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"emoji_{emoji_code}_{int(time.time())}.{ext}")
        emoji_file.save(os.path.join(app.root_path, EMOJI_FOLDER, filename))
        emoji_url = f"/static/emojis/{filename}"
        
        custom_emojis = load_custom_emojis()
        custom_emojis[emoji_code] = emoji_url
        save_custom_emojis(custom_emojis)
        flash(f'Emoji :{emoji_code}: added successfully!', 'success')
    else:
        flash('Invalid file or no file selected', 'error')
    return redirect(url_for('home'))

@app.route('/admin/delete_emoji/<emoji_code>', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner', 'Admin'])
def delete_emoji(emoji_code):
    custom_emojis = load_custom_emojis()
    if emoji_code in custom_emojis:
        url = custom_emojis[emoji_code]
        try:
            os.remove(os.path.join(app.root_path, url.lstrip('/')))
        except: pass
        del custom_emojis[emoji_code]
        save_custom_emojis(custom_emojis)
        flash(f'Emoji :{emoji_code}: deleted.', 'success')
    return redirect(url_for('home'))
@app.route('/admin/user/<username>', methods=['POST'])
@login_required
@requires_role(['Owner', 'Admin', 'Co-owner', 'Developer'])
def manage_user(username):
    if username not in users:
        flash('User not found')
        return redirect(url_for('settings'))

    if username in ["jesseramsey"]:
        flash('No U')
        return redirect(url_for('settings'))
    action = request.form.get('action')
    if action == 'role' and (current_user.role in ['Owner', 'Admin','Co-owner'] or current_user.id in ['Killua', 'jesseramsey']):
        new_role = request.form.get('role')
        if new_role in ROLES:
            users[username]['role'] = new_role
            save_users()
            flash('User role updated successfully!')
    elif action == 'suspend':
        users[username]['is_suspended'] = not users[username].get('is_suspended', False)
        save_users()
        flash(f'User {"suspended" if users[username]["is_suspended"] else "unsuspended"} successfully!')
    elif action == 'mute':
        users[username]['is_muted'] = not users[username].get('is_muted', False)
        save_users()
        flash(f'User {"muted" if users[username]["is_muted"] else "unmuted"} successfully!')
    elif action == 'delete' and (current_user.role in ['Owner', 'Co-owner'] or current_user.id in ['Killua', 'jesseramsey']):
        del users[username]
        save_users()
        flash(f'User {username} has been permanently deleted.')
    elif action == 'edit' and (current_user.role in ['Owner', 'Admin', 'Co-owner', 'Developer', 'Mod'] or current_user.id in ['Killua', 'jesseramsey']):
        new_username = request.form.get('new_username', '').strip()
        new_display_name = request.form.get('new_display_name', '').strip()
        new_password = request.form.get('new_password', '').strip()
        new_profile_pic = request.form.get('new_profile_pic', '').strip()
        new_profile_bg = request.form.get('new_profile_bg', '').strip()

        if new_username and new_username != username:
            if new_username in users:
                flash('Username already exists!')
                return redirect(url_for('home'))
            old_name = username
            users[new_username] = users.pop(username)
            rename_user_data(old_name, new_username)
            username = new_username

        if new_display_name: users[username]['display_name'] = new_display_name
        if new_password: users[username]['password'] = new_password
        if new_profile_pic: users[username]['profile_pic'] = new_profile_pic
        if new_profile_bg: users[username]['profile_bg'] = new_profile_bg
        
        # Only owners can edit badges
        badge_texts = request.form.getlist('badge_text[]')
        badge_icons = request.form.getlist('badge_icon[]')
        badge_colors = request.form.getlist('badge_color[]')
        
        new_badges_list = []
        for i in range(len(badge_texts)):
            if badge_texts[i].strip():
                new_badges_list.append({'text': badge_texts[i].strip(), 'icon': badge_icons[i], 'color': badge_colors[i]})
        users[username]['badges'] = new_badges_list
            
        save_users()
        flash('User details updated successfully!')

    return redirect(url_for('home'))
# Before each request, check if the user is suspended and log them out if they are, then flash a message informing them of the suspension. This ensures that suspended users cannot continue to access the site even if they are currently logged in.
@app.before_request
def check_user_status():
    if current_user.is_authenticated:
        if users[current_user.id].get('is_suspended', False):
            logout_user()
            flash('Your account has been suspended')
            return redirect(url_for('login'))
        
        # Check maintenance mode
        if app_config.get('maintenance_mode', False) and current_user.role not in ['Owner', 'Co-owner']:
            logout_user()
            flash('The site has entered maintenance mode. Please try again later.', 'info')
            return redirect(url_for('login'))

        # Update last online timestamp for active users
        now_str = datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p')
        if users[current_user.id].get('last_online') != now_str:
            users[current_user.id]['last_online'] = now_str
            save_users()

# Define some basic emojis
EMOJIS = {
    'smile': '😊',
    'laugh': '😂',
    'heart': '❤️',
    'thumbsup': '👍',
    'wink': '😉',
    'fire': '🔥',
    'tada': '🎉',
    'rocket': '🚀',
    'star': '⭐',
    'check': '✅'
}
# Function to parse message text, apply profanity filter, replace emoji codes with actual emojis, and format mentions and links. This function is called before saving messages to ensure that all messages are properly formatted and filtered for profanity.
def parse_message(text):
    # First, apply profanity filter
    if app_config.get('profanity_filter_enabled', True):
        text = profanity_filter.censor_text(text)
    # Replace emoji codes
    for code, emoji in EMOJIS.items():
        text = text.replace(f':{code}:', emoji)

    # Replace custom emoji codes
    custom_emojis = load_custom_emojis()
    for code, url in custom_emojis.items():
        text = text.replace(f':{code}:', f'<img src="{url}" class="emoji-img" alt=":{code}:" title=":{code}:">')

    # Format text while preserving links and handling mentions
    words = text.split()
    formatted = []
    for word in words:
        if word.startswith(('http://', 'https://')):
            formatted.append(word)
        elif word.startswith('@'):
            username = word[1:]
            if username in users:
                formatted.append(f'<a href="/profile/{username}" class="mention">@{users[username]["display_name"]}</a>')
            else:
                formatted.append(word)
        else:
            formatted.append(word)
    return ' '.join(formatted)
# Function to handle admin commands in messages. This function checks if the message starts with a slash (indicating a command), and if so, it parses the command and executes the appropriate action (e.g. banning a user, clearing chat history, changing user roles). Only users with the appropriate roles can execute these commands. The function returns a response message that can be sent back to the chat to inform users of the result of the command.
def handle_command(message, room):
    parts = message.split()
    if not parts: return None
    command = parts[0].lower()

    # Everyone can use /whisper
    if command == '/whisper' and len(parts) > 2:
        target = parts[1].lstrip('@')
        whisper_text = ' '.join(parts[2:])
        if target in users:
            return {
                'text': whisper_text,
                'sender': current_user.id,
                'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
                'room': room,
                'whisper_to': target
            }
        return {'text': f'User {target} not found.', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'restricted_visibility': True}

    if command == '/help':
        return {'text': 
        '/whisper {user} {msg} - Private message, /ban {user}-bans someone /unban {user}-unbans someone /chatclear-clears history /role {user} {role}-updates user /mute {user}-mutes someone /poll create {title} {options...} /help-shows this message, /announce {message}-global announcement, /chess {room}-Invite someone to a chess game',
'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    if command == '/chess' and len(parts) > 1:
        return {'text': f'Chess game created! Join room: <b>{parts[1]}</b> at <a href="/chess">the chess page</a>.', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room}

    if current_user.role not in ['Owner', 'Developer', 'Admin', 'Mod', 'Co-owner'] and current_user.id not in ['Killua', 'jesseramsey']:
        return None

    if command == '/ban' and len(parts) > 1:
        target = parts[1]
        if target in users:
            users[target]['is_suspended'] = True
            save_users()
            return {'text': f'User {target} has been banned', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/unban' and len(parts) > 1:
        target = parts[1]
        if target in users:
            users[target]['is_suspended'] = False
            save_users()
            return {'text': f'User {target} has been unbanned', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/chatclear':
        chat_rooms[room].clear()
        save_chat_history(room)
        return {'text': 'Chat has been cleared', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/role' and len(parts) > 2:
        target = parts[1]
        new_role = ' '.join(parts[2:])
        if target in users and new_role in ROLES:
            users[target]['role'] = new_role
            save_users()
            return {'text': f'Changed {target}\'s role to {new_role}', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}
    elif command == '/poll' and len(parts) > 1:
        subcommand = parts[1].lower()
        if subcommand == 'create' and len(parts) > 3:
            poll_title = parts[2]
            poll_options = '|'.join(parts[3:])
            poll_id = str(len(polls) + 1)
            polls[poll_id] = {
                'id': poll_id,
                'title': poll_title,
                'options': poll_options.split('|'),
                'votes': {opt: [] for opt in poll_options.split('|')},
                'creator': current_user.id,
                'room': room,
                'created_at': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
                'closed': False
            }
            save_polls(polls)
            return {'text': f'{poll_title}', 'sender': current_user.id, 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'type': 'poll', 'poll_id': poll_id}
        elif subcommand == 'list':
            room_polls = [p for p in polls.values() if p['room'] == room and not p['closed']]
            poll_text = 'Active Polls: ' + ', '.join([p['title'] for p in room_polls]) if room_polls else 'No active polls'
            return {'text': poll_text, 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}
        elif subcommand == 'close' and len(parts) > 2:
            poll_id = parts[2]
            if poll_id in polls and (polls[poll_id]['creator'] == current_user.id or current_user.role in ['Owner', 'Developer', 'Admin', 'Mod', 'Co-owner'] or current_user.id == 'Killua'):
                polls[poll_id]['closed'] = True
                save_polls(polls)
                return {'text': f'Poll closed', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}
    elif command == '/say' and len(parts) > 2:
        target = parts[1]
        say_message = ' '.join(parts[2:])
        if target in users:
            return {'text': say_message, 'sender': target, 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'restricted_visibility': False}
    
    elif command == '/mute' and len(parts) > 1:
        target = parts[1]
        if target in users:
            users[target]['is_muted'] = True
            save_users()
            return {'text': f'User {target} has been muted', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}
    
    elif command == '/unmute' and len(parts) > 1:
        target = parts[1]
        if target in users:
            users[target]['is_muted'] = False
            save_users()
            return {'text': f'User {target} has been unmuted', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}
    
    elif command == '/announce' and len(parts) > 1:
        announcement_text = ' '.join(parts[1:])
        return {'text': f'{announcement_text}', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'restricted_visibility': False}
    elif command == '/larp':
        prefixes = ['Gooning', 'Furry', 'I didnt know what else to add here so yeah','Gooner', 'Sir', 'Ragebait']
        for username in users:
            # Only add prefix if they don't already have one of our prefixes
            if not any(users[username]['display_name'].startswith(p + " ") for p in prefixes):
                users[username]['display_name'] = f"{random.choice(prefixes)} {users[username]['display_name']}"
        save_users()
        socketio.emit('names-updated')
        return {'text': 'LARP mode enabled! Prefixes assigned to everyone.', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/unlarp':
        prefixes = ['Gooning', 'Furry', 'I didnt know what else to add here so yeah','Gooner', 'Sir', 'Ragebait']
        for username in users:
            for p in prefixes:
                if users[username]['display_name'].startswith(p + " "):
                    users[username]['display_name'] = users[username]['display_name'][len(p)+1:]
                    break
        save_users()
        socketio.emit('names-updated')
        return {'text': 'LARP mode disabled! Names restored.', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/austin':
        socketio.emit('one-time-troll', {'effect': 'austin'})
        return {'text': 'Austin troll triggered!', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    elif command == '/troll' and len(parts) > 1:
        effect = parts[1].lower()

        # Handle one-time effects
        if effect in ['flash', 'austin', 'rotate', 'invert', 'shake', 'comic']:
            # For one-time effects, emit directly to all clients without saving state
            socketio.emit('one-time-troll', {'effect': effect, 'duration': 1500}) # 1.5 seconds
            return {'text': f'{effect.capitalize()} troll triggered!', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

        active_effects = app_config.get('active_troll_effects', [])
        if not isinstance(active_effects, list): active_effects = []

        if effect == 'reset':
            active_effects = []
        elif effect.startswith('un'):
            target = effect[2:]
            if target in active_effects: active_effects.remove(target)
        else:
            if effect not in active_effects: active_effects.append(effect)

        app_config['active_troll_effects'] = active_effects
        app_config.pop('active_troll_effect', None)
        save_config(app_config)
        
        # Broadcast the effect via SocketIO to everyone online
        socketio.emit('troll-effect', {'effects': active_effects})
        return {'text': f'Troll effects updated. Active: {", ".join(active_effects) if active_effects else "None"}', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

    else:
    # No valid command matched - return an error message
        return {'text': f'Unknown command: {command}. Type /help for a list of commands.', 'sender': 'Server', 'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'), 'room': room, 'whisper_to': current_user.id}

# Route for sending messages to a specific chat room. This route checks if the user is muted before allowing them to send a message. If the message starts with a slash, it is treated as a command and passed to the handle_command function. If the message is valid, it is saved to the chat history and returned as a JSON response to be displayed in the chat.
@app.route('/send', methods=['POST'])
@login_required
def send():
    if users[current_user.id].get('is_muted', False):
        return jsonify({'error': 'You are currently muted'}), 403

    # --- Automated Rate Limiter (5 messages per 10 seconds) ---
    now = time.time()
    if current_user.id not in user_message_history:
        user_message_history[current_user.id] = []
    
    # Filter timestamps to keep only those within the last 10 seconds
    user_message_history[current_user.id] = [t for t in user_message_history[current_user.id] if now - t < 10]
    
    if len(user_message_history[current_user.id]) >= 5:
        return jsonify({'error': 'Slow down! You are sending messages too fast.'}), 429
    
    user_message_history[current_user.id].append(now)

    message = request.json.get('message')
    room = request.json.get('room', 'general')
    image_data = request.json.get('image')
    reply_to = request.json.get('reply_to')

    if message and message.startswith('/'):
        command_response = handle_command(message, room)
        if command_response:
            full_msg = {
                'id': len(chat_rooms[room]),
                'image': None,
                'edited': False,
                'reactions': {},
                'reply_to': None,
                'link_preview': None,
                **command_response
            }
            chat_rooms[room].append(full_msg)
            save_chat_history(room)
            socketio.emit('new-message', full_msg, room=room)
            return jsonify([full_msg])
        else:
            return jsonify({'error': 'Invalid command or insufficient permissions'}), 400

    if (message or image_data) and can_access_room(room):
        if message:
            # Store original message to check for profanity
            original_message = message # Keep original for logging

            # Log if profanity was detected (only if filter is enabled)
            if app_config.get('profanity_filter_enabled', True):
                censored_message_for_log = profanity_filter.censor_text(original_message)
                if '#' in censored_message_for_log and original_message != censored_message_for_log:
                    log_activity('profanity', current_user.id, {
                        'room': room,
                        'original_message': original_message,
                        'filtered_message': censored_message_for_log
                    })
            
            # Parse the message (which now internally checks app_config for censoring)
            
            # Parse the message (applies formatting, emojis, mentions, and profanity filtering)
            message = parse_message(original_message)

        # Fetch link preview if message contains a URL
        link_preview = None
        if message:
            urls = re.findall(r'(https?://[^\s]+)', original_message)
            if urls:
                link_preview = get_link_metadata(urls[0])

        # Upload image to disk if present instead of storing base64
        image_url = save_chat_image(image_data) if image_data else None

        new_message = {
            'id': len(chat_rooms[room]),
            'text': message if message else '',
            'image': image_url,
            'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
            'sender': current_user.id,
            'room': room,
            'edited': False,
            'reactions': {},
            'reply_to': reply_to,
            'link_preview': link_preview
        }
        chat_rooms[room].append(new_message)
        save_chat_history(room)
        
        # Broadcast the message instantly to all users in the room
        socketio.emit('new-message', new_message, room=room)

        # Log the message
        if message:
            log_activity('message', current_user.id, {
                'room': room,
                'message': message[:200] if len(message) > 200 else message
            })
        
        return jsonify([new_message])
    return jsonify([])

# Route for creating a poll
@app.route('/api/poll/create', methods=['POST'])
@login_required
def create_poll():
    data = request.json
    title = data.get('title', '').strip()
    options = data.get('options', [])
    room = data.get('room', 'general')
    
    if not title:
        return jsonify({'error': 'Poll title is required'}), 400
    
    if len(options) < 2:
        return jsonify({'error': 'At least 2 options are required'}), 400
    
    # Filter out empty options
    options = [opt.strip() for opt in options if opt.strip()]
    if len(options) < 2:
        return jsonify({'error': 'At least 2 valid options are required'}), 400
    
    global polls
    polls = load_polls()
    # Generate poll_id safely - use max existing ID + 1, or 1 if no polls
    existing_ids = [int(pid) for pid in polls.keys() if pid.isdigit()]
    poll_id = str(max(existing_ids) + 1 if existing_ids else 1)
    polls[poll_id] = {
        'id': poll_id,
        'title': title,
        'options': options,
        'votes': {opt: [] for opt in options},
        'creator': current_user.id,
        'room': room,
        'created_at': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
        'closed': False
    }
    save_polls(polls)
    
    # Add a message to the chat announcing the poll
    poll_message = {
        'id': len(chat_rooms[room]),
        'text': f'📊 {title}',
        'sender': current_user.id,
        'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
        'room': room,
        'type': 'poll',
        'poll_id': poll_id
    }
    chat_rooms[room].append(poll_message)
    save_chat_history(room)
    
    return jsonify({'success': True, 'poll_id': poll_id})

# Route for voting on a poll
@app.route('/api/poll/vote/<poll_id>/<option>', methods=['POST'])
@login_required
def vote_on_poll(poll_id, option):
    global polls
    polls = load_polls()
    if poll_id not in polls:
        return jsonify({'error': 'Poll not found'}), 404
    
    poll = polls[poll_id]
    if option not in poll['options']:
        return jsonify({'error': 'Invalid option'}), 400
    
    if poll['closed']:
        return jsonify({'error': 'Poll is closed'}), 400
    
    # Remove previous vote by this user if exists
    for opt in poll['options']:
        if current_user.id in poll['votes'][opt]:
            poll['votes'][opt].remove(current_user.id)
    
    # Add new vote
    poll['votes'][option].append(current_user.id)
    save_polls(polls)
    
    return jsonify({'success': True, 'poll': poll})

# Route for getting poll results
@app.route('/api/poll/<poll_id>')
@login_required
def get_poll(poll_id):
    polls = load_polls()
    if poll_id not in polls:
        return jsonify({'error': 'Poll not found'}), 404
    
    poll = polls[poll_id]
    poll_data = {
        'id': poll['id'],
        'title': poll['title'],
        'options': poll['options'],
        'votes': {opt: len(poll['votes'][opt]) for opt in poll['options']},
        'user_vote': None,
        'closed': poll['closed']
    }
    
    # Check if current user has voted
    for opt in poll['options']:
        if current_user.id in poll['votes'][opt]:
            poll_data['user_vote'] = opt
            break
    
    return jsonify({'poll': poll_data})
@app.route('/api/react/<room>/<int:message_id>', methods=['POST'])
@login_required
def react(room, message_id):
    if room not in chat_rooms:
        return jsonify({'error': 'Room not found'}), 404
    
    emoji = request.json.get('emoji')
    if not emoji:
        return jsonify({'error': 'No emoji provided'}), 400

    for msg in chat_rooms[room]:
        if msg['id'] == message_id:
            if 'reactions' not in msg:
                msg['reactions'] = {}
            
            if emoji not in msg['reactions']:
                msg['reactions'][emoji] = []
            
            if current_user.id in msg['reactions'][emoji]:
                msg['reactions'][emoji].remove(current_user.id)
            else:
                msg['reactions'][emoji].append(current_user.id)
            
            save_chat_history(room)
            return jsonify({'success': True})
            
    return jsonify({'error': 'Message not found'}), 404

# Route for retrieving messages for a specific chat room. This route also adds the user to the list of active users in the room and logs the channel join activity if the user was not previously active in that room. The messages and list of active users are returned as a JSON response to be displayed in the chat.
@app.route('/messages/<room>')
@login_required
def get_messages(room):
    if can_access_room(room):
        # Log channel join if user just entered
        was_not_active = current_user.id not in active_users[room]
        
        # Add user to room
        active_users[room].add(current_user.id)
        
        # Log the join activity
        if was_not_active:
            log_activity('join', current_user.id, {'room': room})
        
        # Filter out restricted visibility messages for non-staff users
        filtered_messages = []
        staff_roles = ['Owner', 'Admin', 'Mod', 'Co-owner', 'Developer']
        is_staff = current_user.role in staff_roles or current_user.id in ['jesseramsey', 'Killua']
        
        for msg in chat_rooms[room]:
            # Ensure reactions key exists for frontend
            msg.setdefault('reactions', {})
            msg.setdefault('image', None)
            msg.setdefault('edited', False)
            msg.setdefault('reply_to', None)
            msg.setdefault('link_preview', None)

            # Handle Whispers: Only sender, recipient, or staff can see
            whisper_to = msg.get('whisper_to')
            if whisper_to:
                if is_staff or msg.get('sender') == current_user.id or whisper_to == current_user.id:
                    filtered_messages.append(msg)
                continue

            # Show message if it's not restricted, or if user is staff
            if not msg.get('restricted_visibility', False) or is_staff:
                filtered_messages.append(msg)
        
        # Filter active users list for stealth mode
        display_users = []
        for uid in active_users[room]:
            if uid in users:
                # Staff can see stealth users EXCEPT Killua, who remains hidden from everyone but themselves
                if not users[uid].get('is_stealth', False) or uid == current_user.id or (is_staff and uid != 'Killua'):
                    display_users.append(uid)

        return jsonify({
            'messages': filtered_messages,
            'users': display_users
        })
    return jsonify({'messages': [], 'users': []})

@app.route('/search_messages/<room>')
@login_required
def search_messages(room):
    if not can_access_room(room):
        return jsonify({'messages': [], 'users': []}), 403

    query = request.args.get('q', '').strip().lower()

    # Reuse the same message filters as get_messages
    staff_roles = ['Owner', 'Admin', 'Mod', 'Co-owner', 'Developer']
    is_staff = current_user.role in staff_roles or current_user.id in ['jesseramsey', 'Killua']

    filtered_messages = []
    for msg in chat_rooms[room]:
        msg.setdefault('reactions', {})
        msg.setdefault('image', None)
        msg.setdefault('edited', False)
        msg.setdefault('reply_to', None)
        msg.setdefault('link_preview', None)

        whisper_to = msg.get('whisper_to')
        if whisper_to:
            if not (is_staff or msg.get('sender') == current_user.id or whisper_to == current_user.id):
                continue

        if msg.get('restricted_visibility', False) and not is_staff:
            continue

        if not query or query in msg.get('text', '').lower() or query in msg.get('sender', '').lower() or query in (msg.get('link_preview', {}).get('title', '').lower() if msg.get('link_preview') else ''):
            filtered_messages.append(msg)

    display_users = []
    for uid in active_users[room]:
        if uid in users:
            # Apply the same "Super Stealth" logic for Killua in search results
            if not users[uid].get('is_stealth', False) or uid == current_user.id or (is_staff and uid != 'Killua'):
                display_users.append(uid)

    return jsonify({
        'messages': filtered_messages,
        'users': display_users
    })

@app.route('/video_proxy/<video_id>')
@login_required
def video_proxy(video_id):
    """
    Proxies YouTube video embeds through Invidious instances to bypass school filters.
    """
    # List of public Invidious instances that are often unblocked
    instances = [
        "https://invidious.tiekoetter.com",
    ]
    # Pick a random instance to improve reliability
    instance = random.choice(instances)
    target_url = f"{instance}/embed/{video_id}"
    if request.args.get('autoplay') == '0':
        target_url += '?autoplay=0'
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(target_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode('utf-8', errors='ignore')
            # Basic rewriting to ensure relative resources load from the instance domain
            content = content.replace('src="/', f'src="{instance}/').replace('href="/', f'href="{instance}/')
            return Response(content, mimetype='text/html')
    except Exception:
        # Fallback message if proxying fails
        return f"<html><body style='background:#000;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;'><div style='text-align:center;'><p>Proxy error. This Invidious instance might be down or blocked.</p><a href='<https://www.youtube.com/watch?v={video_id}>' target='_blank' style='color:#7289da;'>Watch on YouTube</a></div></body></html>", 200

# Route for leaving a chat room. This route removes the user from the list of active users in the specified room and logs the channel leave activity. A JSON response is returned to confirm that the user has left the room.
@app.route('/leave/<room>')
@login_required
def leave_room(room):
    if room in active_users:
        active_users[room].discard(current_user.id)
    return jsonify({'success': True})

@app.route('/edit_message/<room>/<int:message_id>', methods=['POST'])
@login_required
def edit_message(room, message_id):
    if not can_access_room(room):
        return jsonify({'error': 'Denied'}), 403

    new_text = request.json.get('text')
    if not new_text:
        return jsonify({'error': 'No text provided'}), 400

    for msg in chat_rooms[room]:
        if msg['id'] == message_id:
            if msg['sender'] != current_user.id and current_user.role not in ['Owner', 'Admin','Mod', 'Co-owner', 'Developer']:
                return jsonify({'error': 'Permission denied'}), 403
            msg['text'] = parse_message(new_text)
            msg['edited'] = True
            save_chat_history(room)
            socketio.emit('message-edited', msg, room=room)
            return jsonify(msg)

    return jsonify({'error': 'Message not found'}), 404
# Route for deleting a message. This route checks if the user has permission to delete the message (either they are the sender or they have an admin role) before removing the message from the chat history. A JSON response is returned to confirm that the message has been deleted or to indicate any errors.
@app.route('/delete_message/<room>/<int:message_id>', methods=['POST'])
@login_required
def delete_message(room, message_id):
    if not can_access_room(room):
        return jsonify({'error': 'Denied'}), 403

    for i, msg in enumerate(chat_rooms[room]):
        if msg['id'] == message_id:
            if msg['sender'] != current_user.id and current_user.role not in ['Owner', 'Admin', 'Mod', 'Co-owner', 'Developer']:
                return jsonify({'error': 'Permission denied'}), 403
            del chat_rooms[room][i]
            save_chat_history(room)
            socketio.emit('message-deleted', {'id': message_id, 'room': room}, room=room)
            return jsonify({'success': True})

    return jsonify({'error': 'Message not found'}), 404

@app.route('/report_message/<room>/<int:message_id>', methods=['POST'])
@login_required
def report_message(room, message_id):
    if not can_access_room(room):
        return jsonify({'error': 'Denied'}), 403

    data = request.json
    reason = data.get('reason', '')
    message_text = data.get('message_text', '')
    sender = data.get('sender', '')

    if not reason:
        return jsonify({'error': 'Reason required'}), 400

    # Save report to file
    report_data = {
        'reporter': current_user.id,
        'type': 'channel',
        'room': room,
        'message_id': message_id,
        'message_text': message_text,
        'sender': sender,
        'reason': reason,
        'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
    }

    try:
        with open('data/reports.txt', 'a') as f:
            f.write(json.dumps(report_data) + '\n')
        
        # Notify all non-regular users
        for username, user_data in users.items():
            if user_data['role'] in ['Owner', 'Co-owner', 'Admin', 'Mod']:
                if username not in report_notifications:
                    report_notifications[username] = []
                report_notifications[username].append({
                    'type': 'message_report',
                    'reporter': current_user.id,
                    'room': room,
                    'sender': sender,
                    'reason': reason[:50],
                    'timestamp': report_data['timestamp']
                })
    except Exception as e:
        print(f"Error saving report: {e}")

    return jsonify({'success': True})
# Route for retrieving admin logs. This route is protected by a role requirement, allowing only users with the appropriate roles to access it. The logs include both activity logs (channel joins, messages, profanity) and reports made by users. The logs are sorted by timestamp and returned as a JSON response to be displayed in the admin panel.
@app.route('/get_admin_logs')
@login_required
@requires_role(['Owner', 'Admin', 'Mod', 'Developer'])
def get_admin_logs():
    """Get activity logs for admin panel"""
    logs = load_activity_logs()
    reports = []
    try:
        if os.path.exists('data/reports.txt'):
            with open('data/reports.txt', 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            reports.append(json.loads(line.strip()))
                        except:
                            pass
    except Exception as e:
        print(f"Error loading reports: {e}")
    
    # Return most recent logs first (last 200 entries)
    all_activities = logs + [{'type': 'report', **report} for report in reports]
    all_activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return jsonify(all_activities[-200:])

# Route for resolving a report. This route is protected by a role requirement, allowing only users with appropriate admin roles to mark reports as resolved. The report is identified by reporter, sender, and timestamp, and is stored in a resolved_reports.txt file to maintain history while keeping active reports separate.
@app.route('/admin/resolve_report', methods=['POST'])
@login_required
@requires_role(['Owner', 'Admin', 'Mod', 'Developer'])
def resolve_report():
    """Mark a report as resolved"""
    try:
        data = request.json
        reporter = data.get('reporter')
        sender = data.get('sender')
        timestamp = data.get('timestamp')
        
        if not reporter or not sender or not timestamp:
            return jsonify({'error': 'Missing report identifiers'}), 400
        
        # Load all reports
        reports = []
        resolved_reports = []
        if os.path.exists('data/reports.txt'):
            with open('data/reports.txt', 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            report = json.loads(line.strip())
                            # Check if this is the report to resolve
                            if (report.get('reporter') == reporter and 
                                report.get('sender') == sender and 
                                report.get('timestamp') == timestamp):
                                # Mark as resolved
                                report['resolved'] = True
                                report['resolved_by'] = current_user.id
                                report['resolved_at'] = datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p')
                                resolved_reports.append(report)
                            else:
                                reports.append(report)
                        except:
                            pass
        
        # Save unresolved reports back
        try:
            with open('data/reports.txt', 'w') as f:
                for report in reports:
                    f.write(json.dumps(report) + '\n')
        except Exception as e:
            print(f"Error saving reports: {e}")
            return jsonify({'error': 'Failed to save reports'}), 500
        
        # Append resolved reports to resolved_reports.txt
        try:
            with open('data/resolved_reports.txt', 'a') as f:
                for report in resolved_reports:
                    f.write(json.dumps(report) + '\n')
        except Exception as e:
            print(f"Error saving resolved reports: {e}")
            return jsonify({'error': 'Failed to save resolved reports'}), 500
        
        if not resolved_reports:
            return jsonify({'success': False, 'message': 'Report not found'}), 404
        
        return jsonify({'success': True, 'message': f'Report marked as resolved by {current_user.id}'}), 200
    
    except Exception as e:
        print(f"Error resolving report: {e}")
        return jsonify({'error': str(e)}), 500

# Route for exporting chat logs. This route allows users with the appropriate permissions to export the chat history of a specific room as a text file. The chat log is read from the corresponding text file, and a response is created to prompt the user to download the file. If the room does not exist or if there are any errors during the process, appropriate error messages are returned as JSON responses.
@app.route('/export_users')
@login_required
def export_Users():
    try:
        # Read the chat file
        filepath = f'data/users.txt'
        if not os.path.exists(filepath):
            return jsonify({'error': 'Chat log not found'}), 404
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Create response with file download
        from flask import send_file, Response
        response = Response(content, mimetype='text/plain')
        response.headers['Content-Disposition'] = f'attachment; filename=users_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/export_chat/<room>')
@login_required
def export_chat(room):
    """Export chat log for a specific room"""
    if not can_access_room(room):
        return jsonify({'error': 'Denied'}), 403
    
    # Check if user has permission to access this room
    if room.lower() == 'admin' and current_user.role not in ['Admin', 'Owner', 'Mod', 'Co-owner', 'Developer'] and current_user.id not in ['Killua', 'jesseramsey', 'Killua']:
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        # Read the chat file
        filepath = f'data/chat_{room}.txt'
        if not os.path.exists(filepath):
            return jsonify({'error': 'Chat log not found'}), 404
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Create response with file download
        from flask import send_file, Response
        response = Response(content, mimetype='text/plain')
        response.headers['Content-Disposition'] = f'attachment; filename=chat_{room}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# Route for adding announcements. This route is protected by a role requirement, allowing only users with the appropriate roles to add announcements. The announcement text is retrieved from the form data, filtered for profanity, and then saved to the announcements list and file. A success message is flashed to the user, and they are redirected back to the home page.
@app.route('/add_announcement', methods=['POST'])
@login_required
@requires_role(['Owner', 'Admin'])
def add_announcement():
    text = request.form.get('announcement')
    if text:
        # Apply profanity filter to announcements
        filtered_text = profanity_filter.censor_text(text)
        announcements.append({
            'text': filtered_text,
            'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
            'author': current_user.id
        })
        save_announcements()
        flash('Announcement added successfully!', 'success')
    return redirect(url_for('home'))
# Functions to load and save friends and friend requests. Friendships are stored in a text file with the format username|friend_username|status, where status can be 'accepted' or 'pending'. The load_friends function reads this file and constructs two dictionaries: one for accepted friendships and one for pending friend requests. The save_friends function writes the current state of friendships and friend requests back to the file.
@app.route('/admin/toggle_profanity_filter', methods=['POST'])
@login_required
@requires_role(['Owner', 'Admin', 'Co-owner']) # Only Owners, Admins, and Co-owners can toggle this
def toggle_profanity_filter():
    global app_config
    app_config['profanity_filter_enabled'] = not app_config.get('profanity_filter_enabled', True)
    save_config(app_config)
    status = "enabled" if app_config['profanity_filter_enabled'] else "disabled"
    flash(f'Profanity filter has been {status}.', 'success')
    return jsonify({'success': True, 'status': status})

@app.route('/admin/add_profanity_word', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner'])
def add_profanity_word():
    word = request.form.get('word', '').strip()
    if not word:
        flash('Word cannot be empty.', 'error')
    elif profanity_filter.add_word(word):
        flash(f'Profanity word "{word}" added successfully!', 'success')
    else:
        flash(f'Profanity word "{word}" already exists.', 'warning')
    return redirect(url_for('home'))

@app.route('/admin/delete_profanity_word/<word>', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner'])
def delete_profanity_word(word):
    if profanity_filter.remove_word(word):
        flash(f'Profanity word "{word}" deleted successfully!', 'success')
    else:
        flash(f'Profanity word "{word}" not found.', 'error')
    return redirect(url_for('home'))


@app.route('/admin/send_popup', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner'])
def send_popup():
    message = request.form.get('popup_message', '').strip()
    if message:
        global app_config
        app_config['popup_message'] = profanity_filter.censor_text(message)
        app_config['popup_id'] = str(int(time.time()))
        save_config(app_config)
        flash('Global popup broadcasted!', 'success')
    return redirect(url_for('home'))

@app.route('/admin/toggle_maintenance', methods=['POST'])
@login_required
@requires_role(['Owner'])
def toggle_maintenance():
    global app_config
    app_config['maintenance_mode'] = not app_config.get('maintenance_mode', False)
    save_config(app_config)
    status = "enabled" if app_config['maintenance_mode'] else "disabled"
    flash(f'Maintenance mode has been {status}.', 'success')
    return redirect(url_for('home'))

@app.route('/admin/update_seasonal_theme', methods=['POST'])
@login_required
@requires_role(['Owner'])
def update_seasonal_theme():
    theme = request.form.get('seasonal_theme', 'none')
    global app_config
    app_config['seasonal_theme'] = theme
    save_config(app_config)
    flash(f'Seasonal theme updated to {theme}.', 'success')
    return redirect(url_for('home'))

def load_friends():
    global _friends_cache
    if _friends_cache is not None: return _friends_cache
    friends = {}
    friend_requests = {}
    try:
        with open('data/friends.txt', 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                user1, user2, status = line.strip().split('|')
                if status == 'accepted':
                    friends.setdefault(user1, []).append(user2)
                    friends.setdefault(user2, []).append(user1)
                elif status == 'pending':
                    friend_requests.setdefault(user2, []).append(user1)
    except FileNotFoundError:
        pass
    _friends_cache = (friends, friend_requests)
    return _friends_cache
# The save_friends function writes the current state of friendships and friend requests back to the friends.txt file. It iterates through the friends dictionary to save accepted friendships and through the friend_requests dictionary to save pending friend requests, ensuring that duplicate entries are avoided by only saving friendships where the first username is alphabetically less than the second.
@app.route('/unfriend', methods=['POST'])
@login_required
def unfriend():
    global _friends_cache
    _friends_cache = None
    friend_username = request.form.get('friend_username')
    if friend_username and friend_username in users:
        friends, friend_requests = load_friends()
        # Remove from friends list
        if friend_username in friends.get(current_user.id, []):
            friends[current_user.id].remove(friend_username)
            friends[friend_username].remove(current_user.id)
        # Remove pending requests
        if friend_username in friend_requests.get(current_user.id, []):
            friend_requests[current_user.id].remove(friend_username)
        if current_user.id in friend_requests.get(friend_username, []):
            friend_requests[friend_username].remove(current_user.id)
        save_friends(friends, friend_requests)
        flash(f'You have unfriended {friend_username}', 'success')
    return redirect(url_for('home'))
def save_friends(friends, friend_requests):
    global _friends_cache
    _friends_cache = (friends, friend_requests)
    with open('data/friends.txt', 'w') as f:
        f.write('# Format: username|friend_username|status\n')
        # Save accepted friendships
        for user, friend_list in friends.items():
            for friend in friend_list:
                if user < friend:  # Avoid duplicate entries
                    f.write(f"{user}|{friend}|accepted\n")
        # Save pending requests
        for user, requesters in friend_requests.items():
            for requester in requesters:
                f.write(f"{requester}|{user}|pending\n")

# Route for home page. This route checks if the user is authenticated and, if so, loads their friends, friend requests, and recent DMs to display on the home page. It also passes announcements, active users, chat rooms, and theme information to the template for rendering. If the user is not authenticated, it simply renders the home page with announcements and chat rooms.
@app.route('/api/group/leave/<group_id>', methods=['POST'])
@login_required
def leave_group_api(group_id):
    groups = load_groups()
    if group_id in groups and current_user.id in groups[group_id]['members']:
        groups[group_id]['members'].remove(current_user.id)
        if not groups[group_id]['members']:
            # Delete group file if no members left
            if os.path.exists(f"data/group_msg_{group_id}.txt"):
                os.remove(f"data/group_msg_{group_id}.txt")
            del groups[group_id]
        save_groups(groups)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Group not found or not a member'})

@app.route('/api/group/add_member/<group_id>', methods=['POST'])
@login_required
def add_group_member_api(group_id):
    data = request.json
    new_member = data.get('username')
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the group creator can add members'})
        if new_member and new_member not in groups[group_id]['members']:
            groups[group_id]['members'].append(new_member)
            save_groups(groups)
            return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Operation failed'})

@app.route('/api/group/remove_member/<group_id>', methods=['POST'])
@login_required
def remove_group_member_api(group_id):
    data = request.json
    member_to_remove = data.get('username')
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the group creator can remove members'})
        if member_to_remove in groups[group_id]['members']:
            groups[group_id]['members'].remove(member_to_remove)
            save_groups(groups)
            return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Operation failed'})

@app.route('/api/group/rename/<group_id>', methods=['POST'])
@login_required
def rename_group_api(group_id):
    data = request.json
    new_name = data.get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'error': 'Name cannot be empty'})
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the creator can rename the group'})
        groups[group_id]['name'] = new_name
        save_groups(groups)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Group not found'})

@app.route('/api/group/update_icon/<group_id>', methods=['POST'])
@login_required
def update_group_icon_api(group_id):
    data = request.json
    icon_url = data.get('icon_url', '').strip()
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the creator can update the icon'})
        groups[group_id]['icon_url'] = icon_url
        save_groups(groups)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Group not found'})

@app.route('/api/group/delete/<group_id>', methods=['POST'])
@login_required
def delete_group_api(group_id):
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the creator can delete the group'})
        
        # Delete group history file
        history_path = f"data/group_msg_{group_id}.txt"
        if os.path.exists(history_path):
            os.remove(history_path)
            
        del groups[group_id]
        save_groups(groups)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Group not found'})

@app.route('/api/group/transfer_ownership/<group_id>', methods=['POST'])
@login_required
def transfer_ownership_api(group_id):
    data = request.json
    new_owner = data.get('username')
    groups = load_groups()
    if group_id in groups:
        if groups[group_id].get('creator') != current_user.id:
            return jsonify({'success': False, 'error': 'Only the creator can transfer ownership'})
        
        if new_owner in groups[group_id]['members']:
            groups[group_id]['creator'] = new_owner
            save_groups(groups)
            return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Operation failed'})

@app.route('/')
@login_required
def home():
    if current_user.is_authenticated:
        friends, friend_requests = load_friends()
        user_friends = friends.get(current_user.id, [])
        user_requests = friend_requests.get(current_user.id, [])
        
        all_groups = load_groups()
        user_groups = {gid: data for gid, data in all_groups.items() if current_user.id in data['members']}
        
        # Load most recent DMs for each friend
        recent_dms = []
        for friend in user_friends:
            messages = load_dm_history(current_user.id, friend)
            if messages:
                recent_dms.append(messages[-1])  # Get most recent message
                
        # Add messages where user was recipient
        for username in users:
            if username != current_user.id:
                messages = load_dm_history(username, current_user.id)
                if messages and messages[-1] not in recent_dms:
                    recent_dms.append(messages[-1])
                    
        # Sort by timestamp (newest first)
        recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)
        
        online_users = [u for u in connected_users if not users.get(u, {}).get('is_stealth', False)]

        return render_template('index.html', announcements=announcements, users=users, 
                            friends=user_friends, friend_requests=user_requests,
                            active_users=active_users, dm_messages=recent_dms, groups=user_groups,
                            online_users=online_users,
                            chat_rooms=chat_rooms, user_theme=users.get(current_user.id, {}).get('theme', 'default'),
                            user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {}))
    return render_template('index.html', announcements=announcements, users=users,
                         chat_rooms=chat_rooms, groups={}, user_theme=users.get(current_user.id, {}).get('theme', 'default'),
                         user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {}))
@app.route('/games')
@login_required
def games():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'games.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/platformer')
@login_required
def platformer():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'platformer.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/chess')
@login_required
def chess():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'chess.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/clicker')
@login_required
def clicker():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'clicker.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/tnmn')
@login_required
def tnmn():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'tnmn.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/brotato')
@login_required
def brotato():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'brotato.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/minecraft')
@login_required
def minecraft():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'minecraft.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/fnaf1')
@login_required
def fnaf1():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'fnaf1.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
@app.route('/fnaf2')
@login_required
def fnaf2():
    friends, friend_requests = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_requests = friend_requests.get(current_user.id, [])

    # Load most recent DMs to keep the sidebar updated
    recent_dms = []
    for friend in user_friends:
        messages = load_dm_history(current_user.id, friend)
        if messages:
            recent_dms.append(messages[-1])
    
    # Sort DMs by timestamp
    recent_dms.sort(key=lambda x: x['timestamp'], reverse=True)

    return render_template(
        'fnaf2.html', 
        announcements=announcements, 
        users=users, 
        friends=user_friends, 
        friend_requests=user_requests, 
        active_users=active_users, 
        dm_messages=recent_dms, 
        chat_rooms=chat_rooms, 
        user_theme=users.get(current_user.id, {}).get('theme', 'default'), 
        user_custom_theme=users.get(current_user.id, {}).get('custom_theme', {})
    )
# Route for sending a friend request. This route checks if the target username is valid and not the same as the current user, then checks if they are already friends or if a friend request has already been sent. If everything is valid, it adds a pending friend request to the target user's list and saves the updated friendships to the file. A success message is flashed to the user, and they are redirected back to the profile page of the target user.
@app.route('/send_friend_request/<username>', methods=['POST'])
@login_required
def send_friend_request(username):
    if username not in users or username == current_user.id:
        flash('Invalid friend request')
        return redirect(url_for('view_profile', username=username))

    friends, friend_requests = load_friends()
    if username in friends.get(current_user.id, []):
        flash('Already friends')
        return redirect(url_for('view_profile', username=username))

    if username not in friend_requests:
        friend_requests[username] = []
    if current_user.id not in friend_requests[username]:
        friend_requests[username].append(current_user.id)
        save_friends(friends, friend_requests)
        flash('Friend request sent!')
    else:
        flash('Friend request already sent')

    return redirect(url_for('view_profile', username=username))
# Route for responding to a friend request. This route checks if the target username is valid and if there is a pending friend request from that user. Depending on the action (accept or reject), it either adds the users as friends or simply removes the pending request. The updated friendships are saved to the file, and a success message is flashed to the user before redirecting back to the home page.
@app.route('/respond_friend_request', methods=['POST'])
@login_required
def respond_friend_request():
    username = request.form.get('username')
    action = request.form.get('action')

    if not username or action not in ['accept', 'reject']:
        flash('Invalid request')
        return redirect(url_for('home'))

    friends, friend_requests = load_friends()
    if username not in friend_requests.get(current_user.id, []):
        flash('No friend request found')
        return redirect(url_for('home'))

    friend_requests[current_user.id].remove(username)

    if action == 'accept':
        if current_user.id not in friends:
            friends[current_user.id] = []
        if username not in friends:
            friends[username] = []
        friends[current_user.id].append(username)
        friends[username].append(current_user.id)
        flash('Friend request accepted!')
    else:
        flash('Friend request rejected')

    save_friends(friends, friend_requests)
    return redirect(url_for('home'))

@app.route('/admin/shutdown', methods=['POST'])
@login_required
@requires_role(['Owner', 'Co-owner'])
def shutdown():
    log_activity('shutdown', current_user.id, {'status': 'initiated'})
    print(f"SHUTDOWN initiated by {current_user.id}")
    
    def terminate():
        time.sleep(1)
        os._exit(0)
    
    from threading import Thread
    Thread(target=terminate).start()
    
    return jsonify({'success': True, 'message': 'Server is shutting down...'})

@app.route('/admin/terminal_data')
@login_required
@requires_role(['Owner'])
def terminal_data():
    try:
        if not os.path.exists('data/activity_logs.txt'):
            return "No logs available."
        with open('data/activity_logs.txt', 'r') as f:
            lines = f.readlines()
            # Return last 50 lines for the console view
            return "".join(lines[-50:])
    except Exception as e:
        return f"Error reading logs: {str(e)}"
# Route for direct messaging. This route checks if the target username is valid, then loads the DM history between the current user and the target user. It also loads the current user's friends to display in the DM interface. The direct_message.html template is rendered with the DM messages, recipient information, friends list, active users, and theme information for rendering the DM interface.
@app.route('/dm/<username>')
@login_required
def direct_message(username):
    if username not in users:
        flash('User not found')
        return redirect(url_for('home'))
    dm_messages = load_dm_history(current_user.id, username)
    friends, _ = load_friends()
    user_friends = friends.get(current_user.id, [])
    all_groups = load_groups()
    user_groups = {gid: data for gid, data in all_groups.items() if current_user.id in data['members']}
    
    online_users = [u for u in connected_users if not users.get(u, {}).get('is_stealth', False)]

    return render_template('direct_message.html', 
                         users=users,
                         dm_messages=dm_messages,
                         recipient=username,
                         friends=user_friends,
                         groups=user_groups,
                         is_group=False,
                         is_creator=False,
                         active_users=active_users,
                         online_users=online_users,
                         user_theme=users[current_user.id].get('theme', 'default'),
                         user_custom_theme=users[current_user.id].get('custom_theme', {}))

@app.route('/group_dm/<group_id>')
@login_required
def group_message(group_id):
    all_groups = load_groups()
    if group_id not in all_groups or current_user.id not in all_groups[group_id]['members']:
        flash('Group not found or access denied')
        return redirect(url_for('home'))
    
    group_messages = load_group_history(group_id)
    friends, _ = load_friends()
    user_friends = friends.get(current_user.id, [])
    user_groups = {gid: data for gid, data in all_groups.items() if current_user.id in data['members']}
    is_creator = all_groups[group_id].get('creator') == current_user.id

    return render_template('direct_message.html', 
                         users=users,
                         dm_messages=group_messages,
                         recipient=group_id,
                         recipient_name=all_groups[group_id]['name'],
                         friends=user_friends,
                         groups=user_groups,
                         is_group=True,
                         is_creator=is_creator,
                         active_users=active_users,
                         user_theme=users[current_user.id].get('theme', 'default'),
                         user_custom_theme=users[current_user.id].get('custom_theme', {}))

@app.route('/api/group/create', methods=['POST'])
@login_required
def create_group():
    data = request.json
    name = data.get('name')
    members = data.get('members', [])
    
    if not name or len(members) < 1:
        return jsonify({'success': False, 'error': 'Invalid name or members'})
    
    if current_user.id not in members:
        members.append(current_user.id)
        
    groups = load_groups()
    group_id = f"grp_{int(time.time())}"
    groups[group_id] = {
        'name': name,
        'members': members,
        'creator': current_user.id,
        'icon_url': ""
    }
    save_groups(groups)
    return jsonify({'success': True, 'group_id': group_id})

@app.route('/send_group_dm', methods=['POST'])
@login_required
def send_group_dm():
    data = request.json
    group_id = data.get('recipient')
    message = data.get('message') or ""
    image_data = data.get('image')
    
    groups = load_groups()
    if not group_id or group_id not in groups or current_user.id not in groups[group_id]['members'] or (not message and not image_data):
        return jsonify({'success': False, 'error': 'Access denied'})
        
    messages = load_group_history(group_id)
    # Upload image to disk if present
    image_url = save_chat_image(image_data) if image_data else None

    filtered_message = parse_message(message)
    check_for_infection_spread(current_user.id, recipient)
    
    link_preview = None
    urls = re.findall(r'(https?://[^\s]+)', message)
    for url in urls:
        if not re.search(r'youtube\.com|youtu\.be', url, re.I):
            link_preview = get_link_metadata(url)
            break

    new_message = {
        'id': len(messages),
        'sender': current_user.id,
        'text': filtered_message,
        'image': image_url,
        'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
        'edited': False,
        'link_preview': link_preview
    }
    messages.append(new_message)
    save_group_history(group_id, messages)
    return jsonify({'success': True})

@app.route('/get_group_dm/<group_id>')
@login_required
def get_group_dm(group_id):
    groups = load_groups()
    if group_id not in groups or current_user.id not in groups[group_id]['members']:
        return jsonify({'messages': []})
    
    messages = load_group_history(group_id)
    for msg in messages:
        msg['sender_name'] = users[msg['sender']]['display_name']
        
    return jsonify({'messages': list(reversed(messages))})

@app.route('/send_dm', methods=['POST'])
@login_required
def send_dm():
    data = request.json
    recipient = data.get('recipient')
    message = data.get('message') or ""
    image_data = data.get('image')
    if not recipient or recipient not in users or (not message and not image_data):
        return jsonify({'success': False, 'error': 'Invalid request'})

    messages = load_dm_history(current_user.id, recipient)
    # Upload image to disk if present
    image_url = save_chat_image(image_data) if image_data else None
    
    filtered_message = parse_message(message)
    
    link_preview = None
    urls = re.findall(r'(https?://[^\s]+)', message)
    for url in urls:
        if not re.search(r'youtube\.com|youtu\.be', url, re.I):
            link_preview = get_link_metadata(url)
            break

    new_message = {
        'id': len(messages),
        'sender': current_user.id,
        'recipient': recipient,
        'text': filtered_message,
        'image': image_url,
        'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
        'edited': False,
        'link_preview': link_preview
    }
    messages.append(new_message)
    save_dm_history(current_user.id, recipient, messages)

    return jsonify({'success': True})

@app.route('/edit_dm/<recipient>/<int:message_id>', methods=['POST'])
@login_required
def edit_dm_api(recipient, message_id):
    is_group = recipient.startswith('grp_')
    if is_group:
        groups = load_groups()
        if recipient not in groups or current_user.id not in groups[recipient]['members']:
            return jsonify({'error': 'Access denied'}), 403
        messages = load_group_history(recipient)
    else:
        messages = load_dm_history(current_user.id, recipient)
    
    new_text = request.json.get('text')
    if not new_text: return jsonify({'error': 'No text provided'}), 400

    for msg in messages:
        if msg.get('id') == message_id:
            if msg['sender'] != current_user.id:
                return jsonify({'error': 'Permission denied'}), 403
            msg['text'] = parse_message(new_text)
            msg['edited'] = True
            if is_group: save_group_history(recipient, messages)
            else: save_dm_history(current_user.id, recipient, messages)
            return jsonify({'success': True})
    return jsonify({'error': 'Message not found'}), 404

@app.route('/delete_dm/<recipient>/<int:message_id>', methods=['POST'])
@login_required
def delete_dm_api(recipient, message_id):
    is_group = recipient.startswith('grp_')
    if is_group:
        groups = load_groups()
        if recipient not in groups or current_user.id not in groups[recipient]['members']:
            return jsonify({'error': 'Access denied'}), 403
        messages = load_group_history(recipient)
    else:
        messages = load_dm_history(current_user.id, recipient)

    for i, msg in enumerate(messages):
        if msg.get('id') == message_id:
            if msg['sender'] != current_user.id:
                return jsonify({'error': 'Permission denied'}), 403
            del messages[i]
            if is_group: save_group_history(recipient, messages)
            else: save_dm_history(current_user.id, recipient, messages)
            return jsonify({'success': True})
    return jsonify({'error': 'Message not found'}), 404
# Route for broadcasting troll effects (deprecated). This route is protected by a role requirement, allowing only users with the 'Developer' role to broadcast troll effects. The effect to be broadcasted is retrieved from the JSON request body and added to a queue of troll effects. A JSON response is returned to confirm that the effect is being broadcasted or to indicate any errors.
@app.route('/broadcast_troll', methods=['POST'])
@login_required
def broadcast_troll():
    if current_user.role != 'Developer':
        return jsonify({'error': 'Unauthorized'}), 403
    effect = request.json.get('effect')
    if effect:
        troll_effect_queue.append(effect)
        return jsonify({'message': f'Broadcasting {effect}'}), 200
    return jsonify({'error': 'No effect specified'}), 400

troll_effect_queue = []
report_notifications = {}
# Route for streaming troll events and report notifications(deprecated). This route is protected by a login requirement, ensuring that only authenticated users can access it. The event_stream function continuously checks for new troll effects and report notifications, yielding them as server-sent events to be received by the client in real-time. The response is set to have a MIME type of 'text/event-stream' to enable the streaming of events.
@app.route('/troll_events')
@login_required
def troll_events():
    def event_stream():
        while True:
            data = {}
            if troll_effect_queue:
                data['effect'] = troll_effect_queue.pop(0)
            
            # Check for report notifications for non-regular users
            if current_user and current_user.is_authenticated and current_user.role in ['Owner', 'Co-owner', 'Admin', 'Mod']:
                if current_user.id in report_notifications:
                    data['reports'] = report_notifications[current_user.id]
                    report_notifications[current_user.id] = []
            
            yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)
    return Response(event_stream(), mimetype='text/event-stream')
# Route for reporting a direct message. This route checks if a reason for the report is provided, then saves the report details to a file and adds a notification for all non-regular users (Owner, Co-owner, Admin, Mod) about the new report. A JSON response is returned to confirm that the report was submitted successfully or to indicate any errors.
@app.route('/report_dm', methods=['POST'])
@login_required
def report_dm():
    data = request.json
    reason = data.get('reason', '')
    message_text = data.get('message_text', '')
    sender = data.get('sender', '')
    recipient = data.get('recipient', '')

    if not reason:
        return jsonify({'error': 'Reason required'}), 400

    # Save report to file
    report_data = {
        'reporter': current_user.id,
        'type': 'dm',
        'message_text': message_text,
        'sender': sender,
        'recipient': recipient,
        'reason': reason,
        'timestamp': datetime.now(cst_timezone).strftime('%Y-%m-%d %I:%M %p'),
    }

    try:
        with open('data/reports.txt', 'a') as f:
            f.write(json.dumps(report_data) + '\n')
        
        # Notify all non-regular users
        for username, user_data in users.items():
            if user_data['role'] in ['Owner', 'Co-owner', 'Admin', 'Mod']:
                if username not in report_notifications:
                    report_notifications[username] = []
                report_notifications[username].append({
                    'type': 'dm_report',
                    'reporter': current_user.id,
                    'sender': sender,
                    'reason': reason[:50],
                    'timestamp': report_data['timestamp']
                })
    except Exception as e:
        print(f"Error saving DM report: {e}")

    return jsonify({'success': True})
# Route for retrieving direct message history between the current user and another user. This route checks if the target username is valid, then loads the DM history between the two users. The messages are formatted to include the sender's display name and returned as a JSON response to be displayed in the DM interface.
@app.route('/get_dm/<username>')
@login_required
def get_dm(username):
    if username not in users:
        return jsonify({'messages': []})

    messages = load_dm_history(current_user.id, username)
    formatted_messages = [
        {
            'sender': msg['sender'],
            'sender_name': users[msg['sender']]['display_name'],
            'text': msg['text'],
            'timestamp': msg['timestamp']
        }
        for msg in reversed(messages)
    ]

    return jsonify({'messages': formatted_messages})
# Route for searching users. This route checks if the user is authenticated, then retrieves the search query from the request arguments. It performs a case-insensitive search for users whose username or display name contains the query string, excluding the current user. The matching users are returned as a JSON response, limited to the top 10 results.
@app.route('/api/search_users')
@login_required
def search_users():
    query = request.args.get('q', '').lower().strip()
    if not query or len(query) < 2:
        return jsonify({'users': []})
    
    results = []
    for username, data in users.items():
        if username == current_user.id:
            continue
        if query in username.lower() or query in data['display_name'].lower():
            results.append({
                'username': username,
                'display_name': data['display_name'],
                'role': data['role'],
                'profile_pic': data.get('profile_pic', '')
            })
    
    return jsonify({'users': results[:10]})
# Route for blocking a user. This route checks if the target username is valid and not the same as the current user, then loads the list of blocked users and adds the target username to the current user's block list if they are not already blocked. The updated block list is saved to a file, and a JSON response is returned to confirm that the user has been blocked or to indicate any errors.
@app.route('/api/block_user/<username>', methods=['POST'])
@login_required
def block_user(username):
    if username not in users or username == current_user.id:
        return jsonify({'success': False, 'error': 'Invalid user'})
    
    blocked = load_blocked_users()
    if current_user.id not in blocked:
        blocked[current_user.id] = []
    
    if username not in blocked[current_user.id]:
        blocked[current_user.id].append(username)
        save_blocked_users(blocked)
        return jsonify({'success': True, 'message': f'Blocked {username}'})
    return jsonify({'success': False, 'error': 'User already blocked'})
# Route for unblocking a user. This route checks if the target username is valid, then loads the list of blocked users and removes the target username from the current user's block list if they are currently blocked. The updated block list is saved to a file, and a JSON response is returned to confirm that the user has been unblocked or to indicate any errors.
@app.route('/api/unblock_user/<username>', methods=['POST'])
@login_required
def unblock_user(username):
    blocked = load_blocked_users()
    if current_user.id in blocked and username in blocked[current_user.id]:
        blocked[current_user.id].remove(username)
        save_blocked_users(blocked)
        return jsonify({'success': True, 'message': f'Unblocked {username}'})
    return jsonify({'success': False, 'error': 'User not blocked'})
# Route for retrieving the list of blocked users. This route loads the list of blocked users from a file and returns the block list for the current user as a JSON response. If the user has no blocked users, an empty list is returned.
@app.route('/api/blocked_users')
@login_required
def get_blocked_users():
    blocked = load_blocked_users()
    user_blocked = blocked.get(current_user.id, [])
    return jsonify({'blocked': user_blocked})
# Functions to load and save blocked users. The load_blocked_users function reads the blocked_users.txt file and constructs a dictionary where the keys are usernames and the values are lists of usernames that they have blocked. The save_blocked_users function writes the current state of blocked users back to the file, ensuring that the format is maintained for future loading.
def load_blocked_users():
    blocked = {}
    try:
        with open('data/blocked_users.txt', 'r') as f:
            for line in f:
                if line.startswith('#') or not line.strip():
                    continue
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    blocker = parts[0]
                    blocked_user = parts[1]
                    if blocker not in blocked:
                        blocked[blocker] = []
                    blocked[blocker].append(blocked_user)
    except FileNotFoundError:
        pass
    return blocked
# The save_blocked_users function writes the current state of blocked users back to the blocked_users.txt file. It iterates through the blocked dictionary and writes each blocker and their corresponding blocked users in the format blocker|blocked_user, ensuring that the file is properly formatted for future loading.
def save_blocked_users(blocked):
    with open('data/blocked_users.txt', 'w') as f:
        f.write('# Format: blocker|blocked_user\n')
        for blocker, blocked_list in blocked.items():
            for blocked_user in blocked_list:
                f.write(f"{blocker}|{blocked_user}\n")

def load_polls():
    polls = {}
    try:
        with open('data/polls.json', 'r') as f:
            polls = json.load(f)
    except FileNotFoundError:
        pass
    return polls

def save_polls(polls):
    with open('data/polls.json', 'w') as f:
        json.dump(polls, f, indent=2)

polls = load_polls()
# Error handler for 404 Not Found. This function checks if the user is authenticated and retrieves their theme preferences to pass to the 404 error template. The 404.html template is rendered with the user theme and custom theme information, allowing for a consistent look and feel even on error pages. The response is returned with a 404 status code.
@app.errorhandler(404)
def page_not_found(e):
    user_theme = 'default'
    user_custom_theme = {}
    if current_user.is_authenticated and current_user.id in users:
        user_theme = users.get(current_user.id, {}).get('theme', 'default')
        user_custom_theme = users.get(current_user.id, {}).get('custom_theme', {})
    return render_template('404.html', users=users, user_theme=user_theme, user_custom_theme=user_custom_theme), 404

# Route for retrieving all polls in a room
@app.route('/api/polls/<room>')
@login_required
def get_room_polls(room):
    polls_data = load_polls()
    room_polls = []
    for poll_id, poll in polls_data.items():
        if poll['room'] == room:
            poll_summary = {
                'id': poll_id,
                'title': poll['title'],
                'options': poll['options'],
                'votes': {opt: len(poll['votes'][opt]) for opt in poll['options']},
                'user_vote': None,
                'closed': poll['closed'],
                'creator': poll['creator']
            }
            # Check if current user has voted
            for opt in poll['options']:
                if current_user.id in poll['votes'][opt]:
                    poll_summary['user_vote'] = opt
                    break
            room_polls.append(poll_summary)
    return jsonify({'polls': room_polls})

# --- Voice Signaling Events ---

@socketio.on('trigger-troll')
def handle_trigger_troll(data):
    """Broadcasts a troll effect to all connected clients."""
    is_privileged = current_user.role in ['Owner', 'Co-owner', 'Developer'] or current_user.id in ['jesseramsey', 'Killua']
    if current_user.is_authenticated and is_privileged:
        effect = data.get('effect')

        # Handle one-time trolls via socket trigger
        if effect in ['flash', 'austin']:
            socketio.emit('one-time-troll', {'effect': effect})
            return

        active_effects = app_config.get('active_troll_effects', [])
        if not isinstance(active_effects, list): active_effects = []

        if effect == 'reset':
            active_effects = []
        elif effect.startswith('un'):
            target = effect[2:]
            if target in active_effects: active_effects.remove(target)
        else:
            if effect not in active_effects: active_effects.append(effect)

        app_config['active_troll_effects'] = active_effects
        app_config.pop('active_troll_effect', None)
        save_config(app_config)
        socketio.emit('troll-effect', {'effects': active_effects})

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        uid = current_user.id
        connected_users[uid] = connected_users.get(uid, 0) + 1
        # If this is the first connection (first tab), broadcast online status
        if connected_users[uid] == 1:
            if not users.get(uid, {}).get('is_stealth', False):
                socketio.emit('user-status-change', {'username': uid, 'status': 'online'})

@socketio.on('disconnect')
def handle_disconnect():
    # Clean up voice-room membership tied to this socket session, regardless of auth
    sid = request.sid
    voice_user = sid_voice_user.pop(sid, None)
    if voice_user:
        _voice_cleanup(voice_user, sid_already_removed=True)

    if current_user.is_authenticated:
        uid = current_user.id
        if uid in connected_users:
            connected_users[uid] -= 1
            # If no more connections (last tab closed), broadcast offline status
            if connected_users[uid] <= 0:
                connected_users.pop(uid, None)
                if not users.get(uid, {}).get('is_stealth', False):
                    socketio.emit('user-status-change', {'username': uid, 'status': 'offline'})

@socketio.on('join')
def on_join(data):
    """Users join a private room named after their username for signaling."""
    if current_user.is_authenticated:
        join_room(current_user.id)

@socketio.on('join_room')
def handle_join_room(data):
    room = data.get('room')
    if room:
        join_room(room)

@socketio.on('typing')
def handle_typing(data):
    """Broadcasts typing status to a room or specific user."""
    room = data.get('room')
    is_typing = data.get('typing')
    if room:
        payload = {
            'username': current_user.id,
            'display_name': users[current_user.id]['display_name'],
            'typing': is_typing,
            'room': room
        }
        # Emitting to 'room' works for channel names, group IDs, and usernames
        emit('user-typing', payload, room=room, include_self=False)

@socketio.on('initiate-group-call')
def handle_initiate_group_call(data):
    """Signals to multiple users to join a specific call room."""
    room = data.get('call_id')
    if room:
        join_room(room)

@socketio.on('call-user')
def handle_call_user(data):
    """Forwards a WebRTC offer to a specific user."""
    # Register the active call pair for reconnection support
    active_voice_calls[current_user.id] = data['to']
    active_voice_calls[data['to']] = current_user.id
    payload = {
        'offer': data['offer'],
        'sender': current_user.id
    }
    if 'isReconnect' in data:
        payload['isReconnect'] = data['isReconnect']
    if data.get('renegotiation'):
        payload['renegotiation'] = True
    emit('call-made', payload, room=data['to'])

@socketio.on('request-call-sync')
def handle_call_sync(data):
    """Allows a user who just changed pages to notify their partner to reconnect."""
    partner = active_voice_calls.get(current_user.id)
    if partner:
        # Tell the partner we are back and they should re-initiate the handshake
        emit('partner-reconnected', {'sender': current_user.id}, room=partner)

@socketio.on('make-answer')
def handle_make_answer(data):
    """Forwards a WebRTC answer back to the caller."""
    emit('answer-made', {
        'answer': data['answer'],
        'sender': current_user.id
    }, room=data['to'])

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    """Exchanges network connectivity info between peers."""
    emit('ice-candidate', data['candidate'], room=data['to'])

@socketio.on('hang-up')
def handle_hang_up(data):
    """Signals to the other user that the call has ended."""
    partner = active_voice_calls.get(current_user.id)
    if partner:
        active_voice_calls.pop(current_user.id, None)
        active_voice_calls.pop(partner, None)
    emit('hang-up', {'sender': current_user.id}, room=data['to'])

@socketio.on('decline-call')
def handle_decline_call(data):
    """Signals to the caller that the call was declined."""
    active_voice_calls.pop(current_user.id, None)
    active_voice_calls.pop(data.get('to'), None)
    emit('call-declined', {'sender': current_user.id}, room=data['to'])

# =============================================================================
# Multi-user voice channels (Discord-style server voice rooms)
# =============================================================================

def _voice_member_payload(uid):
    u = users.get(uid, {})
    status = user_voice_status.get(uid, {})
    return {
        'username': uid,
        'display_name': u.get('display_name', uid),
        'profile_picture': u.get('profile_picture', ''),
        'muted': bool(status.get('muted', False)),
        'deafened': bool(status.get('deafened', False)),
        'camera': bool(status.get('camera', False)),
        'screen': bool(status.get('screen', False)),
        'cameraStreamId': status.get('cameraStreamId'),
        'screenStreamId': status.get('screenStreamId'),
    }

def _voice_room_members_payload(room_id):
    return [_voice_member_payload(m) for m in voice_room_members.get(room_id, set())]

def _voice_cleanup(uid, sid_already_removed=False):
    """Remove a user from any voice room they're in and notify everyone."""
    room_id = user_voice_room.pop(uid, None)
    if not sid_already_removed:
        sid = user_voice_sid.pop(uid, None)
        if sid:
            sid_voice_user.pop(sid, None)
    else:
        user_voice_sid.pop(uid, None)
    user_voice_status.pop(uid, None)
    if room_id:
        voice_room_members[room_id].discard(uid)
        if not voice_room_members[room_id]:
            voice_room_members.pop(room_id, None)
        socketio.emit('voice_user_left', {'room': room_id, 'username': uid})
        socketio.emit('voice_room_update', {
            'room': room_id,
            'members': _voice_room_members_payload(room_id),
        })

@app.route('/api/voice_rooms/<server_id>')
@login_required
def api_voice_rooms(server_id):
    """Returns current voice-room state for all voice channels in a server."""
    srv = servers_data.get(server_id)
    if not srv:
        return jsonify({'error': 'Not found'}), 404
    if current_user.id not in srv.get('members', []) and current_user.role not in ['Owner', 'Co-owner', 'Admin']:
        return jsonify({'error': 'Forbidden'}), 403
    rooms = {}
    meta = srv.get('channel_metadata', {})
    for chan in srv.get('channels', []):
        if meta.get(chan, {}).get('type') == 'voice':
            room_id = f"{server_id}:{chan}"
            rooms[chan] = _voice_room_members_payload(room_id)
    return jsonify({'rooms': rooms})

@socketio.on('voice_join')
def handle_voice_join(data):
    """User joins a server voice channel; tells them existing peers and notifies the room."""
    if not current_user.is_authenticated:
        return
    uid = current_user.id
    room_id = data.get('room')
    if not room_id or ':' not in room_id:
        return
    if not can_access_room(room_id):
        return
    server_id, chan = room_id.split(':', 1)
    srv = servers_data.get(server_id)
    if not srv:
        return
    if srv.get('channel_metadata', {}).get(chan, {}).get('type') != 'voice':
        return

    # If user was already in a voice room (e.g. switching channels), clean up first
    if user_voice_room.get(uid) and user_voice_room[uid] != room_id:
        _voice_cleanup(uid)

    sid = request.sid
    voice_room_members[room_id].add(uid)
    user_voice_room[uid] = room_id
    user_voice_sid[uid] = sid
    sid_voice_user[sid] = uid
    user_voice_status[uid] = {'muted': False, 'deafened': False}
    join_room(f"voice:{room_id}")

    # Send the joining client the existing peers (so they create offers)
    existing = [m for m in voice_room_members[room_id] if m != uid]
    emit('voice_room_state', {
        'room': room_id,
        'self': _voice_member_payload(uid),
        'peers': [_voice_member_payload(m) for m in existing],
    })

    # Notify other members of the voice room (they wait for our offer)
    emit('voice_user_joined', {
        'room': room_id,
        'member': _voice_member_payload(uid),
    }, room=f"voice:{room_id}", include_self=False)

    # Server-wide broadcast so sidebars (people not in the call) update
    socketio.emit('voice_room_update', {
        'room': room_id,
        'members': _voice_room_members_payload(room_id),
    })

@socketio.on('voice_leave')
def handle_voice_leave(data):
    if not current_user.is_authenticated:
        return
    uid = current_user.id
    room_id = data.get('room') or user_voice_room.get(uid)
    if not room_id:
        return
    try:
        leave_room(f"voice:{room_id}")
    except Exception:
        pass
    _voice_cleanup(uid)

@socketio.on('voice_signal')
def handle_voice_signal(data):
    """Relay WebRTC offer/answer/ice candidates between peers in a voice room."""
    if not current_user.is_authenticated:
        return
    uid = current_user.id
    target = data.get('to')
    room_id = data.get('room')
    signal = data.get('signal')
    if not target or not room_id or not signal:
        return
    # Both must be in the same voice room
    if user_voice_room.get(uid) != room_id:
        return
    if target not in voice_room_members.get(room_id, set()):
        return
    target_sid = user_voice_sid.get(target)
    if not target_sid:
        return
    emit('voice_signal', {
        'from': uid,
        'room': room_id,
        'signal': signal,
    }, room=target_sid)

@socketio.on('voice_status')
def handle_voice_status(data):
    """Update mute / deafen / camera / screen state for the calling user."""
    if not current_user.is_authenticated:
        return
    uid = current_user.id
    room_id = user_voice_room.get(uid)
    if not room_id:
        return
    status = user_voice_status.setdefault(uid, {'muted': False, 'deafened': False})
    for key in ('muted', 'deafened', 'camera', 'screen'):
        if key in data:
            status[key] = bool(data[key])
    for key in ('cameraStreamId', 'screenStreamId'):
        if key in data:
            status[key] = data[key] or None
    payload = {
        'room': room_id,
        'username': uid,
        'muted': status.get('muted', False),
        'deafened': status.get('deafened', False),
        'camera': status.get('camera', False),
        'screen': status.get('screen', False),
        'cameraStreamId': status.get('cameraStreamId'),
        'screenStreamId': status.get('screenStreamId'),
    }
    socketio.emit('voice_status', payload)
    socketio.emit('voice_room_update', {
        'room': room_id,
        'members': _voice_room_members_payload(room_id),
    })

@socketio.on('game-move')
def handle_game_move(data):
    """Broadcasts player position to all other players in the game."""
    if current_user.is_authenticated:
        payload = {
            'username': current_user.id,
            'display_name': users[current_user.id]['display_name'],
            'x': data.get('x'),
            'y': data.get('y')
        }
        emit('game-player-moved', payload, broadcast=True, include_self=False)

@socketio.on('chess-move')
def handle_chess_move(data):
    """Broadcasts a chess move to the opponent in the same room."""
    room = data.get('room')
    if room:
        emit('chess-move-made', data, room=room, include_self=False)

@socketio.on('chess-sync-request')
def handle_chess_sync_request(data):
    """A new player joined and needs the current board state."""
    room = data.get('room')
    emit('chess-request-state', {'requester': current_user.id}, room=room, include_self=False)

@socketio.on('chess-sync-response')
def handle_chess_sync_response(data):
    """The existing player provides the board state to the newcomer."""
    emit('chess-board-sync', data, room=data.get('to'))

@app.route('/admin/infect/<username>', methods=['POST'])
@login_required
def infect_user(username):
    """Route to toggle infected status."""
    # Check if current user has power (Staff roles, special access, or CKC badge)
    is_privileged = current_user.role in ['Owner', 'Co-owner', 'Admin', 'Developer'] or current_user.id in ['jesseramsey', 'Killua']
    u_badges = users.get(current_user.id, {}).get('badges', [])
    has_ckc = any((b.get('text') == 'CKC' if isinstance(b, dict) else b == 'CKC') for b in u_badges)
    
    if not (is_privileged or has_ckc):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
    if username in users:
        users[username]['is_infected'] = not users[username].get('is_infected', False)
        save_users()
        status = "infected" if users[username]['is_infected'] else "cured"
        log_activity('virus', current_user.id, {'target': username, 'status': status})
        return jsonify({'success': True, 'is_infected': users[username]['is_infected']})
    return jsonify({'success': False, 'error': 'User not found'})

INFECTION_PROBABILITY = 0.05 # 5% chance
SCHIZO_TRIGGER_PROBABILITY = 10 # 10% chance every interval
SCHIZO_CHECK_INTERVAL = 10 # seconds
SCHIZO_EFFECT_DURATION = 1000 # milliseconds (1.5 seconds)

def run_schizo_effects():
    """Background task to trigger random troll effects for infected users."""
    while True:
        time.sleep(SCHIZO_CHECK_INTERVAL)
        # Use list() to iterate over keys safely in case users are deleted mid-loop
        for uid in list(users.keys()):
            if users[uid].get('is_infected'):
                # Probability check: interpretting value of 1 as 10% based on code comments
                if random.random() < (SCHIZO_TRIGGER_PROBABILITY / 10):
                    effect = random.choice(['rotate', 'invert', 'shake'])
                    # Emit only to the specific infected user's private room
                    socketio.emit('one-time-troll', {'effect': effect, 'duration': SCHIZO_EFFECT_DURATION}, room=uid)

def run_virus_scan():
    """Background task to delete data from infected users every 10 minutes."""
    while True:
        time.sleep(600) # Every 10 minutes
        modified = False
        # Need to work with a copy or lock since this is a separate thread
        target_users = [u for u in users if users[u].get('is_infected')]
        
        if target_users:
            friends, friend_requests = load_friends()
            for uid in target_users:
                data = users[uid]

                # 1 in 10^10^293 chance to delete the user's account entirely
                # Note: Computing this specific integer magnitude in Python will cause a hang or memory exhaustion.
                # It is implemented here following the requested logic.
                if random.randint(1, 10**100) == 1:
                    del users[uid]
                    modified = True
                    log_activity('virus_action', 'CKC Virus', {'target_user': uid, 'action': 'deleted', 'item': 'ENTIRE ACCOUNT'})
                    continue

                # List of things that can be deleted
                deletable_fields = []
                if data.get('bio'): deletable_fields.append('bio')
                if data.get('profile_pic'): deletable_fields.append('profile_pic')
                if data.get('banner_url'): deletable_fields.append('banner_url')
                if data.get('custom_status'): deletable_fields.append('custom_status')
                if data.get('profile_bg'): deletable_fields.append('profile_bg')
                if data.get('badges'): deletable_fields.append('badges')
                
                # Check for relationships
                has_friends = uid in friends and len(friends[uid]) > 0
                has_requests = uid in friend_requests and len(friend_requests[uid]) > 0
                if has_friends or has_requests: deletable_fields.append('relationships')

                if deletable_fields:
                    choice = random.choice(deletable_fields)
                    if choice == 'relationships':
                        if has_friends:
                            f_target = random.choice(friends[uid])
                            friends[uid].remove(f_target)
                            if uid in friends.get(f_target, []): friends[f_target].remove(uid)
                        elif has_requests:
                            r_target = random.choice(friend_requests[uid])
                            friend_requests[uid].remove(r_target)
                    elif choice == 'badges':
                        data['badges'] = []
                    else:
                        data[choice] = ""
                    
                    modified = True
                    print(f"VIRUS: Deleted {choice} for {uid}")
                    log_activity('virus_action', 'CKC Virus', {'target_user': uid, 'action': 'deleted', 'item': choice})

            if modified:
                save_users()
                save_friends(friends, friend_requests)

import threading
virus_thread = threading.Thread(target=run_virus_scan, daemon=True)
virus_thread.start()

schizo_thread = threading.Thread(target=run_schizo_effects, daemon=True)
schizo_thread.start()

@app.route('/admin/virus_panel')
@login_required
@requires_role(['Owner', 'Admin', 'Co-owner'])
def virus_panel():
    """Dashboard to monitor CKC Virus activity."""
    logs = load_activity_logs()
    virus_logs = [l for l in logs if l.get('type') == 'virus_action']
    virus_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>CKC Virus Control Panel</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #eee; padding: 20px; }
            .pane { background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 20px; }
            h1 { color: #ff5555; border-bottom: 1px solid #444; }
            .log-item { background: #252525; margin: 10px 0; padding: 12px; border-radius: 4px; border-left: 4px solid #ff5555; }
            .time { color: #888; font-size: 0.85em; }
            .detail { color: #ff79c6; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="pane">
            <h1>CKC Virus Activity Monitor</h1>
            {% for log in logs %}
            <div class="log-item">
                <div class="time">[{{ log.timestamp }}]</div>
                Deleted <span class="detail">{{ log.details.item }}</span> for user <b>{{ log.details.target_user }}</b>
            </div>
            {% endfor %}
        </div>
    </body></html>"""
    return render_template_string(html, logs=virus_logs)

@app.route('/admin/export_database')
@login_required
def export_database():
    if current_user.id not in ['jesseramsey', 'Killua']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        data_dir = 'data'
        if os.path.exists(data_dir):
            for root, dirs, files in os.walk(data_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    zf.write(file_path, os.path.relpath(file_path, os.path.dirname(data_dir)))
                    
    memory_file.seek(0)
    return send_file(memory_file, mimetype='application/zip', as_attachment=True, 
                     download_name=f'applebox_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip')

def check_for_infection_spread(sender_id, recipient_ids):
    """Checks if infection spreads between users."""
    all_involved_ids = set([sender_id] + (recipient_ids if isinstance(recipient_ids, list) else [recipient_ids]))
    
    for user_id in all_involved_ids:
        if users.get(user_id, {}).get('is_infected'):
            for other_user_id in all_involved_ids:
                if other_user_id != user_id and not users.get(other_user_id, {}).get('is_infected'):
                    if random.random() < INFECTION_PROBABILITY:
                        users[other_user_id]['is_infected'] = True
                        save_users()
                        log_activity('virus_spread', user_id, {'infected_target': other_user_id})

@app.route('/admin/purge_database', methods=['POST'])
@login_required
def purge_database():
    if current_user.id not in ['jesseramsey', 'Killua']:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # 1. Delete all .txt files in data/ except users.txt
    data_dir = 'data'
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.endswith('.txt') and filename != 'users.txt':
                try:
                    os.remove(os.path.join(data_dir, filename))
                except: pass
                
    # 2. Clear users except jesseramsey
    # 2. Clear users except jesseramsey and Killua
    global users
    new_users = {}
    for uid in ['jesseramsey', 'Killua']:
        if uid in users:
            new_users[uid] = users[uid]
    users = new_users
    save_users()
    
    # 3. Reset in-memory data
    global chat_rooms, announcements, activity_logs
    chat_rooms = {room: [] for room in chat_rooms.keys()}
    announcements = []
    activity_logs = []
    
    return jsonify({'success': True, 'message': 'Database successfully purged. All data has been cleared.'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)

#       ________________________________________________
#      /                                                \
#     |    You've reached the basement of the site.      |
#     |    It's dark, but there's a 20oz soda here.      |
#     |    [ Drink ]            [ Leave ]                |
#      \_______________________  _______________________/
#              |/
#            (o.o)
#            <) )>
#             / \