# ./monolith_discord.py

import discord
from discord.ext import commands
# Removed: from discord.ext.commands import Context (No longer needed here)
import os
import logging
import asyncio
import platform
from dotenv import load_dotenv
import pathlib
import sys # Added for sys.exit

# --- Configuration Loading ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
APP_CONFIG = {
    # Documentation Cog Settings
    "DOCS_ZIP_URL": os.getenv("DOCS_ZIP_URL"),
    "DOCS_BASE_URL": os.getenv("DOCS_BASE_URL"),
    "DOCS_PATH_IN_ZIP": os.getenv("DOCS_PATH_IN_ZIP", "docs-main/docs"), # Example default

    # OpenWebUI Cog Settings
    "OPENWEBUI_API_URL": os.getenv("OPENWEBUI_API_URL"),
    "OPENWEBUI_DEFAULT_MODEL": os.getenv("OPENWEBUI_DEFAULT_MODEL"),
    "OPENWEBUI_API_KEY": os.getenv("OPENWEBUI_API_KEY"),         # Added API Key loading
    "OPENWEBUI_JWT_TOKEN": os.getenv("OPENWEBUI_JWT_TOKEN"),     # Added JWT Token loading

    # Add any other global config or API keys here, for example:
    # "OLLAMA_API_URL": os.getenv("OLLAMA_API_URL"),
    # "SOME_OTHER_API_KEY": os.getenv("SOME_OTHER_API_KEY"),
}

# --- Logging Setup ---
# Configure root logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)-8s:%(name)-15s: %(message)s')
# Optionally silence excessively verbose library loggers
# logging.getLogger('discord.http').setLevel(logging.WARNING)
# logging.getLogger('discord.gateway').setLevel(logging.WARNING)
logger = logging.getLogger(__name__) # Logger for this main file

# --- Bot Definition ---
# Define intents required by the bot and its cogs
intents = discord.Intents.default()
intents.message_content = True # Needed for commands, potentially other cogs
intents.members = True       # Might be needed by some cogs

# Subclass Bot to easily add attributes like config
class MonolithBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = APP_CONFIG # Attach config to bot instance

bot = MonolithBot(command_prefix='!', intents=intents)

# --- Core Bot Events ---
@bot.event
async def on_ready():
    """Called when the bot is fully logged in and ready."""
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f"Discord.py version: {discord.__version__}")
    logger.info(f"Python version: {platform.python_version()}")
    logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
    logger.info(f"Connected to {len(bot.guilds)} guilds.")
    # Presence can be set here or in a dedicated cog
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the docs | !docs"))
    logger.info('------ Bot is Ready ------')

@bot.event
async def setup_hook():
    """Async setup hook called before on_ready. Ideal for loading cogs."""
    logger.info("Running setup_hook...")
    cogs_dir = pathlib.Path(__file__).parent / "cogs"
    logger.info(f"Attempting to load extensions from: {cogs_dir}")

    if not cogs_dir.is_dir():
        logger.warning(f"Cogs directory not found at {cogs_dir}. No extensions will be loaded.")
        return

    for filename in os.listdir(cogs_dir):
        # Load python files in the cogs directory, ignoring __init__.py and non-.py files
        if filename.endswith('.py') and filename != '__init__.py':
            extension = f'cogs.{filename[:-3]}'
            try:
                await bot.load_extension(extension)
                logger.info(f'Successfully loaded extension: {extension}')
            except commands.ExtensionNotFound:
                logger.error(f'Extension not found: {extension}')
            except commands.ExtensionAlreadyLoaded:
                logger.warning(f'Extension already loaded: {extension}')
            except commands.NoEntryPointError:
                logger.error(f'Extension {extension} has no setup function.')
            except commands.ExtensionFailed as e:
                # Log the original error that occurred within the cog's setup
                logger.error(f'Extension {extension} failed to load.', exc_info=e.original)
            except Exception as e:
                logger.error(f'Failed to load extension {extension}.', exc_info=True)

    logger.info("Finished loading extensions.")
    # Optional: Sync global commands if using slash commands
    # logger.info("Syncing global commands...")
    # await bot.tree.sync()
    # logger.info("Global commands synced.")

# --- Removed Ping Command ---
# The ping command is assumed to be moved to cogs/general_cog.py

# --- Optional: General Error Handler ---
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Basic error handler for commands not caught by cog listeners."""
    # Check if the cog has its own error handler
    if ctx.cog and ctx.cog.has_error_handler():
        return # Let the cog handle its own errors

    # Check if the command has its own error handler
    if hasattr(ctx.command, 'on_error'):
        return # Let the command handle its own errors

    # Extract the original error if it's wrapped
    original_error = getattr(error, 'original', error)

    # Ignore common check failures or specific handled errors silently
    if isinstance(original_error, (commands.CommandNotFound, commands.NotOwner)):
        logger.debug(f"Command error ignored: {type(original_error).__name__} in {ctx.channel} by {ctx.author}")
        return
    elif isinstance(original_error, commands.MissingPermissions):
        logger.warning(f"Missing permissions for command '{ctx.command.qualified_name}': {original_error.missing_permissions}")
        try:
             await ctx.send(f"Sorry {ctx.author.mention}, you don't have permission to use that command.", delete_after=10)
        except discord.Forbidden: pass
        return
    elif isinstance(original_error, commands.CheckFailure): # Other generic checks
        logger.warning(f"Check failed for command '{ctx.command.qualified_name}': {original_error}")
        try:
             await ctx.send(f"Sorry {ctx.author.mention}, you cannot run this command here.", delete_after=10)
        except discord.Forbidden: pass
        return

    # Log other errors more verbosely
    command_name = ctx.command.qualified_name if ctx.command else 'Unknown Command'
    logger.error(f"Unhandled error in command '{command_name}':", exc_info=error) # Log original wrapped error too

    # Inform user generically about unhandled errors
    try:
        await ctx.send(f"Oops! An unexpected error occurred while running `{command_name}`. Please contact an admin if this persists.")
    except discord.Forbidden:
        logger.warning(f"Cannot send error message in channel {ctx.channel.id} due to permissions.")


# --- Main Execution ---
if __name__ == "__main__":
    # Validate essential config
    if not TOKEN:
        logger.critical("FATAL: DISCORD_TOKEN environment variable not set!")
        sys.exit(1)
    # Configuration for cogs (like URLs) is generally checked within the cog's __init__ now

    # Run the bot
    try:
        logger.info("Starting bot...")
        # Use our root logger config, don't let discord.py interfere
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("FATAL: Login failed. Check if DISCORD_TOKEN is valid.")
    except Exception as e:
        logger.critical(f"FATAL: An error occurred during bot execution:", exc_info=True)
        sys.exit(1) # Exit if the bot fails critically during startup/run