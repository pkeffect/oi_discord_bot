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

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))
    logger.info("GeneralCog added to bot.")