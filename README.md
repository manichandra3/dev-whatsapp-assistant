# 🤖 Developer WhatsApp Assistant

A Developer's WhatsApp Assistant Brain (via Baileys) and AI (OpenAI/Anthropic/Google Gemini). Features an intent router for taking actions like setting reminders, running code, and summarizing links.

**Architecture**: Hybrid Bridge - Node.js handles WhatsApp transport, while Python handles the LLM orchestration, SQLite memory, and intent routing.

## 🎯 Features

### 🧠 Intent Routing
- **Strict JSON Generation**: Evaluates user intent into `schedule_task`, `execute_code`, `debug_code`, `summarize_link`, `log_expense`, or `general_chat`
- **Fallback Catch**: "Silent Catch" gracefully degrades parsing failures into conversational apologies
- **Dual Stack Support**: Run in pure Node.js or via the Python bridge for future Python-native agent tooling

### 💾 Stateful Memory
- **Rolling Context**: Remembers the last 10 messages for stateful debugging conversations
- **SQLite Storage**: Logs all messages and generated intents for analytics and recovery

- **SQLite Database**: Stores daily metrics, recovery milestones, and user configuration
- **Trend Analysis**: Monitors progress over time
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
cd acl-rehab-coach

# Install Python dependencies
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

# Set surgery date (YYYY-MM-DD)
SURGERY_DATE=2026-01-15

# Optional: Customize paths
DATABASE_PATH=./data/acl_rehab.db
WHATSAPP_SESSION_PATH=./whatsapp_session
LOG_LEVEL=info
```

### Step 3: Start the Services

The application runs as two services: Python backend (coach logic) and Node.js frontend (WhatsApp transport).

**Terminal 1 - Start Python Backend:**

```bash
# Start the Python coach service
npm run python:start
# Or: python -m app.main

# You should see:
# ACL Rehab Coach Starting...
# LLM Provider: anthropic
# Model: claude-3-haiku-20240307
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

If you prefer to run without the Python backend (not recommended):

```bash
npm run start:legacy
```

### Step 4: Test the Bot

Send a message to the WhatsApp number you linked from another device:

```
Hello!
```

You should receive a greeting from your ACL Rehab Coach!

## 🧪 Testing

### Test Python Safety Interceptor

```bash
npm run python:test
# Or: python -m pytest tests/ -v
```

### Test Node.js Safety Interceptor (Legacy)

```bash
npm test
```

This runs the safety interceptor test suite to verify red flag detection is working correctly.

### Manual Testing

**Test Red Flag Detection:**

Send this message to your bot:
```
I have severe calf pain and swelling
```

You should receive an **immediate emergency response** (bypassing the AI):
```
🚨 MEDICAL ALERT 🚨

I've detected symptoms that require IMMEDIATE medical attention...
```

**Test Normal Coaching:**

Send this message:
```
Hi! My pain is 4/10 today, swelling is the same, ROM is 5° extension and 110° flexion. I did my exercises.
```

The bot should:
1. Call `log_daily_metrics` tool
2. Call `get_recovery_phase` tool
3. Provide personalized coaching based on your phase
4. Include daily reminders (water, medication, ice/elevate)

## 📂 Project Structure

```
acl-rehab-coach/
├── app/                       # Python backend
│   ├── __init__.py
│   ├── main.py               # Python entry point
│   ├── config.py             # Settings management (pydantic)
│   ├── coach.py              # Main conversation orchestrator
│   ├── safety_interceptor.py # Red flag detection (Python)
│   ├── database.py           # SQLite database (SQLAlchemy)
│   ├── tools.py              # LLM function tools
│   ├── llm/
│   │   ├── __init__.py
│   │   └── providers.py      # OpenAI/Anthropic/Google adapters
│   └── api/
│       ├── __init__.py
│       └── bridge.py         # FastAPI HTTP bridge
├── src/                       # Node.js WhatsApp transport
│   ├── index.js              # Legacy entry point (Node-only)
│   ├── index-bridge.js       # Bridge entry point (recommended)
│   ├── bridge-client.js      # HTTP client for Python backend
│   ├── whatsapp-bot.js       # WhatsApp Baileys integration
│   ├── safety-interceptor.js # Red flag detection (Node, legacy)
│   ├── database.js           # SQLite manager (Node, legacy)
│   ├── tools.js              # LLM tools (Node, legacy)
│   ├── llm-provider.js       # LLM interface (Node, legacy)
│   └── test-safety.js        # Safety test suite (Node)
├── tests/                     # Python tests
│   ├── __init__.py
│   └── test_safety.py        # Safety interceptor tests (pytest)
├── skills/
│   └── acl-rehab/
│       └── SKILL.md          # Skill documentation
├── data/                     # SQLite database (auto-created)
├── whatsapp_session/         # WhatsApp auth (auto-created)
├── pyproject.toml            # Python project config
├── package.json              # Node.js project config
├── .env.example              # Environment template
└── README.md
```

## 🛠️ Development

### Run in Development Mode (Auto-reload)

