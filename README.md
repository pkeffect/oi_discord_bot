# 🤖 Monolith Discord Bot for OpenWebUI

A Discord bot for the OpenWebUI community, providing LLM interactions, documentation search, model discovery, and more.

## 📋 Features

### 🧠 OpenWebUI Integration
- **!ask [model] \<prompt>** - Send prompts to an LLM through OpenWebUI
- **!openwebui_models** - List all available models from your OpenWebUI instance
- **!diagnose_api** - Run diagnostics on the OpenWebUI API connection

### 📚 Documentation
- **!docs \<query>** - Search through the OpenWebUI documentation
- Auto-syncing with the latest documentation

### 🔍 Model Discovery
- **!osearch \<query>** - Search for models on ollama.com
- View model details, stats, and download information

### 🎥 YouTube Search
- **!youtube \<query>** (or **!yt \<query>**) - Search YouTube and get top 3 results

### 📊 Utility
- **!ping** - Check the bot's latency to Discord

### 🛡️ Admin Commands
- **!syncdocs** - Manually trigger documentation sync
- **!set_api_key** - Set OpenWebUI API key
- **!set_jwt_token** - Set OpenWebUI JWT token
- **!test_auth** - Test API authentication
- **!debug_env** - Show environment configuration
- **!reload_logger_config** - Reload channel logger configuration
- **!logger_status** - Show which channels are being logged

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- Docker (optional, for containerized deployment)
- Discord Bot Token
- OpenWebUI instance (for LLM-related features)

### Environment Setup
1. Clone the repository
   ```bash
   git clone https://github.com/yourusername/monolith-discord-bot.git
   cd monolith-discord-bot
   ```

2. Copy the example environment file and edit with your settings
   ```bash
   cp .env.example .env
   # Edit .env with your preferred editor
   ```

3. Fill in the required environment variables:
   - `DISCORD_TOKEN`: Your Discord bot token
   - `OPENWEBUI_API_URL`: URL to your OpenWebUI instance
   - `OPENWEBUI_DEFAULT_MODEL`: Default LLM model to use
   - `OPENWEBUI_API_KEY` or `OPENWEBUI_JWT_TOKEN`: Authentication for OpenWebUI
   - `DOCS_ZIP_URL`: URL to the documentation ZIP file (default is OpenWebUI docs)
   - `DOCS_BASE_URL`: Base URL for documentation links

### Installation

#### Option 1: Docker (Recommended)
```bash
docker-compose up -d
```

#### Option 2: Local Installation
```bash
# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python monolith_discord.py
```

## 🔧 Configuration

### OpenWebUI Connection
The bot needs to connect to an OpenWebUI instance for LLM-related features. Configure in `.env`:
```
OPENWEBUI_API_URL="http://host.docker.internal:3999"  # Adjust as needed
OPENWEBUI_DEFAULT_MODEL="llama3:latest"  # Your default model
OPENWEBUI_API_KEY=""  # API key if required
OPENWEBUI_JWT_TOKEN=""  # JWT token if required instead of API key
```

### Documentation Setup
For documentation search features:
```
DOCS_ZIP_URL="https://github.com/open-webui/docs/archive/refs/heads/main.zip"
DOCS_BASE_URL="https://docs.openwebui.com/"
DOCS_SUBDIR_IN_ZIP="docs/"
```

### Channel Logging
Channel logging is configured in `channel_logger_config.json`:
```json
{
  "log_directory": "./data/channel_logs",
  "log_format": "{timestamp} [{author_name} ({author_id})] {message_content}{attachments_info}",
  "download_media": true,
  "media_directory": "./data/channel_logs/media",
  "servers": {
    "SERVER_ID": [
      "CHANNEL_ID_1",
      "CHANNEL_ID_2"
    ]
  }
}
```

## 📝 Usage Examples

### Ask an LLM via OpenWebUI:
```
!ask What is OpenWebUI?
```

### Ask with specific model:
```
!ask llama3:latest Explain the advantages of Ollama vs other local LLM solutions
```

### Search documentation:
```
!docs installation
```

### Search for Ollama models:
```
!osearch llama3
```

### Search YouTube:
```
!yt open webui tutorial
```

## 🔄 Updating

### Docker Setup
```bash
git pull
docker-compose build
docker-compose up -d
```

### Local Setup
```bash
git pull
pip install -r requirements.txt
# Restart the bot
```

## 🔮 Roadmap

- Discord Slash Commands integration
- Web dashboard for administration
- Integration with more model repositories
- User-specific LLM preferences
- Context-aware conversations with LLMs
- Custom knowledge base training
- Community polls and feedback collection
- Integration with GitHub for issue tracking

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) and [Security Policy](SECURITY.md) before contributing.