# In cogs/admin_cog.py - Add dynamic config commands

@commands.command(name='set_config', help='(Admin Only) Set a configuration value')
@commands.has_permissions(administrator=True)
async def set_config(self, ctx, key: str, *, value: str):
    """Dynamically update a configuration value."""
    if not hasattr(self.bot, 'config_manager'):
        await ctx.send("❌ Configuration manager not available.")
        return
    
    # Create a whitelist of allowed config keys to prevent security issues
    allowed_keys = [
        "openwebui_default_model",
        "docs_base_url",
        # Add other safe keys
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
        await ctx.send(f"❌ Error setting configuration: {e}")

@commands.command(name='reload_config', help='(Admin Only) Reload configuration from file')
@commands.has_permissions(administrator=True)
async def reload_config(self, ctx):
    """Reload configuration from the config file."""
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
        await ctx.send(f"❌ Error reloading configuration: {e}")

# In OpenWebUICog - Add event listener for config changes
@commands.Cog.listener()
async def on_config_update(self, key, value):
    """Handle dynamic configuration updates."""
    if key == "openwebui_api_url":
        self.api_base_url = value
        logger.info(f"Updated API base URL to {value}")
    elif key == "openwebui_default_model":
        self.default_model = value
        logger.info(f"Updated default model to {value}")
    # Handle other relevant keys