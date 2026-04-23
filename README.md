# AppleBox Chat

AppleBox Chat is a feature-rich, real-time communication platform built with Python and Flask. Designed for communities and friend groups, it combines traditional messaging with advanced customization, security features, and integrated gaming.

## 🚀 Key Features

### 💬 Communication
*   **Real-Time Messaging:** Public channels (General, Random, Support, etc.) powered by SocketIO.
*   **Private Conversations:** Secure Direct Messaging (DM) system between friends.
*   **Group Chats:** Create and manage group DMs with custom names and icons.
*   **Voice Calling:** Peer-to-peer voice calls implemented via WebRTC signaling.

### 🎨 Customization
*   **Profile Personalization:** Set custom bios, profile pictures, and profile banners.
*   **Theme Engine:** Choose from built-in themes (Solarized, Nord, Dark) or create a fully custom CSS-based theme.
*   **Badges:** Unique cosmetic badges for staff, developers, and OG members.
*   **Custom Emojis:** Admin-managed custom emoji uploads.

### 🛡️ Security & Moderation
*   **Data Protection:** AES-GCM encrypted passwords and security question verification.
*   **Profanity Filter:** Automated filtering of inappropriate content in messages and bios.
*   **Admin Panel:** Robust tools for staff to manage users, view activity logs, and handle reports.
*   **Stealth Mode:** Staff-only feature to remain invisible while active.

### 🎮 Integrated Entertainment
*   **AppleBox Platformer:** A custom Pygame-based platformer embedded directly in the site.
*   **Poll System:** Create interactive polls and track community votes in real-time.
*   **Game Ports:** Support for integrated web-based games and clickers.

## 🛠️ Technology Stack

*   **Backend:** Python, Flask
*   **Real-time:** Flask-SocketIO (WebSockets)
*   **Authentication:** Flask-Login
*   **Encryption:** Cryptography (AES-GCM)
*   **Database:** Flat-file storage (JSON/TXT) for high portability
*   **Game Engine:** Pygame

## 📋 Admin Commands

Users with `Mod`, `Admin`, or `Owner` roles have access to powerful slash commands:

| Command | Description |
| :--- | :--- |
| `/ban {user}` | Suspends a user account. |
| `/mute {user}` | Prevents a user from sending messages. |
| `/chatclear` | Wipes the message history of the current room. |
| `/role {user} {role}` | Updates a user's permission level. |
| `/poll create {title} {options}` | Launches a new community poll. |
| `/announce {text}` | Broadcasts a server-wide announcement. |
| `/larp` | Randomly assigns funny prefixes to all display names. |
| `/say {user} {text}` | (Admin+) Sends a message as a specific user. |

## 💻 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/applebox-chat.git
    ```
2.  **Install dependencies:**
    ```bash
    pip install flask flask-socketio flask-login cryptography pytz
    ```
3.  **Run the application:**
    ```bash
    python main.py
    ```

## 📄 License

This project is developed for educational and community purposes. 

---

*“Still better than homework!”*

*(o.o)*
*<) )>*