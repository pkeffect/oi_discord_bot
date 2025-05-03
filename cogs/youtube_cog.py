# ./cogs/youtube_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging
from youtubesearchpython import VideosSearch # Import the library
import asyncio

# --- Cog Specific Logger ---
logger = logging.getLogger(__name__) # Logger name: 'cogs.youtube_cog'

class YouTubeCog(commands.Cog, name="YouTube Search"):
    """Provides commands to search YouTube."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("YouTubeCog loaded.")

    def sync_youtube_search(self, query: str, limit: int = 3) -> dict | None: # Request 3 results
        """Synchronous helper function to perform the YouTube search."""
        try:
            # Limit results
            search = VideosSearch(query, limit=limit)
            results = search.result() # This performs the synchronous search
            return results
        except Exception as e:
            logger.error(f"youtube-search-python error for query '{query}': {e}", exc_info=True)
            return None # Return None on error

    @commands.command(name='youtube', aliases=['yt'], help='Searches YouTube for videos. Usage: !yt <search query>')
    async def youtube_search(self, ctx: Context, *, query: str | None = None):
        """Searches YouTube and returns the top 3 video results in an embed."""
        if not query:
            await ctx.send("Please provide something to search for! Usage: `!yt <search query>`")
            return

        logger.info(f"YouTube search requested by {ctx.author} for: '{query}'")

        async with ctx.typing():
            try:
                # Run the synchronous search function in an executor thread, requesting 3 results
                loop = asyncio.get_running_loop()
                search_results = await loop.run_in_executor(
                    None, # Use default executor
                    self.sync_youtube_search, # Function to run
                    query, # Argument for the function
                    3 # Limit argument for the function
                )

                if not search_results or not search_results.get('result'):
                    await ctx.send(f"Sorry, couldn't find any YouTube results for '{query}'.")
                    return

                results_list = search_results['result']

                # --- Create Embed ---
                embed = discord.Embed(
                    title=f"YouTube Search Results for '{query}'",
                    color=discord.Color.red() # Use YouTube Red
                )

                description_parts = []
                thumbnail_url = None # To store the first video's thumbnail

                for i, video in enumerate(results_list):
                    video_title = video.get('title', 'Unknown Title')
                    video_link = video.get('link', None)
                    channel_name = video.get('channel', {}).get('name', 'Unknown Channel')
                    duration = video.get('duration', '')
                    # published_time = video.get('publishedTime', '') # Optional

                    # Escape potential markdown characters
                    title_escaped = discord.utils.escape_markdown(video_title)
                    channel_escaped = discord.utils.escape_markdown(channel_name)

                    # Add entry to description
                    description_line = f"{i+1}. **[{title_escaped}]({video_link})**"
                    metadata = []
                    if channel_escaped: metadata.append(f"Channel: {channel_escaped}")
                    if duration: metadata.append(f"Duration: {duration}")
                    # if published_time: metadata.append(f"Published: {published_time}")
                    if metadata:
                        description_line += f"\n   *({', '.join(metadata)})*" # Add metadata on next line, italicized

                    description_parts.append(description_line)

                    # Get thumbnail URL from the first result only
                    if i == 0:
                        thumbnails = video.get('thumbnails', [])
                        if thumbnails:
                            # youtube-search-python usually provides multiple sizes.
                            # The first one is typically smallest (default). Use that.
                            thumbnail_url = thumbnails[0].get('url', None)
                            # Clean up URL parameters sometimes added
                            if thumbnail_url and '?' in thumbnail_url:
                                thumbnail_url = thumbnail_url.split('?')[0]

                # Set the description
                embed.description = "\n\n".join(description_parts) # Add blank line between results

                # Set the thumbnail (if found for the first result)
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)
                else:
                     logger.warning(f"Could not find thumbnail for first YT result of '{query}'")

                embed.set_footer(text=f"Found {len(results_list)} result(s).")

                await ctx.send(embed=embed)


            except Exception as e:
                logger.error(f"Error processing !yt command for query '{query}': {e}", exc_info=True)
                await ctx.send("An error occurred while searching YouTube. Please try again later.")

# --- Setup Function ---
# Required for discord.py to load the cog
async def setup(bot: commands.Bot):
    await bot.add_cog(YouTubeCog(bot))
    # Main file logs loading success