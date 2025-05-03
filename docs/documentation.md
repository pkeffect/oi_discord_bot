# Monolith Discord Bot - Comprehensive Documentation

## Table of Contents
- [Introduction](#introduction)
- [Core Features](#core-features)
  - [OpenWebUI Integration](#openwebui-integration)
  - [Documentation Search](#documentation-search)
  - [Model Discovery](#model-discovery)
  - [Media Search](#media-search)
  - [Utility Commands](#utility-commands)
  - [Administrative Tools](#administrative-tools)
  - [Channel Logging](#channel-logging)
- [Technical Architecture](#technical-architecture)
  - [Codebase Organization](#codebase-organization)
  - [Class Structure](#class-structure)
  - [Error Handling System](#error-handling-system)
  - [Configuration Management](#configuration-management)
  - [Rate Limiting](#rate-limiting)
- [Setup and Deployment](#setup-and-deployment)
  - [Environment Configuration](#environment-configuration)
  - [Local Installation](#local-installation)
  - [Docker Deployment](#docker-deployment)
  - [Data Persistence](#data-persistence)
- [API Integrations](#api-integrations)
  - [OpenWebUI API](#openwebui-api)
  - [Discord API](#discord-api)
  - [YouTube API](#youtube-api)
  - [Ollama Model Repository](#ollama-model-repository)
- [Command Reference](#command-reference)
  - [User Commands](#user-commands)
  - [Administrator Commands](#administrator-commands)
- [Development Guide](#development-guide)
  - [Adding New Commands](#adding-new-commands)
  - [Creating New Cogs](#creating-new-cogs)
  - [Testing Guidelines](#testing-guidelines)
  - [Contribution Workflow](#contribution-workflow)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
  - [Diagnostic Tools](#diagnostic-tools)
  - [Logs Interpretation](#logs-interpretation)
- [Security Considerations](#security-considerations)
  - [API Key Management](#api-key-management)
  - [Permission System](#permission-system)
  - [Data Handling](#data-handling)
- [Appendices](#appendices)
  - [Configuration File Examples](#configuration-file-examples)
  - [Advanced Usage Patterns](#advanced-usage-patterns)

## Introduction

Monolith Discord Bot is a comprehensive integration solution for OpenWebUI, providing Discord communities with seamless access to Large Language Models (LLMs), documentation search capabilities, model discovery tools, and more. Built on a modular architecture using Discord.py's cogs system, the bot offers a rich feature set while maintaining extensibility and maintainability.

The bot serves as a bridge between Discord communities and the powerful capabilities of OpenWebUI, allowing users to interact with various LLMs directly from Discord channels. Whether users need quick answers, documentation lookups, or want to explore available models, Monolith provides these capabilities through an intuitive command interface.

## Core Features

### OpenWebUI Integration

The OpenWebUI integration module forms the heart of Monolith, enabling direct interaction with language models through the OpenWebUI API.

#### LLM Interaction (`!ask`)

The `!ask` command provides the core functionality of communicating with language models. It supports:

- Querying the default model: `!ask What is OpenWebUI?`
- Specifying a particular model: `!ask llama3:latest Explain quantum computing`
- Maintaining conversation context through a session system
- Message streaming for real-time responses (where supported)
- Regeneration options for unsatisfactory responses

Under the hood, the command:
1. Parses the input to extract any model specification
2. Retrieves the user's conversation history (if any)
3. Formats and sends the request to the OpenWebUI API
4. Processes the response, adding features like clickable regeneration buttons
5. Updates the conversation history for context preservation

The implementation intelligently handles different API endpoint formats and authentication methods, making it compatible with various OpenWebUI configurations.

#### Model Listing (`!openwebui_models`)

This command queries the OpenWebUI instance for all available models and presents them in an organized format. It:

- Tries multiple endpoint patterns to maximize compatibility
- Formats model information including size and modification date
- Groups models by type (when such information is available)
- Provides buttons for testing models directly

#### API Diagnostics (`!diagnose_api`)

The comprehensive diagnostics tool performs a series of tests on the OpenWebUI connection:

1. Network connectivity tests (DNS resolution, TCP connection)
2. Multiple endpoint availability checks
3. Authentication verification
4. Request/response cycle validation
5. Data format verification

Results are presented in an easy-to-understand embedded report with color-coding for issues detected.

#### Conversation Management (`!clear_chat`)

The bot maintains conversation history for each user, enabling context-aware interactions with LLMs. The `!clear_chat` command allows users to:

- Reset their conversation history
- Start fresh conversations with the model
- Manage their interaction privacy

Conversations automatically expire after a period of inactivity (default: 30 minutes) to conserve memory.

### Documentation Search

The documentation module provides access to OpenWebUI's documentation directly in Discord.

#### Documentation Search (`!docs`)

The `!docs` command enables powerful searches through the documentation:

- Full-text search capability: `!docs installation`
- Support for phrase matching: `!docs "api configuration"`
- Intelligent ranking of results based on relevance
- Section highlighting to indicate where matches occurred

Technically, this utilizes:
- A SQLite FTS (Full-Text Search) database
- Asyncio for non-blocking operation
- Regular syncing with the source documentation
- Smart result summarization for Discord's format

#### Documentation Synchronization (`!syncdocs`)

For administrators, the `!syncdocs` command:
- Downloads the latest documentation ZIP
- Extracts relevant content
- Parses Markdown files to extract structure
- Builds the search index database
- Updates internal URL mappings

This ensures the bot always has the most current information available.

### Model Discovery

The model discovery feature helps users find and learn about available LLM models.

#### Ollama Model Search (`!osearch`)

The `!osearch` command scrapes ollama.com to provide up-to-date information on models:

- Retrieves model metadata: `!osearch llama`
- Shows download counts, tag counts, and last update dates
- Presents formatted results with pagination
- Provides direct links to model pages

This is implemented through:
- Web scraping with BeautifulSoup
- Asynchronous HTTP requests
- Interactive Discord UI components for navigation
- Robust error handling for network issues

### Media Search

The media search module integrates with external platforms for content discovery.

#### YouTube Search (`!youtube`, `!yt`)

The YouTube search commands utilize the youtube-search-python library to:
- Find relevant videos: `!yt openwebui tutorial`
- Display video thumbnails, durations, and channel information
- Provide direct links to videos
- Return the most relevant results first

The implementation features:
- Asynchronous execution for responsiveness
- Rate limiting to prevent API abuse
- Rich embed formatting for visual appeal
- Error handling for network issues and API changes

### Utility Commands

The utility module provides general-purpose commands for bot interaction.

#### Latency Check (`!ping`)

The `!ping` command checks the bot's connection to Discord by:
- Measuring round-trip time between command and response
- Calculating Discord API latency
- Displaying results in milliseconds

This serves as both a quick availability check and a diagnostic tool.

#### Welcome Message (`!welcome`)

The welcome command provides:
- An introduction to the bot's capabilities
- Quick-start information for new users
- Command examples for common tasks
- Links to additional resources

### Administrative Tools

The administrative module equips server administrators with tools to manage and configure the bot.

#### API Authentication (`!set_api_key`, `!set_jwt_token`, `!test_auth`)

These commands allow administrators to:
- Set or update the OpenWebUI API key without editing config files
- Configure JWT token authentication when needed
- Test authentication against the API to verify it's working
- Safely manage sensitive credentials through Discord's permissions system

The commands feature secure handling of credentials:
- Auto-deletion of messages containing secrets
- Masking of sensitive values in responses
- Updating of configuration files for persistence
- Immediate validation of new credentials

#### Environment Inspection (`!debug_env`)

The debug command provides administrators with:
- Current configuration values (with sensitive data masked)
- Environment variable status
- Network information for connectivity troubleshooting
- System status data for diagnosing issues

This information is delivered via DM for security.

### Channel Logging

The channel logging system provides a way to archive Discord channel content.

#### Configuration Management (`!reload_logger_config`, `!logger_status`)

These commands allow administrators to:
- Update channel logging settings without restarting the bot
- View which channels are currently being logged
- Check the status of media downloading (if enabled)
- Verify log file locations

#### Capabilities

The channel logger offers:
- Text logging with timestamps and user information
- Media downloading for attachments
- URL detection and content downloading
- Special handling for Tenor GIFs and other embedded content
- Organized storage with date-based directories

## Technical Architecture

### Codebase Organization

The Monolith bot is structured around a modular architecture that facilitates maintenance and extensibility:

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
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Docker configuration
└── Dockerfile               # Container definition
```

Each cog encapsulates a specific feature set, ensuring separation of concerns. The main bot module (`monolith_discord.py`) bootstraps the application, handles configuration loading, and establishes the bot's global behavior.

### Class Structure

#### MonolithBot Class

The `MonolithBot` class extends Discord.py's `commands.Bot` class with additional features:

```python
class MonolithBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_manager = ConfigManager(self)
        self.config = self.config_manager.load_config()
        # Validate critical config...
        
    async def setup_hook(self):
        # Load extensions...
        # Sync application commands...
        
    async def on_ready(self):
        # Setup presence...
        # Log connection info...
        
    async def on_command_error(self):
        # Handle global errors...
```

This design centralizes bot-wide functionality while delegating feature-specific behavior to the respective cogs.

#### Cog Structure

Each cog follows a consistent pattern:

```python
class FeatureCog(commands.Cog, name="Feature"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Initialize cog-specific state...
        
    # Command definitions...
    @commands.command(name="command_name")
    async def command_method(self, ctx: commands.Context, *args):
        # Command implementation...
        
    # Event listeners...
    @commands.Cog.listener()
    async def on_specific_event(self, *args):
        # Event handling...
        
    # Error handlers...
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Cog-specific error handling...

async def setup(bot: commands.Bot):
    await bot.add_cog(FeatureCog(bot))
```

This structure maintains clean separation between different feature sets while enabling seamless integration with the bot's core functionality.

### Error Handling System

Monolith implements a multi-layered error handling system:

1. **Command-level error handling**: Each command can define specific error handling logic
2. **Cog-level error handling**: Each cog has an `on_command_error` listener for cog-specific errors
3. **Global error handling**: The bot provides a global handler for unhandled errors
4. **Standardized error methods**: The `utils.py` module provides standardized error handling patterns

This ensures that errors are:
- Caught at the appropriate level
- Logged with sufficient context
- Presented to users in a friendly manner
- Handled according to their severity

### Configuration Management

The `ConfigManager` class provides a robust configuration system:

- **Source Hierarchy**: Environment variables, config files, and runtime settings
- **Validation**: Type checking and constraint validation for configuration values
- **Dynamic Updates**: Commands can update configuration at runtime
- **Persistence**: Changes can be saved to disk for restart survival
- **Security**: Sensitive values are masked in logs and user-facing output

The configuration system is designed to be flexible enough for development, testing, and production use cases.

### Rate Limiting

To prevent abuse and ensure fair resource usage, Monolith implements a sophisticated rate limiting system:

- **Per-User Tracking**: Limits are applied on a per-user basis
- **Command-Specific Limits**: Different commands can have different limit profiles
- **Dynamic Time Windows**: Rolling time windows rather than fixed periods
- **User Feedback**: Clear messaging when limits are exceeded
- **Administrative Override**: Administrators can reset limits when needed

## Setup and Deployment

### Environment Configuration

The bot can be configured through environment variables:

| Variable | Description | Required? | Default |
|----------|-------------|-----------|---------|
| DISCORD_TOKEN | Discord Bot Token | Yes | - |
| OPENWEBUI_API_URL | URL to OpenWebUI instance | For LLM features | - |
| OPENWEBUI_DEFAULT_MODEL | Default model to use | For LLM features | - |
| OPENWEBUI_API_KEY | API key for authentication | If API requires | - |
| OPENWEBUI_JWT_TOKEN | JWT token for authentication | If API requires | - |
| DOCS_ZIP_URL | URL to docs zip file | For docs features | https://github.com/open-webui/docs/archive/refs/heads/main.zip |
| DOCS_BASE_URL | Base URL for doc links | For docs features | https://docs.openwebui.com/ |
| DOCS_SUBDIR_IN_ZIP | Subdirectory in zip | For docs features | docs/ |

These can be set in a `.env` file for convenience.

### Local Installation

For local installation:

1. Clone the repository
2. Set up a Python virtual environment (3.12+ recommended)
3. Install dependencies from `requirements.txt`
4. Configure environment variables
5. Run `python monolith_discord.py`

The bot will initialize, load configurations, and connect to Discord.

### Docker Deployment

Docker deployment offers advantages in isolation, dependency management, and portability:

1. Build using the included Dockerfile:
   ```bash
   docker build -t monolith-discord-bot .
   ```

2. Or use docker-compose for a more complete setup:
   ```bash
   docker-compose up -d
   ```

The docker-compose configuration includes:
- Volume mapping for persistent data
- Environment variable configuration
- Networking setup for OpenWebUI connectivity
- Resource constraints to prevent container overload

### Data Persistence

The bot persists several types of data:

- **Channel Logs**: Stored in `./data/channel_logs/` by default
- **Downloaded Media**: Stored in `./data/channel_logs/media/` by default
- **Documentation Index**: SQLite database in the data directory
- **Configuration Changes**: Saved to config file if specified

For Docker deployments, these directories should be volume-mounted to persist between container restarts.

## API Integrations

### OpenWebUI API

The OpenWebUI integration uses the API's chat completions endpoints:

- Primary Endpoint: `/api/chat/completions`
- Alternative Endpoints (tried sequentially):
  - `/openai/chat/completions`
  - `/v1/chat/completions`
  - `/api/v1/chat/completions`
  - `/ollama/api/chat`
  - `/ollama/v1/chat/completions`

The bot supports two authentication methods:
- API Key authentication with header: `Authorization: Bearer <key>`
- JWT Token authentication with header: `Authorization: Bearer <token>`

Request Format:
```json
{
  "model": "model_name",
  "messages": [
    {"role": "user", "content": "prompt text"}
  ],
  "stream": false
}
```

For conversation context, previous messages are included in the messages array.

### Discord API

The bot leverages Discord.py to interact with Discord's API, utilizing:

- Message events for command processing
- Reaction events for interactive UI
- Embed objects for rich formatting
- View and UI component classes for interactive elements
- Channel and permission APIs for administrative functions

### YouTube API

The YouTube search functionality uses the youtube-search-python library, which:
- Provides a clean interface to YouTube's data
- Doesn't require YouTube API keys
- Returns structured information about videos
- Supports pagination and result limiting

### Ollama Model Repository

The Ollama model search feature scrapes ollama.com to retrieve model information:
- Uses aiohttp for asynchronous HTTP requests
- Employs BeautifulSoup for HTML parsing
- Extracts model metadata through selector patterns
- Formats and presents the data in Discord embeds

## Command Reference

### User Commands

#### OpenWebUI Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!ask` | `!ask <prompt>` | Send prompt to default model |
| `!ask` | `!ask <model> <prompt>` | Send prompt to specified model |
| `!openwebui_models` | `!openwebui_models` | List all available models |
| `!clear_chat` | `!clear_chat` | Reset conversation history |

#### Documentation Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!docs` | `!docs <query>` | Search documentation |

#### Model Search Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!osearch` | `!osearch <query>` | Search Ollama models |

#### Media Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!youtube` | `!youtube <query>` | Search YouTube videos |
| `!yt` | `!yt <query>` | Search YouTube (alias) |

#### Utility Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!ping` | `!ping` | Check bot latency |
| `!welcome` | `!welcome` | Show welcome message |
| `!help` | `!help [command]` | Show help for commands |

### Administrator Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `!set_api_key` | `!set_api_key <key>` | Set OpenWebUI API key |
| `!set_jwt_token` | `!set_jwt_token <token>` | Set OpenWebUI JWT token |
| `!test_auth` | `!test_auth` | Test API authentication |
| `!debug_env` | `!debug_env` | Show environment config |
| `!syncdocs` | `!syncdocs` | Manually sync documentation |
| `!reload_logger_config` | `!reload_logger_config` | Reload logger configuration |
| `!logger_status` | `!logger_status` | Show channel logging status |

## Development Guide

### Adding New Commands

To add a new command to an existing cog:

1. Define the command method with the appropriate decorator:
   ```python
   @commands.command(name="command_name", help="Command description")
   async def command_method(self, ctx: commands.Context, *args):
       # Command implementation
   ```

2. Add error handling for the command:
   ```python
   @command_method.error
   async def command_method_error(self, ctx: commands.Context, error: commands.CommandError):
       # Handle errors
   ```

3. Update the help system to include documentation for the new command.

4. Add appropriate logging for command actions.

### Creating New Cogs

To add a new feature module:

1. Create a new file in the `cogs/` directory:
   ```python
   # cogs/my_feature_cog.py
   import discord
   from discord.ext import commands
   import logging
   
   logger = logging.getLogger(__name__)
   
   class MyFeatureCog(commands.Cog, name="MyFeature"):
       def __init__(self, bot: commands.Bot):
           self.bot = bot
           logger.info("MyFeatureCog loaded.")
           
       # Commands...
       
       # Error handlers...
       
   async def setup(bot: commands.Bot):
       await bot.add_cog(MyFeatureCog(bot))
       logger.info("MyFeatureCog added to bot.")
   ```

2. Ensure your cog follows the established patterns for:
   - Error handling
   - Logging
   - Command naming conventions
   - Code style

3. Add any necessary dependencies to `requirements.txt`.

### Testing Guidelines

The project includes a test framework using pytest:

1. Create test files in the `tests/` directory matching the pattern `test_*.py`.

2. Use async fixtures for bot and cog instances:
   ```python
   @pytest.fixture
   async def bot():
       mock_bot = AsyncMock(spec=commands.Bot)
       mock_bot.config = {...}
       mock_bot.loop = asyncio.get_event_loop()
       return mock_bot
       
   @pytest.fixture
   async def cog(bot):
       return MyFeatureCog(bot)
   ```

3. Write test cases for command functionality:
   ```python
   @pytest.mark.asyncio
   async def test_command(cog, bot):
       # Setup
       ctx = AsyncMock(spec=commands.Context)
       # Test
       await cog.command_method(ctx, "test_arg")
       # Assert
       ctx.send.assert_called_once()
   ```

4. Run tests with pytest:
   ```bash
   pytest
   ```

### Contribution Workflow

1. Fork the repository

2. Create a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```

3. Make changes following the coding standards

4. Write appropriate tests for your changes

5. Submit a pull request with a clear description of the changes

## Troubleshooting

### Common Issues

#### Bot Doesn't Start

**Symptoms:**
- Error about missing Discord token
- Connection refused errors
- SSL/TLS errors

**Solutions:**
1. Verify `DISCORD_TOKEN` is set correctly
2. Check network connectivity to Discord
3. Ensure Python version is 3.12 or higher
4. Verify all required dependencies are installed

#### LLM Commands Fail

**Symptoms:**
- `!ask` commands return errors
- Authentication failures
- Timeout errors

**Solutions:**
1. Run `!diagnose_api` to check OpenWebUI connectivity
2. Verify API key or JWT token is set correctly
3. Check that specified models actually exist
4. Confirm the OpenWebUI instance is running and accessible

#### Documentation Search Issues

**Symptoms:**
- `!docs` command returns no results
- Index build errors
- Missing documentation content

**Solutions:**
1. Run `!syncdocs` to rebuild the documentation index
2. Check `DOCS_ZIP_URL` points to a valid documentation archive
3. Verify the documentation structure matches expected patterns
4. Check disk space for extracting and indexing documentation

### Diagnostic Tools

#### API Diagnostics

The `!diagnose_api` command provides comprehensive API testing:
1. Network connectivity tests
2. Authentication verification
3. Endpoint availability checks
4. Response format validation

#### Environment Inspection

The `!debug_env` command shows:
1. Configuration values (with sensitive data masked)
2. Environment variable status
3. Network information
4. System status data

#### Logger Status

The `!logger_status` command displays:
1. Which channels are being logged
2. Log file locations
3. Media download status
4. Format configuration

### Logs Interpretation

The bot produces structured logs with the format:
```
TIMESTAMP:LEVEL:LOGGER_NAME: MESSAGE
```

Common log prefixes:
- `__main__`: Core bot functionality
- `cogs.openwebui_cog`: OpenWebUI integration
- `cogs.documentation_cog`: Documentation features
- `discord.client`: Discord.py client events
- `aiohttp.client`: HTTP request logging

Critical issues to watch for:
- `CRITICAL` level messages (almost always fatal)
- `ERROR` messages with `Connection refused` (network issues)
- `ERROR` messages with `Authentication failed` (credential problems)
- `ERROR` messages with `Not Found` (API endpoint issues)

## Security Considerations

### API Key Management

The bot implements several security measures for API key handling:

1. **Memory-Only Option**: Keys can be kept only in memory without persistence
2. **Masked Logging**: Keys are never logged in full form
3. **Restricted Commands**: Key management commands require administrator permissions
4. **Message Deletion**: Messages containing keys are automatically deleted
5. **DM Responses**: Sensitive information is sent via DM when possible

### Permission System

The bot uses Discord's permission system to control access:

1. All administrative commands require the `Administrator` permission
2. Channel logging requires appropriate channel permissions
3. Command error handlers check permissions before executing
4. The help system shows only accessible commands to users

### Data Handling

The bot's data handling practices are designed to protect user information:

1. Conversation histories are ephemeral and expire after inactivity
2. Channel logs are stored according to admin configuration
3. No personal information beyond Discord IDs is stored
4. All stored data paths are configurable for security policies

## Appendices

### Configuration File Examples

#### Environment File (`.env`)

```
DISCORD_TOKEN=your_discord_token_here
OPENWEBUI_API_URL=http://localhost:3999
OPENWEBUI_DEFAULT_MODEL=llama3:latest
OPENWEBUI_API_KEY=your_api_key_here
DOCS_ZIP_URL=https://github.com/open-webui/docs/archive/refs/heads/main.zip
DOCS_BASE_URL=https://docs.openwebui.com/
DOCS_SUBDIR_IN_ZIP=docs/
```

#### Channel Logger Configuration

```json
{
  "log_directory": "./data/channel_logs",
  "log_format": "{timestamp} [{author_name} ({author_id})] {message_content}{attachments_info}",
  "download_media": true,
  "media_directory": "./data/channel_logs/media",
  "servers": {
    "123456789012345678": [
      "123456789012345679",
      "123456789012345680"
    ]
  }
}
```

#### Docker Compose Configuration

```yaml
services:
  monolith-discord-bot:
    container_name: monolith-discord-bot
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
      - ./channel_logger_config.json:/app/channel_logger_config.json
    environment:
      - 'DISCORD_TOKEN=${DISCORD_TOKEN}'
      - 'OPENWEBUI_API_URL=${OPENWEBUI_API_URL}'
      - 'OPENWEBUI_DEFAULT_MODEL=${OPENWEBUI_DEFAULT_MODEL}'
      - 'OPENWEBUI_API_KEY=${OPENWEBUI_API_KEY}'
      - 'PYTHONUNBUFFERED=1'
    restart: unless-stopped
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Advanced Usage Patterns

#### LLM Pattern for Detailed Explanations

```
!ask llama3:latest I need a detailed explanation of how transformer models work, including:
1. The attention mechanism
2. Positional encoding
3. Multi-head attention
4. Feed-forward networks
Please provide concrete examples where appropriate.
```

#### Documentation Search with Specific Filtering

```
!docs "API authentication" setup requirements
```

#### Combining Multiple Features

The bot's commands can be used together for powerful workflows:

1. Search for models:
   ```
   !osearch mistral
   ```

2. Check model availability:
   ```
   !openwebui_models
   ```

3. Ask the model a question:
   ```
   !ask mistral:latest Explain how you work
   ```

4. Look up related documentation:
   ```
   !docs mistral configuration
   ```

This combination enables a full exploration workflow without leaving Discord.