# ./command_standards.py

"""
Command naming standards and categories for Monolith Discord Bot.
Used to ensure consistent naming and grouping of commands across cogs.
"""

# Command Categories
CATEGORIES = {
    "OPENWEBUI": {
        "name": "OpenWebUI",
        "emoji": "🧠",
        "description": "Interact with the OpenWebUI LLM service"
    },
    "DOCUMENTATION": {
        "name": "Documentation",
        "emoji": "📚",
        "description": "Search and manage documentation"
    },
    "MODEL_SEARCH": {
        "name": "Model Search",
        "emoji": "🔍",
        "description": "Find and explore available models"
    },
    "MEDIA": {
        "name": "Media",
        "emoji": "🎥",
        "description": "Search for media content"
    },
    "UTILITY": {
        "name": "Utility",
        "emoji": "⚙️",
        "description": "Core bot functions and utilities"
    },
    "ADMIN": {
        "name": "Admin",
        "emoji": "🛡️",
        "description": "Administrative commands (restricted)"
    },
    "LOGGING": {
        "name": "Logging",
        "emoji": "📝",
        "description": "Channel logging functions"
    }
}

# Command Name Standards with Categories
COMMANDS = {
    # OpenWebUI Commands
    "ask": {
        "category": "OPENWEBUI",
        "aliases": ["chat", "llm"],
        "description": "Ask a question to the configured LLM"
    },
    "list_models": {
        "category": "OPENWEBUI",
        "aliases": ["models", "openwebui_models"],
        "description": "List available models from OpenWebUI"
    },
    "clear_chat": {
        "category": "OPENWEBUI",
        "aliases": ["reset_chat"],
        "description": "Clear your conversation history"
    },
    "diagnose_api": {
        "category": "OPENWEBUI",
        "aliases": ["api_check"],
        "description": "Run diagnostics on the OpenWebUI API connection"
    },
    
    # Documentation Commands
    "docs": {
        "category": "DOCUMENTATION",
        "aliases": ["doc", "search_docs"],
        "description": "Search through the documentation"
    },
    "syncdocs": {
        "category": "DOCUMENTATION",
        "aliases": ["update_docs"],
        "description": "Manually trigger documentation sync (admin only)"
    },
    
    # Model Search Commands
    "osearch": {
        "category": "MODEL_SEARCH",
        "aliases": ["ollama_search", "search_models"],
        "description": "Search for models on ollama.com"
    },
    
    # Media Commands
    "youtube": {
        "category": "MEDIA",
        "aliases": ["yt"],
        "description": "Search YouTube and get top results"
    },
    
    # Utility Commands
    "ping": {
        "category": "UTILITY",
        "aliases": [],
        "description": "Check the bot's latency to Discord"
    },
    "welcome": {
        "category": "UTILITY",
        "aliases": ["start", "intro"],
        "description": "Show introduction and available commands"
    },
    "help": {
        "category": "UTILITY",
        "aliases": [],
        "description": "Show help information for commands"
    },
    
    # Admin Commands
    "set_api_key": {
        "category": "ADMIN",
        "aliases": [],
        "description": "Set OpenWebUI API key (admin only)"
    },
    "set_jwt_token": {
        "category": "ADMIN",
        "aliases": [],
        "description": "Set OpenWebUI JWT token (admin only)"
    },
    "test_auth": {
        "category": "ADMIN",
        "aliases": ["check_auth"],
        "description": "Test API authentication (admin only)"
    },
    "debug_env": {
        "category": "ADMIN",
        "aliases": ["show_config"],
        "description": "Show environment configuration (admin only)"
    },
    
    # Logging Commands
    "reload_logger_config": {
        "category": "LOGGING",
        "aliases": ["reload_log_config"],
        "description": "Reload channel logger configuration (admin only)"
    },
    "logger_status": {
        "category": "LOGGING",
        "aliases": ["log_status"],
        "description": "Show which channels are being logged"
    }
}

def get_commands_by_category(category_id: str):
    """Get all commands in a specific category."""
    return {name: cmd for name, cmd in COMMANDS.items() if cmd["category"] == category_id}

def get_category_info(category_id: str):
    """Get info about a category."""
    return CATEGORIES.get(category_id, None)

def get_command_info(command_name: str):
    """Get info about a command by its name."""
    return COMMANDS.get(command_name, None)

def get_command_by_alias(alias: str):
    """Find a command by its alias."""
    for name, cmd in COMMANDS.items():
        if alias in cmd["aliases"] or alias == name:
            return name, cmd
    return None, None