# 🤖 Monolith Discord Bot for OpenWebUI

A Discord bot for the OpenWebUI community, providing LLM interactions, documentation search, model discovery, and more.

## 📋 Features

### 🧠 OpenWebUI Integration
- **!ask [model] \<prompt>** - Send prompts to an LLM through OpenWebUI
- **!openwebui_models** - List all available models from your OpenWebUI instance
- **!diagnose_api** - Run diagnostics on the OpenWebUI API connection
- **!clear_chat** - Clear your conversation history with the bot

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
- **!welcome** - Display a welcome message with features overview

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
   git clone https://github.com/pkeffect/oi_discord_bot.git
   cd monolith-discord-bot
   ```

2. Copy the example environment file and edit with your settings
   ```bash
   cp .env.example .env
   # Edit .env with your preferred editor
   ```

3. Fill in the required environment variables:
   - `DISCORD_TOKEN`: Your Discord bot token (required)
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

### Clear conversation history:
```
!clear_chat
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

## 🛠️ Project Structure and Architecture

The bot is designed with a modular architecture using Discord.py's cog system:

```
monolith-discord-bot/
├── cogs/                    # Command modules
│   ├── admin_cog.py         # Administrative commands
│   ├── channel_logger_cog.py # Channel logging functionality
│   ├── documentation_cog.py  # Documentation search
│   ├── general_cog.py       # Basic utility commands
│   ├── help_cog.py          # Custom help system
│   ├── ollama_model_search_cog.py # Model discovery
│   ├── openwebui_cog.py     # LLM interaction
│   └── youtube_cog.py       # YouTube search
├── config_manager.py        # Configuration handling
├── monolith_discord.py      # Main bot entry point
├── utils.py                 # Shared utility functions
└── ... other configuration files
```

Key components:

- **MonolithBot Class**: Extended Discord.py bot with configuration management and error handling
- **ConfigManager**: Centralizes configuration from environment variables and files
- **Cog System**: Organizes commands into modular feature sets
- **Error Handling System**: Multi-layered approach with specific handlers at each level
- **Rate Limiting**: Prevents command spam and API abuse

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Bot Won't Start
- Ensure `DISCORD_TOKEN` is set correctly
- Verify Python version is 3.12+
- Check all dependencies are installed
- Look for detailed error messages in the logs

#### OpenWebUI Commands Fail
- Run `!diagnose_api` to check OpenWebUI connectivity
- Verify API key or JWT token configuration
- Ensure OpenWebUI server is running and accessible
- Check that specified models exist on your OpenWebUI instance

#### Documentation Search Issues
- Run `!syncdocs` to manually rebuild the documentation index
- Verify `DOCS_ZIP_URL` points to a valid documentation archive
- Check that the documentation structure matches expected patterns

### Diagnostic Tools

- **!diagnose_api**: Comprehensive API connection testing
- **!debug_env**: Shows loaded configuration (admin only)
- **!test_auth**: Verifies authentication credentials
- **!logger_status**: Displays channel logging configuration

## 📊 Logging System

The bot implements comprehensive logging:

- **Console Output**: Real-time logs during operation
- **File Logging**: All logs stored in the `logs/` directory
- **Channel Logging**: Optional Discord channel archiving
- **Structured Format**: Timestamps, log levels, and contextual information

Log files use the format `bot_YYYYMMDD_HHMMSS.log` and contain all bot activity.

## 🧪 Development Guidelines

### Adding New Commands

To add a new command to an existing cog:

1. Define the command method with appropriate decorator:
   ```python
   @commands.command(name="command_name", help="Command description")
   async def command_method(self, ctx: commands.Context, *args):
       # Command implementation
   ```

2. Add error handling for the command
3. Update help documentation
4. Include proper logging

### Creating New Cogs

For new feature modules:

1. Create a new file in the `cogs/` directory
2. Follow the established cog structure pattern
3. Implement `setup()` function for loading
4. Register the cog in documentation

### Testing

The project uses pytest for testing:

- Test files located in `tests/` directory
- Run with `pytest` command
- Async fixture support for bot/cog testing
- Mocking framework for external dependencies

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
