# ./cogs/help_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging

# Set up logger for this cog
logger = logging.getLogger(__name__)

class HelpCog(commands.Cog, name="Help"):
    """
    Custom help command system with categories and examples.
    Replaces the default help command with a more detailed version.
    """
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the Help cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
        # Remove the default help command
        self.bot.remove_command('help')
        logger.info("HelpCog loaded. Default help command removed.")
        
    @commands.group(invoke_without_command=True)
    async def help(self, ctx: Context, *, command_name: str = None):
        """
        Improved help command with categories and examples.
        
        Args:
            ctx: The command context
            command_name: Optional command or category name to get help for
        """
        prefix = ctx.prefix
        
        if command_name is None:
            # Show main help menu with categories
            embed = discord.Embed(
                title="Bot Help",
                description=f"Use `{prefix}help <category>` for more info on a category.\n"
                           f"Use `{prefix}help <command>` for more info on a command.",
                color=discord.Color.blue()
            )
            
            # Define categories
            categories = {
                "🧠 OpenWebUI": ["ask", "openwebui_models", "diagnose_api", "test_auth"],
                "📚 Documentation": ["docs", "syncdocs"],
                "🔍 Model Search": ["osearch"],
                "🎥 Media": ["youtube", "yt"],
                "⚙️ Utility": ["ping"],
                "🛡️ Admin": ["set_api_key", "set_jwt_token", "debug_env", "reload_logger_config"],
            }
            
            # Add fields for each category
            for category, commands_list in categories.items():
                command_text = ", ".join(f"`{prefix}{cmd}`" for cmd in commands_list)
                embed.add_field(name=category, value=command_text, inline=False)
                
            embed.set_footer(text="Tip: Type !help <command> for detailed help on a command")
            await ctx.send(embed=embed)
            
        else:
            # Check if it's a category
            categories = {
                "openwebui": "🧠 OpenWebUI",
                "documentation": "📚 Documentation",
                "modelsearch": "🔍 Model Search",
                "media": "🎥 Media",
                "utility": "⚙️ Utility", 
                "admin": "🛡️ Admin",
            }
            
            lowered = command_name.lower()
            
            if lowered in categories:
                await self.send_category_help(ctx, lowered, categories[lowered])
                return
            
            # It's a command, show specific help
            command = self.bot.get_command(command_name)
            
            if command is None:
                await ctx.send(f"❌ Command or category `{command_name}` not found.")
                return
                
            await self.send_command_help(ctx, command)
    
    async def send_category_help(self, ctx: Context, category_id: str, category_name: str):
        """
        Send help for a specific category.
        
        Args:
            ctx: The command context
            category_id: The category identifier
            category_name: The display name of the category
        """
        prefix = ctx.prefix
        embed = discord.Embed(
            title=f"{category_name} Commands",
            color=discord.Color.blue()
        )
        
        # Map category IDs to commands and their descriptions
        category_commands = {
            "openwebui": [
                ("ask", "Ask a question to the LLM", f"`{prefix}ask What is OpenWebUI?`\n`{prefix}ask llama3:latest Tell me a joke`"),
                ("openwebui_models", "List available models", f"`{prefix}openwebui_models`"),
                ("diagnose_api", "Test API connectivity", f"`{prefix}diagnose_api`"),
            ],
            "documentation": [
                ("docs", "Search documentation", f"`{prefix}docs installation`\n`{prefix}docs api reference`"),
                ("syncdocs", "Manually sync docs (admin)", f"`{prefix}syncdocs`"),
            ],
            "modelsearch": [
                ("osearch", "Search for Ollama models", f"`{prefix}osearch llama`\n`{prefix}osearch mistral`"),
            ],
            "media": [
                ("youtube", "Search YouTube", f"`{prefix}youtube openwebui tutorial`"),
                ("yt", "Shorthand for YouTube search", f"`{prefix}yt openwebui tutorial`"),
            ],
            "utility": [
                ("ping", "Check bot latency", f"`{prefix}ping`"),
                ("welcome", "Show bot introduction", f"`{prefix}welcome`"),
            ],
            "admin": [
                ("set_api_key", "Set OpenWebUI API key", f"`{prefix}set_api_key <key>`"),
                ("set_jwt_token", "Set OpenWebUI JWT token", f"`{prefix}set_jwt_token <token>`"),
                ("debug_env", "Show environment config", f"`{prefix}debug_env`"),
                ("reload_logger_config", "Reload channel logger config", f"`{prefix}reload_logger_config`"),
            ],
        }
        
        # Get commands for this category
        commands_info = category_commands.get(category_id, [])
        
        if not commands_info:
            embed.description = "No commands found for this category."
        else:
            for name, desc, example in commands_info:
                embed.add_field(
                    name=f"`{prefix}{name}`",
                    value=f"**Description:** {desc}\n**Example:**\n{example}",
                    inline=False
                )
                
        await ctx.send(embed=embed)
    
    async def send_command_help(self, ctx: Context, command: commands.Command):
        """
        Send help for a specific command.
        
        Args:
            ctx: The command context
            command: The command object to get help for
        """
        prefix = ctx.prefix
        
        embed = discord.Embed(
            title=f"Help: {prefix}{command.name}",
            color=discord.Color.blue()
        )
        
        # Add command description
        if command.help:
            embed.description = command.help
        else:
            embed.description = "No description available."
            
        # Add usage
        usage = f"{prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
        
        # Add aliases if any
        if command.aliases:
            aliases = ", ".join(f"`{prefix}{alias}`" for alias in command.aliases)
            embed.add_field(name="Aliases", value=aliases, inline=False)
            
        # Add examples (manually defined)
        examples = {
            "ask": f"`{prefix}ask What is OpenWebUI?`\n`{prefix}ask llama3:latest Explain quantum computing`",
            "docs": f"`{prefix}docs installation`\n`{prefix}docs api reference`",
            "osearch": f"`{prefix}osearch llama`\n`{prefix}osearch mistral`",
            "youtube": f"`{prefix}youtube openwebui tutorial`\n`{prefix}youtube how to setup ollama`",
            "yt": f"`{prefix}yt openwebui tutorial`\n`{prefix}yt how to setup ollama`",
            "ping": f"`{prefix}ping`",
            "welcome": f"`{prefix}welcome`",
            "set_api_key": f"`{prefix}set_api_key YOUR_API_KEY`",
            "set_jwt_token": f"`{prefix}set_jwt_token YOUR_JWT_TOKEN`",
            "debug_env": f"`{prefix}debug_env`",
            "openwebui_models": f"`{prefix}openwebui_models`",
            "diagnose_api": f"`{prefix}diagnose_api`",
            "syncdocs": f"`{prefix}syncdocs`",
            "reload_logger_config": f"`{prefix}reload_logger_config`",
        }
        
        if command.name in examples:
            embed.add_field(name="Examples", value=examples[command.name], inline=False)
            
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """
    Load the HelpCog into the bot.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(HelpCog(bot))
    logger.info("HelpCog added to bot.")