**Python Backend:**

```bash
# Using uvicorn directly with reload
uvicorn app.api.bridge:app --reload --host 127.0.0.1 --port 8000
```

**Node.js Bridge:**

```bash
npm run dev:bridge
```

### npm Scripts

| Script | Description |
|--------|-------------|
| `npm run python:start` | Start Python backend |
| `npm run python:test` | Run Python tests |
| `npm run start:bridge` | Start Node.js WhatsApp bridge |
| `npm run dev:bridge` | Start bridge with auto-reload |
| `npm run start:legacy` | Start legacy Node-only mode |
| `npm test` | Run Node.js safety tests |

### Database Schema

**daily_metrics:**
- `id`, `user_id`, `date`, `timestamp`
- `pain_level` (0-10), `swelling_status` (worse/same/better)
- `rom_extension`, `rom_flexion` (degrees)
- `adherence` (boolean), `notes`

**user_config:**
- `user_id`, `surgery_date`, `surgeon_name`, `surgery_type`
- `created_at`, `updated_at`

**recovery_milestones:**
- `id`, `user_id`, `milestone_name`
- `achieved_date`, `weeks_post_op`, `notes`

## 📊 Recovery Phases

The system automatically determines the user's recovery phase:

| Phase | Timeline | Focus |
|-------|----------|-------|
| Phase 1 | 0-2 weeks | Protection & Initial Recovery |
| Phase 2 | 2-6 weeks | Early Strengthening |
| Phase 3 | 6-12 weeks | Progressive Loading |
| Phase 4 | 3+ months | Return to Sport Preparation |

Each phase has specific:
- Recommended exercises
- Precautions
- Goals

## 🚨 Red Flag Keywords

The safety interceptor automatically detects:

- **DVT/Blood Clots**: calf pain, calf swelling
- **Infection**: fever, pus, discharge, infection
- **Graft Failure**: loud pop, popping sound
- **Severe Swelling**: huge swelling, massive swelling
- **Severe Pain**: severe pain, unbearable pain, pain level 9-10
- **Neurological**: numbness, tingling, loss of feeling
- **Cardiovascular**: chest pain, breathing difficulty
- **Circulation**: foot cold, foot blue, toes blue

## 🔒 Security & Privacy

- All data stored **locally** in SQLite database
- WhatsApp session files stored **locally**
- No data sent to third parties (except LLM API for coaching)
- LLM API keys stored in `.env` (never committed to git)

**Important:** Add `.env` and `whatsapp_session/` to `.gitignore`!

## 🐛 Troubleshooting

### QR Code Not Appearing

```bash
# Make sure you're in the project directory
cd acl-rehab-coach

# Try deleting session and reconnecting
rm -rf whatsapp_session
npm start
```

### Database Errors

```bash
# Check if data directory exists and is writable
mkdir -p data
chmod 755 data

# Check database file permissions
ls -la data/acl_rehab.db
```

### LLM API Errors

```bash
# Verify your API key is set
echo $OPENAI_API_KEY  # or ANTHROPIC_API_KEY, GOOGLE_API_KEY

# Check .env file
cat .env | grep API_KEY

# Test API key manually
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Connection Issues

```bash
# Check logs for errors
npm start

# Look for connection status messages:
# ✅ [WhatsApp] Connected successfully!
# ✅ [DATABASE] Connected to ./data/acl_rehab.db
# [LLM] Initialized openai with model gpt-4o
```

## 📚 Advanced Configuration

### Multi-User Support

The system supports multiple WhatsApp users. Each user gets:
- Independent conversation history
- Separate metrics tracking
- Individual surgery date configuration

### Custom Surgery Date Per User

Users can have different surgery dates stored in the database:

```javascript
// In database.js
db.setSurgeryDate(userId, '2026-02-01', 'Dr. Smith', 'ACL Reconstruction');
```

### Conversation History Limits

Default: 20 messages per user to prevent context overflow.

To change, edit `src/index.js`:

```javascript
const maxMessages = 30;  // Increase history length
```

## 📄 License

MIT License - See LICENSE file for details

## ⚠️ Medical Disclaimer

**THIS SOFTWARE IS FOR COACHING AND TRACKING PURPOSES ONLY.**

- NOT a replacement for professional medical advice
- NOT a diagnostic tool
- NOT a treatment recommendation system
- Always consult with your surgeon or physical therapist for medical decisions
- Emergency symptoms require immediate medical attention

The safety interceptor is designed to catch common red flags, but it is NOT comprehensive and should NOT be relied upon as a medical alert system.

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [ ] Add more sophisticated red flag detection (ML-based)
- [ ] Integrate with wearable devices for automatic ROM tracking
- [ ] Add visualization dashboard for recovery trends
- [ ] Support for multiple languages
- [ ] Voice message support
- [ ] Integration with physical therapy clinic systems

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review test cases in `src/test-safety.js`
3. Open an issue on GitHub (if repository is public)

---

**Built with ❤️ for ACL recovery patients**
