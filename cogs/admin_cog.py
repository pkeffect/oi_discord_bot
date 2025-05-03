# ./cogs/admin_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging

# Set up logger for this cog
logger = logging.getLogger(__name__)

class AdminCog(commands.Cog, name="Admin"):
    """
    Administrative commands for bot management.
    Provides commands for configuration, debugging, and maintenance.
    """

    def __init__(self, bot: commands.Bot):
        """
        Initialize the Admin cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
        logger.info("AdminCog loaded.")

    @commands.command(name='set_config', help='(Admin Only) Set a configuration value')
    @commands.has_permissions(administrator=True)
    async def set_config(self, ctx: Context, key: str, *, value: str):
        """
        Dynamically update a configuration value.
        
        Args:
            ctx: The command context
            key: The configuration key to set
            value: The value to set
        """
        if not hasattr(self.bot, 'config_manager'):
            await ctx.send("❌ Configuration manager not available.")
            return
        
        # Create a whitelist of allowed config keys to prevent security issues
        allowed_keys = [
            "openwebui_default_model",
            "docs_base_url",
            # Add other safe keys as needed
        ]
        
        if key not in allowed_keys:
            await ctx.send(f"❌ Cannot modify config key `{key}`. Only the following keys can be changed dynamically: {', '.join(allowed_keys)}")
            return
        
        try:
            # Handle special types
            if value.lower() == "true":
                parsed_value = True
            elif value.lower() == "false":
                parsed_value = False
            elif value.isdigit():
                parsed_value = int(value)
            elif value.replace('.', '', 1).isdigit() and value.count('.') == 1:
                parsed_value = float(value)
            else:
                parsed_value = value
            
            # Update config
            self.bot.config_manager.set(key, parsed_value, save=True)
            
            # Also update bot.config for backward compatibility
            self.bot.config[key] = parsed_value
            
            await ctx.send(f"✅ Configuration key `{key}` set to `{parsed_value}`.")
            
            # Notify cogs about config change
            if hasattr(self.bot, "dispatch"):
                self.bot.dispatch("config_update", key, parsed_value)
            
        except Exception as e:
            logger.error(f"Error setting configuration value: {e}", exc_info=True)
            await ctx.send(f"❌ Error setting configuration: {e}")

    @commands.command(name='reload_config', help='(Admin Only) Reload configuration from file')
    @commands.has_permissions(administrator=True)
    async def reload_config(self, ctx: Context):
        """
        Reload configuration from the config file.
        
        Args:
            ctx: The command context
        """
        if not hasattr(self.bot, 'config_manager'):
            await ctx.send("❌ Configuration manager not available.")
            return
        
        try:
            # Remember the file path
            config_file = self.bot.config_manager.config_file_path
            
            if not config_file:
                await ctx.send("❌ No config file was used for initial loading.")
                return
            
            # Reload configuration
            self.bot.config_manager.load_config(config_file)
            
            # Update bot.config reference
            self.bot.config = self.bot.config_manager.config
            
            await ctx.send(f"✅ Configuration reloaded from {config_file}.")
            
            # Notify cogs about config reload
            if hasattr(self.bot, "dispatch"):
                self.bot.dispatch("config_reload")
            
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}", exc_info=True)
            await ctx.send(f"❌ Error reloading configuration: {e}")

    @commands.Cog.listener()
    async def on_config_update(self, key: str, value):
        """
        Handle dynamic configuration updates.
        
        Args:
            key: The configuration key that was updated
            value: The new value
        """
        logger.info(f"Configuration updated: {key} = {value}")
        
        # You can add specific handling for different keys here
        # This example just logs the change, but you could trigger
        # specific behavior based on which config value changed


async def setup(bot: commands.Bot):
    """
    Load the AdminCog into the bot.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(AdminCog(bot))
    logger.info("AdminCog added to bot.")