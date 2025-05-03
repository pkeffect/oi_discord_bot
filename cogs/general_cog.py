# ./cogs/general_cog.py
import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging

logger = logging.getLogger(__name__)

class GeneralCog(commands.Cog, name="General"):
    """General purpose commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("GeneralCog loaded.")

    @commands.command(name='ping', help='Checks bot latency.')
    async def ping(self, ctx: Context):
        """Checks bot latency to Discord."""
        latency = self.bot.latency * 1000 # Access bot via self.bot
        await ctx.send(f'Pong! 🏓 ({latency:.2f}ms)')

    # You can add other general commands here later (help, info, etc.)

# In cogs/general_cog.py - Add an onboarding command

@commands.command(name='welcome', aliases=['start', 'intro'])
async def welcome_command(self, ctx):
    """Provides an introduction to the bot and its features."""
    prefix = ctx.prefix
    
    welcome_embed = discord.Embed(
        title="👋 Welcome to Monolith Discord Bot for OpenWebUI!",
        description="I'm here to help you interact with OpenWebUI and provide useful information. Here's a quick tour of what I can do:",
        color=discord.Color.blue()
    )
    
    # Add sections for different features
    welcome_embed.add_field(
        name="🧠 Talking to LLMs",
        value=f"Use `{prefix}ask <prompt>` to talk to the default LLM model.\n"
             f"Or specify a model with `{prefix}ask llama3:latest <prompt>`.\n"
             f"Check available models with `{prefix}openwebui_models`.",
        inline=False
    )
    
    welcome_embed.add_field(
        name="📚 Documentation Search",
        value=f"Search the OpenWebUI documentation with `{prefix}docs <query>`.\n"
             f"For example: `{prefix}docs installation`",
        inline=False
    )
    
    welcome_embed.add_field(
        name="🔍 Finding Models",
        value=f"Search for Ollama models with `{prefix}osearch <query>`.\n"
             f"For example: `{prefix}osearch llama`",
        inline=False
    )
    
    welcome_embed.add_field(
        name="🎥 YouTube Search",
        value=f"Find videos with `{prefix}yt <query>`.\n"
             f"For example: `{prefix}yt openwebui tutorial`",
        inline=False
    )
    
    welcome_embed.add_field(
        name="⚙️ Getting Help",
        value=f"Use `{prefix}help` to see all commands.\n"
             f"Or `{prefix}help <command>` for details on a specific command.",
        inline=False
    )
    
    # Create a button to link to documentation
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Visit Documentation",
        url="https://docs.openwebui.com/",
        style=discord.ButtonStyle.link
    ))
    
    await ctx.send(embed=welcome_embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
    logger.info("GeneralCog added to bot.")