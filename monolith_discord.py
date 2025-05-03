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
from config_manager import ConfigManager

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)-8s:%(name)-15s: %(message)s')
logger = logging.getLogger(__name__)

# --- Load environment variables ---
load_dotenv()

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
        
        # Initialize ConfigManager
        self.config_manager = ConfigManager(self)
        self.config = self.config_manager.load_config()
        
        # Validate critical config
        if not self.config.get("discord_token"):
            logger.critical("FATAL: Discord token not found in configuration!")
            sys.exit(1)
        
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

def setup_logging():
    """Configure logging to both console and file."""
    # Create logs directory if it doesn't exist
    logs_dir = pathlib.Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Determine the log filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"bot_{timestamp}.log"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler with colorized output
    console_handler = logging.StreamHandler()
    console_format = '%(asctime)s:%(levelname)-8s:%(name)-15s: %(message)s'
    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_format = '%(asctime)s:%(levelname)-8s:%(name)-15s: %(message)s'
    file_handler.setFormatter(logging.Formatter(file_format))
    root_logger.addHandler(file_handler)
    
    # Set specific logging levels for noisy modules
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    return log_file

# Call setup_logging at the beginning of main execution
log_file = setup_logging()
logger = logging.getLogger(__name__)
logger.info(f"Logging to console and file: {log_file}")

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
    # Initialize the bot
    bot = MonolithBot(command_prefix='!', intents=intents)
    
    # Run the bot
    try:
        logger.info("Starting bot...")
        # Use our root logger config, don't let discord.py interfere
        bot.run(bot.config.get("discord_token"), log_handler=None)
    except discord.LoginFailure:
        logger.critical("FATAL: Login failed. Check if DISCORD_TOKEN is valid.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"FATAL: An error occurred during bot execution:", exc_info=True)
        sys.exit(1)