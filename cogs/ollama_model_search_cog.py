# ./cogs/ollama_model_search_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup # For HTML parsing
import urllib.parse # For URL encoding the query
import re # For finding stats possibly
from typing import List, Dict, Optional

# --- Cog Specific Logger ---
logger = logging.getLogger(__name__) # Logger name: 'cogs.ollama_model_search_cog'

# --- Constants ---
BASE_SEARCH_URL = "https://ollama.com/search"
BASE_OLLAMA_URL = "https://ollama.com" # For joining relative links
MAX_RESULTS_TO_SHOW = 5 # Limit how many results we display to avoid spam
REQUEST_TIMEOUT = 15 # Seconds to wait for the website response
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36" # Mimic a browser

class OllamaModelSearchCog(commands.Cog, name="OllamaSearch"):
    """Searches for models on ollama.com via web scraping."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        # Start background task to create session
        self.bot.loop.create_task(self.initialize_session())
        logger.info("OllamaModelSearchCog initialized.")

    async def initialize_session(self):
        """Creates the aiohttp session."""
        self._session = aiohttp.ClientSession(headers={'User-Agent': USER_AGENT})
        logger.info("aiohttp session for Ollama search initialized.")

    async def cog_unload(self):
        """Clean up the session when the cog is unloaded."""
        if self._session:
            await self._session.close()
            logger.info("aiohttp session closed.")

    async def _fetch_search_page(self, query: str) -> Optional[str]:
        """Fetches the HTML content of the search results page."""
        if not self._session or self._session.closed:
            logger.error("aiohttp session not ready or closed.")
            return None

        encoded_query = urllib.parse.quote_plus(query)
        search_url = f"{BASE_SEARCH_URL}?q={encoded_query}"
        logger.info(f"Fetching search results from: {search_url}")

        try:
            async with self._session.get(search_url, timeout=REQUEST_TIMEOUT) as response:
                logger.debug(f"Received status code {response.status} from {search_url}")
                response.raise_for_status() # Raise exception for bad status codes (4xx, 5xx)
                html_content = await response.text()
                logger.info(f"Successfully fetched HTML content (length: {len(html_content)}) for query '{query}'")
                return html_content
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching search results for '{query}' from {search_url}")
            return None
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error fetching search results for '{query}': Status {e.status}, Message: {e.message}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Client error fetching search results for '{query}': {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error fetching search results for '{query}': {e}")
            return None

    def _parse_search_results(self, html_content: str) -> List[Dict[str, str]]:
        """
        Parses the HTML to extract model information using updated selectors
        based on the provided search results page HTML (as of 2024-05-03).
        """
        if not html_content:
            logger.warning("HTML content provided to parser was empty.")
            return []

        logger.debug("Parsing HTML content with BeautifulSoup...")
        try:
            # Use lxml if available, otherwise html.parser
            try:
                 soup = BeautifulSoup(html_content, 'lxml')
            except ImportError:
                 logger.warning("lxml parser not found, falling back to html.parser.")
                 soup = BeautifulSoup(html_content, 'html.parser')

            results = []

            # --- Corrected Selectors based on provided HTML ---
            # Find all list items representing a search result
            result_containers = soup.find_all('li', attrs={'x-test-model': ''})

            logger.info(f"Found {len(result_containers)} potential result container elements (li[x-test-model]).")
            if not result_containers:
                 logger.warning("The primary selector (li[x-test-model]) did not find any result containers. Check selector or page structure.")

            for container in result_containers:
                model_data = {}
                try:
                    # Find the main link within the list item
                    link_tag = container.find('a', class_='group', href=True) # Ensure href exists
                    if not link_tag:
                         logger.warning("Skipping container, could not find primary link tag (a.group).")
                         continue

                    link = link_tag.get('href')
                    model_data['link'] = urllib.parse.urljoin(BASE_OLLAMA_URL, link)

                    # Find the name within the link's h2/span structure
                    name_span = link_tag.find('span', attrs={'x-test-search-response-title': ''})
                    if name_span:
                         full_name = name_span.text.strip()
                         if '/' in full_name:
                              # Handle names like 'author/modelname'
                              model_data['author'], model_data['name'] = full_name.split('/', 1)
                         else:
                              # Handle names like 'modelname' (assume library)
                              model_data['name'] = full_name
                              model_data['author'] = 'library'
                    else:
                        logger.warning(f"Could not find name span (span[x-test-search-response-title]) within link: {link}")
                        # Fallback using link path
                        parsed_link = urlparse(link)
                        path_parts = [p for p in parsed_link.path.split('/') if p]
                        if len(path_parts) >= 1:
                             model_data['name'] = path_parts[-1] # Use last part as name
                             # Try to guess author from path if possible
                             if len(path_parts) > 1 and path_parts[0] != 'library':
                                 model_data['author'] = path_parts[0]
                             elif len(path_parts) > 2 and path_parts[0] == 'library':
                                  model_data['author'] = path_parts[1] # e.g. /library/author/model
                             else:
                                  model_data['author'] = 'library' # Default if structure unknown
                        else:
                             logger.warning(f"Could not reliably determine name for {link}. Skipping.")
                             continue

                    # Find the description paragraph within the link
                    # The class seems consistent based on your HTML
                    desc_tag = link_tag.find('p', class_='max-w-lg')
                    model_data['description'] = desc_tag.text.strip() if desc_tag else "No description found."

                    # Find the stats paragraph within the link
                    stats_container = link_tag.find('p', class_='text-neutral-500')
                    pulls = "N/A"
                    tags_count = "N/A"
                    updated = "N/A"
                    if stats_container:
                        # Extract specific stats using the x-test attributes
                        pulls_span = stats_container.find('span', attrs={'x-test-pull-count': ''})
                        tags_span = stats_container.find('span', attrs={'x-test-tag-count': ''})
                        updated_span = stats_container.find('span', attrs={'x-test-updated': ''})

                        if pulls_span: pulls = pulls_span.text.strip()
                        if tags_span: tags_count = tags_span.text.strip()
                        if updated_span: updated = updated_span.text.strip()

                        logger.debug(f"Extracted Stats - Pulls: {pulls}, Tags: {tags_count}, Updated: {updated}")
                    else:
                         logger.warning(f"Could not find stats container (p.text-neutral-500) for model {model_data.get('name', 'N/A')}")

                    model_data['pulls'] = pulls
                    model_data['tags_count'] = tags_count
                    model_data['updated'] = updated
                    # --- End of Corrected Selectors ---

                    results.append(model_data)
                    logger.debug(f"Successfully parsed model: {model_data.get('author')}/{model_data.get('name')}")
                    if len(results) >= MAX_RESULTS_TO_SHOW: # Stop parsing early
                        logger.info(f"Reached max results ({MAX_RESULTS_TO_SHOW}). Stopping parse.")
                        break

                except Exception as e:
                    # Log error for specific card but continue with others
                    logger.warning(f"Error parsing individual model card for link {model_data.get('link', 'N/A')}: {e}", exc_info=False)
                    continue # Skip this card

            logger.info(f"Finished parsing. Extracted {len(results)} models.")
            return results

        except Exception as e:
            logger.exception(f"Critical error parsing HTML content: {e}")
            return [] # Return empty list on major parsing error


    @commands.command(name="osearch", aliases=["ollama_search"], help="Search for models on ollama.com.\nUsage: !osearch <model name>")
    async def osearch(self, ctx: Context, *, query: str | None = None):
        """Searches ollama.com for models and displays results."""
        if not query:
            await ctx.send(f"Please provide a search query.\nUsage: `{ctx.prefix}osearch <model name>`")
            return

        logger.info(f"Received search request from {ctx.author} (ID: {ctx.author.id}) for query: '{query}'")
        async with ctx.typing():
            html_content = await self._fetch_search_page(query)

            if html_content is None: # Check for None explicitly
                await ctx.send(f"❌ Sorry, failed to fetch search results for '{query}'. The website might be down, blocking requests, or the session isn't ready.")
                return
            if not html_content: # Check for empty string (less likely but possible)
                await ctx.send(f"❌ Received empty content from search page for '{query}'.")
                return


            results = self._parse_search_results(html_content)

            if not results:
                 # Distinguish between parsing failure and genuine no results
                 if len(html_content) > 1000: # Arbitrary check: if we got significant HTML, parsing likely failed
                      logger.warning(f"Parsing failed to find results for '{query}' despite receiving HTML content.")
                      await ctx.send(f"ℹ️ Could not parse any models matching '{query}' on ollama.com. The website structure might have changed, or the selectors need updating.")
                 else: # If HTML was very short or parsing yielded nothing from a valid structure
                      logger.info(f"No models found matching '{query}' after parsing.")
                      await ctx.send(f"ℹ️ No models found matching '{query}' on ollama.com.")
                 return

            # Format results into an embed
            search_page_url = f"{BASE_SEARCH_URL}?q={urllib.parse.quote_plus(query)}"
            embed = discord.Embed(
                title=f"Ollama Model Search Results for '{query}'",
                description=f"Showing top {len(results)} results from [ollama.com/search]({search_page_url}).",
                color=discord.Color.blue()
            )

            for model in results:
                # Construct name, handle potential missing author/name after parsing
                author = model.get('author', 'library')
                name_part = model.get('name', 'Unknown')
                display_name = f"{author}/{name_part}"

                link = model.get('link') or "#" # Link or fallback
                description = model.get('description', 'N/A')
                pulls = model.get('pulls', 'N/A')
                tags = model.get('tags_count', 'N/A')
                updated = model.get('updated', 'N/A')

                field_value = (
                    f"{description}\n"
                    f"**Pulls:** {pulls} | **Tags:** {tags} | **Updated:** {updated}"
                )
                # Ensure field value doesn't exceed Discord limits
                if len(field_value) > 1024:
                     field_value = field_value[:1020] + "..."

                embed.add_field(name=f"[{display_name}]({link})", value=field_value, inline=False)


            embed.set_footer(text=f"Found {len(results)} results (displaying top {min(len(results), MAX_RESULTS_TO_SHOW)}). Scraped from ollama.com.")

            try:
                await ctx.send(embed=embed)
                logger.info(f"Successfully sent search results for '{query}' to channel {ctx.channel.id}")
            except discord.HTTPException as e:
                 logger.error(f"Failed to send search results embed: {e}")
                 await ctx.send("❌ Error: Could not display search results (message too long or other Discord error).")


    # --- Error Handling ---
    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError):
        """Handles errors specific to commands within this Cog."""
        if ctx.cog is not self or not ctx.command: return

        log_prefix = f"Cog '{self.qualified_name}' - Command '{ctx.command.qualified_name}':"

        if isinstance(error, commands.MissingRequiredArgument):
             logger.info(f"{log_prefix} Missing argument: {error.param.name}")
             await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `{ctx.prefix}help {ctx.command.qualified_name}` for usage.")
        elif isinstance(error, commands.CommandInvokeError):
             original = error.original
             logger.error(f"{log_prefix} Error during invocation: {original.__class__.__name__}: {original}", exc_info=True)
             await ctx.send(f"An unexpected error occurred while running the command: `{original.__class__.__name__}`. Please check logs.")
        else:
            # Log other errors but maybe don't notify user unless critical
            logger.error(f"{log_prefix} Unexpected error: {error}", exc_info=True)


# --- Setup Function ---
async def setup(bot: commands.Bot):
    """Loads the OllamaModelSearchCog."""
    # Ensure necessary libraries are available
    try:
         import bs4
         # import lxml # Check for preferred parser is done inside parse function now
    except ImportError as e:
         logger.critical(f"CRITICAL: Missing required library 'BeautifulSoup4' for OllamaModelSearchCog: {e}. Install with 'pip install beautifulsoup4'. Cog will not load.")
         # Prevent loading if bs4 is missing entirely
         raise commands.ExtensionFailed("OllamaModelSearchCog", f"Missing dependency: {e}") from e

    await bot.add_cog(OllamaModelSearchCog(bot))
    logger.info("OllamaModelSearch Cog loaded successfully.")