# ./monolith_discord.py

import discord
from discord.ext import commands
import os
import logging
import platform
from dotenv import load_dotenv
import pathlib
import sys
from typing import Optional

# --- Configuration Loading ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
APP_CONFIG = {
    # Documentation Cog Settings
    "DOCS_ZIP_URL": os.getenv("DOCS_ZIP_URL"),
    "DOCS_BASE_URL": os.getenv("DOCS_BASE_URL"),
    "DOCS_PATH_IN_ZIP": os.getenv("DOCS_PATH_IN_ZIP", "docs-main/docs"),

    # OpenWebUI Cog Settings
    "OPENWEBUI_API_URL": os.getenv("OPENWEBUI_API_URL"),
    "OPENWEBUI_DEFAULT_MODEL": os.getenv("OPENWEBUI_DEFAULT_MODEL"),
    "OPENWEBUI_API_KEY": os.getenv("OPENWEBUI_API_KEY"),
    "OPENWEBUI_JWT_TOKEN": os.getenv("OPENWEBUI_JWT_TOKEN"),

    # Ollama Settings
    "OLLAMA_API_URL": os.getenv("OLLAMA_API_URL"),
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)-8s:%(name)-15s: %(message)s')
logger = logging.getLogger(__name__)

# --- Bot Definition ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MonolithBot(commands.Bot):
    """
    Custom bot class with additional configuration and utilities.
    Extends discord.py's Bot class with project-specific functionality.
    """
    def __init__(self, *args, **kwargs):
        """Initialize the bot with configuration and settings."""
        super().__init__(*args, **kwargs)
        self.config = APP_CONFIG
        
    async def setup_hook(self):
        """
        Async setup hook called before on_ready.
        Loads extensions and syncs application commands.
        """
        logger.info("Running setup_hook...")
        
        # Load extensions from cogs directory
        cogs_dir = pathlib.Path(__file__).parent / "cogs"
        logger.info(f"Attempting to load extensions from: {cogs_dir}")

        if not cogs_dir.is_dir():
            logger.warning(f"Cogs directory not found at {cogs_dir}. No extensions will be loaded.")
            return

        for filename in os.listdir(cogs_dir):
            # Skip non-python files and __init__.py
            if not filename.endswith('.py') or filename == '__init__.py':
                continue
                
            # Skip test files that might be in the cogs directory
            if filename.startswith('test_'):
                logger.info(f"Skipping test file: {filename}")
                continue
                
            extension = f'cogs.{filename[:-3]}'
            try:
                await self.load_extension(extension)
                logger.info(f'Successfully loaded extension: {extension}')
            except commands.ExtensionNotFound:
                logger.error(f'Extension not found: {extension}')
            except commands.ExtensionAlreadyLoaded:
                logger.warning(f'Extension already loaded: {extension}')
            except commands.NoEntryPointError:
                logger.error(f'Extension {extension} has no setup function.')
            except commands.ExtensionFailed as e:
                logger.error(f'Extension {extension} failed to load.', exc_info=e.original)
            except Exception as e:
                logger.error(f'Failed to load extension {extension}.', exc_info=True)

        logger.info("Finished loading extensions.")
        
        # Sync application commands
        logger.info("Syncing application commands...")
        await self.tree.sync()
        logger.info("Application commands synced.")
        
    async def on_ready(self):
        """Called when the bot is fully logged in and ready."""
        logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')
        logger.info(f"Discord.py version: {discord.__version__}")
        logger.info(f"Python version: {platform.python_version()}")
        logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        logger.info(f"Connected to {len(self.guilds)} guilds.")
        
        # Set bot presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, 
                name="the docs | !docs"
            )
        )
        logger.info('------ Bot is Ready ------')

# Create bot instance with command prefix and intents
bot = MonolithBot(command_prefix='!', intents=intents)

# --- Global Error Handler ---
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """
    Global error handler for commands not caught by cog-specific handlers.
    
    Args:
        ctx: The command context
        error: The error raised during command execution
    """
    # Check if the cog has its own error handler
    if ctx.cog and hasattr(ctx.cog, 'cog_command_error'):
        return  # Let the cog handle its own errors

    # Check if the command has its own error handler
    if hasattr(ctx.command, 'on_error'):
        return  # Let the command handle its own errors

    # Extract the original error if it's wrapped
    original_error = getattr(error, 'original', error)

    # Handle specific error types
    if isinstance(original_error, (commands.CommandNotFound, commands.NotOwner)):
        logger.debug(f"Command error ignored: {type(original_error).__name__} in {ctx.channel} by {ctx.author}")
        return
    elif isinstance(original_error, commands.MissingPermissions):
        logger.warning(f"Missing permissions for command '{ctx.command.qualified_name if ctx.command else 'Unknown'}': {original_error.missing_permissions}")
        try:
            await ctx.send(f"Sorry {ctx.author.mention}, you don't have permission to use that command.", delete_after=10)
        except discord.Forbidden:
            pass
        return
    elif isinstance(original_error, commands.CheckFailure):
        logger.warning(f"Check failed for command '{ctx.command.qualified_name if ctx.command else 'Unknown'}': {original_error}")
        try:
            await ctx.send(f"Sorry {ctx.author.mention}, you cannot run this command here.", delete_after=10)
        except discord.Forbidden:
            pass
        return

    # Log other errors more verbosely
    command_name = ctx.command.qualified_name if ctx.command else 'Unknown Command'
    logger.error(f"Unhandled error in command '{command_name}':", exc_info=error)

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

    # Run the bot
    try:
        logger.info("Starting bot...")
        # Use our root logger config, don't let discord.py interfere
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        logger.critical("FATAL: Login failed. Check if DISCORD_TOKEN is valid.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"FATAL: An error occurred during bot execution:", exc_info=True)
        sys.exit(1)