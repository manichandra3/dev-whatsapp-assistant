# 🤖 Developer WhatsApp Assistant

A Developer's WhatsApp Assistant Brain (via Baileys) and AI (OpenAI/Anthropic/Google Gemini). Features an intent router for taking actions like setting reminders, running code, and summarizing links.

**Architecture**: Hybrid Bridge - Node.js handles WhatsApp transport, while Python handles the LLM orchestration, SQLite memory, and intent routing.

## 🎯 Features

### 🧠 Intent Routing
- **Strict JSON Generation**: Evaluates user intent into `schedule_task`, `execute_code`, `debug_code`, `summarize_link`, `log_expense`, `general_chat`, `list_tasks`, or `cancel_task`
- **Fallback Catch**: "Silent Catch" gracefully degrades parsing failures into conversational apologies
- **Dual Stack Support**: Run in pure Node.js or via the Python bridge for future Python-native agent tooling

### 💾 Stateful Memory
- **Rolling Context**: Remembers the last 10 messages for stateful debugging conversations
- **SQLite Storage**: Logs all messages and generated intents for analytics and recovery
- **Privacy-First**: All data stored locally

### 📱 WhatsApp Integration
- **QR Code Authentication**: Simple setup via WhatsApp linked devices
- **Real-time Messaging**: Instant responses with typing indicators
- **Persistent Sessions**: Maintains connection across restarts

## 📋 Prerequisites

- **Python**: Version 3.12+
- **Node.js**: Version 18+ (20+ recommended) - for WhatsApp transport only
- **npm** or **pnpm** or **bun**
- **WhatsApp Account**: Personal phone number for bot
- **LLM API Key**: Choose one:
  - OpenAI API key (recommended: GPT-4o)
  - Anthropic API key (Claude 3.5 Sonnet)
  - Google AI API key (Gemini 2.0 Flash)

## 🚀 Installation

### Step 1: Clone and Install Dependencies

```bash
# Navigate to project directory
cd dev-whatsapp-assistant

# Setup virtual environment and install Python dependencies
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Install Node.js dependencies (for WhatsApp transport)
npm install
```

### Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env  # or use your preferred editor
```

**Required Configuration:**

```env
# Choose your LLM provider
LLM_PROVIDER=openai  # or: anthropic, google
LLM_MODEL=gpt-4o     # or: claude-3-5-sonnet-20241022, gemini-2.0-flash-exp

# Add corresponding API key
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=...

# Optional: Customize paths
DATABASE_PATH=./data/dev_assistant.db
WHATSAPP_SESSION_PATH=./whatsapp_session
LOG_LEVEL=info

# Reminder Scheduler (optional)
SCHEDULER_ENABLED=true
SCHEDULER_POLL_INTERVAL_SECONDS=30
SCHEDULER_BATCH_SIZE=50
SCHEDULER_DELIVERY_CALLBACK_URL=http://127.0.0.1:3010
SCHEDULER_CALLBACK_SECRET=your-secret  # Optional: HMAC secret for callback security
```

### Step 3: Start the Services

The application runs as two services: Python backend and Node.js frontend (WhatsApp transport).

**Terminal 1 - Start Python Backend:**

```bash
# Start the Python service
npm run python:start

# You should see:
# Dev Assistant Starting...
# LLM Provider: ...
# Model: ...
# Bridge: http://127.0.0.1:8000
```

**Terminal 2 - Start Node.js WhatsApp Bridge:**

```bash
# Start the WhatsApp bridge
npm run start:bridge

# A QR code will appear in your terminal
# Scan it with WhatsApp:
# 1. Open WhatsApp on your phone
# 2. Go to: Settings > Linked Devices
# 3. Tap "Link a Device"
# 4. Scan the QR code

# Once connected, you'll see: ✅ [WhatsApp] Connected successfully!
```

### Legacy Mode (Node.js Only)

If you prefer to run without the Python backend:

```bash
npm run start:legacy
```

## 🧪 Testing

### Test Python Intents
```bash
npm run python:test
```

### Test Node.js 
```bash
npm test
```

## 🔒 Security & Privacy

- All data stored **locally** in SQLite database
- WhatsApp session files stored **locally**
- No data sent to third parties (except LLM API for intent routing)
- LLM API keys stored in `.env` (never committed to git)

## 📄 License

MIT License - See LICENSE file for details
