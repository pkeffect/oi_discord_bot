# ./cogs/documentation_cog.py

import logging
import os
import zipfile
import aiohttp
import aiosqlite
import discord
from discord.ext import commands
from discord.ext.commands import Context
import asyncio
import pathlib
from urllib.parse import urljoin
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup, NavigableString
import time
import shutil
from typing import Dict, List, Optional, Tuple, Any, Union

# Set up logger for this cog
logger = logging.getLogger(__name__)

# Helper Functions
def extract_title_from_markdown(content: str, fallback_filename: str) -> str:
    """
    Extract a title from markdown content, either from frontmatter or first heading.
    
    Args:
        content: Markdown content to extract title from
        fallback_filename: Filename to use as fallback if no title is found
        
    Returns:
        str: The extracted title or fallback
    """
    try:
        if content.startswith('---'):
            end_marker = content.find('---', 3)
            if end_marker != -1:
                front_matter = content[3:end_marker]
                for line in front_matter.splitlines():
                    if line.startswith('title:'):
                        return line.split(':', 1)[1].strip().strip("'\"")
        lines = content.splitlines()
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('# '):
                return line_stripped[2:].strip()
    except Exception as e: 
        logger.warning(f"Title parse error for {fallback_filename}: {e}")
    return fallback_filename.replace('-', ' ').replace('_', ' ').title()

def generate_doc_url(relative_path_from_docs_source: str, base_url: str) -> str:
    """
    Generate a documentation URL from relative path and base URL.
    
    Args:
        relative_path_from_docs_source: Relative path from docs source
        base_url: Base URL for documentation
        
    Returns:
        str: The generated URL
    """
    if not base_url.endswith('/'): 
        base_url += '/'
    path_part = relative_path_from_docs_source.strip('/').replace('\\', '/')
    is_index = False
    if path_part.lower().endswith('/index.md'):
        path_part = path_part[:-len('index.md')]
        is_index = True
    elif path_part.lower() == 'index.md':
        path_part = ''
        is_index = True
    elif path_part.lower().endswith('.md'):
        path_part = path_part[:-len('.md')]
    final_url = urljoin(base_url, path_part)
    if is_index and path_part and not final_url.endswith('/'):
        final_url += '/'
    return final_url

def extract_structured_content(markdown_content: str, md_parser: MarkdownIt) -> Dict[str, str]:
    """
    Extract structured content from markdown for searching.
    
    Args:
        markdown_content: Markdown content to extract from
        md_parser: MarkdownIt parser instance
        
    Returns:
        Dict containing structured content sections
    """
    content_parts = {'h1': [], 'h2': [], 'other_headings': [], 'bold': [], 'body': []}
    processed_elements = set()
    try:
        html_content = md_parser.render(markdown_content)
        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove unwanted blocks first
        for code_block in soup.find_all(['pre', 'code']):
            for element in code_block.descendants: 
                processed_elements.add(element)
            code_block.decompose()
        # Extract structured content
        headings_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] 
        bold_tags = ['strong', 'b']
        for tag_name in headings_tags:
            for tag in soup.find_all(tag_name):
                text = tag.get_text(separator=' ', strip=True)
                if text:
                    key = tag_name if tag_name in ['h1', 'h2'] else 'other_headings'
                    content_parts[key].append(text)
                    for element in tag.descendants: 
                        processed_elements.add(element)
        for tag_name in bold_tags:
            for tag in soup.find_all(tag_name):
                if tag.find_parent(headings_tags): 
                    continue
                text = tag.get_text(separator=' ', strip=True)
                if text:
                    content_parts['bold'].append(text)
                    for element in tag.descendants: 
                        processed_elements.add(element)
        # Extract remaining body content
        for text_node in soup.find_all(string=True):
            if text_node in processed_elements or text_node.parent in processed_elements: 
                continue
            if text_node.parent.name in ['script', 'style', 'nav', 'footer', 'header', 'aside']:
                processed_elements.add(text_node)
                continue
            text = text_node.strip()
            if text: 
                content_parts['body'].append(text)
            processed_elements.add(text_node)
        # Join lists
        result = {k: ' '.join(v) for k, v in content_parts.items()}
        return result
    except Exception as e:
        logger.error(f"Error extracting structured content: {e}", exc_info=True)
        return {'h1': '', 'h2': '', 'other_headings': '', 'bold': '', 'body': ''}


class DocumentationCog(commands.Cog, name="Documentation"):
    """
    Handles documentation fetching, indexing, and searching.
    Provides commands to search documentation and manage documentation sync.
    """

    def __init__(self, bot: commands.Bot):
        """
        Initialize the Documentation cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
        # Access config attached to the bot instance
        self.config = getattr(bot, 'config', {})
        self.docs_zip_url = self.config.get("DOCS_ZIP_URL")
        self.docs_base_url = self.config.get("DOCS_BASE_URL")
        self.docs_path_in_zip = self.config.get("DOCS_PATH_IN_ZIP")
        
        # Define paths relative to the main app directory
        self.app_dir = pathlib.Path(__file__).parent.parent
        self.data_dir = self.app_dir / "data"
        self.docs_dir = self.data_dir / "extracted_docs"
        self.zip_path = self.data_dir / "docs.zip"
        self.db_path = self.data_dir / "docs_index.db"

        self.md_parser = MarkdownIt()
        
        # Cache settings
        self.cache_durations = {
            "search": 300,      # 5 minutes for search results
        }
        
        # Cache storages
        self.search_cache = {}
        self.timestamp_cache = {}

        # Validate required config
        if not all([self.docs_zip_url, self.docs_base_url, self.docs_path_in_zip]):
            logger.critical("Documentation Cog is missing required configuration! Disabling background tasks.")
            # Cancel the task if config is bad - it won't run before_loop either
        else:
            # Start the background task - before_loop will run first
            self.sync_docs_task.start()
            logger.info("DocumentationCog loaded and sync task scheduled.")

    # --- Cache Methods ---
    def _cache_key(self, query: str, limit: int = 5) -> str:
        """
        Generate a cache key for a search query.
        
        Args:
            query: The search query
            limit: The result limit
            
        Returns:
            str: The cache key
        """
        return f"{query}::{limit}"
    
    def _is_cache_valid(self, cache_key: str, cache_type: str = "search") -> bool:
        """
        Check if a cached item is still valid based on its timestamp.
        
        Args:
            cache_key: The cache key to check
            cache_type: The type of cache
            
        Returns:
            bool: True if the cache is valid, False otherwise
        """
        if cache_key not in self.timestamp_cache:
            return False
            
        timestamp = self.timestamp_cache[cache_key]
        max_age = self.cache_durations.get(cache_type, 300)
        return (time.time() - timestamp) < max_age
    
    def _cache_set(self, cache_key: str, value: Any, cache_type: str = "search") -> None:
        """
        Store an item in the appropriate cache with timestamp.
        
        Args:
            cache_key: The cache key
            value: The value to cache
            cache_type: The type of cache
        """
        if cache_type == "search":
            self.search_cache[cache_key] = value
        
        self.timestamp_cache[cache_key] = time.time()
    
    def _cache_get(self, cache_key: str, cache_type: str = "search") -> Any:
        """
        Retrieve a cached item if it exists and is valid.
        
        Args:
            cache_key: The cache key
            cache_type: The type of cache
            
        Returns:
            The cached value, or None if not found or invalid
        """
        if not self._is_cache_valid(cache_key, cache_type):
            return None
            
        if cache_type == "search":
            return self.search_cache.get(cache_key)
        
        return None
    
    def _cache_invalidate(self, cache_type: Optional[str] = None) -> None:
        """
        Invalidate all caches or a specific cache type.
        
        Args:
            cache_type: The type of cache to invalidate, or None for all
        """
        if cache_type == "search":
            self.search_cache.clear()
            # Also remove timestamps for this cache type
            for key in list(self.timestamp_cache.keys()):
                if key.endswith("::search"):
                    del self.timestamp_cache[key]
        elif cache_type is None:
            # Invalidate all caches
            self.search_cache.clear()
            self.timestamp_cache.clear()

    # --- Database Methods ---
    async def initialize_database(self) -> None:
        """
        Creates the necessary directories and DB tables for this cog.
        """
        self.data_dir.mkdir(exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            # Table schema
            await db.execute('''
                CREATE TABLE IF NOT EXISTS docs_meta (
                    filepath TEXT PRIMARY KEY, title TEXT, url TEXT UNIQUE,
                    h1_content TEXT, h2_content TEXT, other_headings TEXT,
                    bold_content TEXT, body_content TEXT
                )''')
            await db.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS docs_content USING fts5(
                    title, h1_content, h2_content, other_headings, bold_content, body_content,
                    content='docs_meta', content_rowid='rowid'
                )''')
            # Triggers
            await db.execute('''CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs_meta BEGIN INSERT INTO docs_content (rowid, title, h1_content, h2_content, other_headings, bold_content, body_content) VALUES (new.rowid, new.title, new.h1_content, new.h2_content, new.other_headings, new.bold_content, new.body_content); END;''')
            await db.execute('''CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs_meta BEGIN DELETE FROM docs_content WHERE rowid=old.rowid; END;''')
            await db.execute('''CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs_meta BEGIN UPDATE docs_content SET rowid=new.rowid, title=new.title, h1_content=new.h1_content, h2_content=new.h2_content, other_headings=new.other_headings, bold_content=new.bold_content, body_content=new.body_content WHERE rowid=old.rowid; END;''')
            await db.commit()
            logger.info(f"Documentation DB initialized/verified at {self.db_path}")

    async def clear_database(self) -> None:
        """
        Clears the documentation meta table for this cog.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM docs_meta")
            await db.commit()
            logger.info("Cleared Documentation DB (docs_meta cleared, FTS handled by trigger).")

    # --- Indexing Method ---
    async def index_docs(self) -> bool:
        """
        Finds, parses, and indexes documentation files.
        
        Returns:
            bool: True if indexing was successful, False otherwise
        """
        logger.info("Starting documentation indexing...")
        index_successful = False
        try:
            await self.clear_database()
            if not self.docs_dir.exists():
                logger.error(f"Docs extraction directory {self.docs_dir} not found.")
                return False

            search_root = (self.docs_dir / self.docs_path_in_zip).resolve()
            logger.info(f"Using documentation search root: {search_root}")
            if not search_root.is_dir():
                logger.error(f"Indexing failed: Search root '{search_root}' is not a directory.")
                return False

            docs_meta_to_insert = []
            count, indexed_count = 0, 0
            for md_file in search_root.rglob('*.md'):
                count += 1
                try:
                    relative_path = str(md_file.relative_to(search_root)).replace('\\', '/')
                    content = await self.bot.loop.run_in_executor(None, md_file.read_text, 'utf-8')
                    structured_data = extract_structured_content(content, self.md_parser)
                    filename_base = md_file.stem
                    title = extract_title_from_markdown(content, filename_base)
                    if not title and structured_data['h1']: 
                        title = structured_data['h1'].split('\n')[0]
                    url = generate_doc_url(relative_path, self.docs_base_url)
                    docs_meta_to_insert.append((
                        relative_path, title, url,
                        structured_data['h1'], structured_data['h2'], structured_data['other_headings'],
                        structured_data['bold'], structured_data['body']
                    ))
                    indexed_count += 1
                except UnicodeDecodeError: 
                    logger.warning(f"Skipping {md_file} due to non-UTF-8 encoding.")
                except Exception as e: 
                    logger.error(f"Failed processing {md_file}: {e}", exc_info=False)

            logger.info(f"Scanned {count} markdown files. Processing {indexed_count} for indexing.")
            if not docs_meta_to_insert:
                logger.warning("No documents found/processed to index.")
                return True

            async with aiosqlite.connect(self.db_path) as db:
                try:
                    await db.execute("BEGIN TRANSACTION;")
                    await db.executemany("""INSERT OR REPLACE INTO docs_meta (filepath, title, url, h1_content, h2_content, other_headings, bold_content, body_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", docs_meta_to_insert)
                    await db.commit()
                    logger.info(f"Successfully indexed {len(docs_meta_to_insert)} documents.")
                    index_successful = True
                except aiosqlite.Error as e: 
                    await db.rollback()
                    logger.error(f"DB error during indexing: {e}", exc_info=True)
                except Exception as e: 
                    await db.rollback()
                    logger.error(f"Unexpected DB error: {e}", exc_info=True)
            
            # Invalidate search cache when docs are reindexed
            if index_successful:
                self._cache_invalidate("search")
                
            return index_successful
        except Exception as e: 
            logger.error(f"Unexpected error in index_docs: {e}", exc_info=True)
            return False

    # --- Search Method ---
    async def search_documentation(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Searches the FTS index across structured fields with caching.
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of dictionaries containing search results
        """
        cache_key = self._cache_key(query, limit)
        cached_results = self._cache_get(cache_key, "search")
        
        if cached_results is not None:
            logger.info(f"Using cached results for search query '{query}' (limit: {limit})")
            return cached_results
        
        search_query = query.strip()
        if " " in search_query and not (search_query.startswith('"') and search_query.endswith('"')):
            search_query = f'"{search_query}"'
        logger.info(f"Executing FTS search for: '{search_query}' (original: '{query}')")
        results = []
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Snippet from body_content (index 5)
                cursor = await db.execute(
                    f"""SELECT dm.title, dm.url, snippet(docs_content, 5, '**', '**', '...', 25) as snippet
                       FROM docs_content dc JOIN docs_meta dm ON dc.rowid = dm.rowid
                       WHERE dc.docs_content MATCH ? ORDER BY rank LIMIT ?""",
                    (search_query, limit))
                rows = await cursor.fetchall()
                results = [{"title": r[0], "url": r[1], "snippet": r[2]} for r in rows if r[2] and r[2] != '...']
                if len(rows) > 0 and len(results) == 0:
                    logger.info(f"Query '{search_query}' matched non-body fields, no snippet generated.")
                logger.info(f"Found {len(results)} results with snippets for query '{search_query}'")
            except aiosqlite.Error as e: 
                logger.error(f"DB search error: {e}", exc_info=True)
                
        # Cache the results before returning
        self._cache_set(cache_key, results, "search")
        return results

    # --- Background Task ---
    @commands.tasks.loop(hours=6)
    async def sync_docs_task(self) -> None:
        """
        Cog's background task for syncing documentation.
        Runs periodically to download, extract, and index documentation.
        """
        logger.info("Starting scheduled documentation sync run...")
        # 1. Download
        download_ok = False
        zip_content = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.docs_zip_url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()
                    zip_content = await response.read()
                    self.data_dir.mkdir(exist_ok=True)
                    with open(self.zip_path, 'wb') as f: 
                        f.write(zip_content)
                    logger.info(f"Docs ZIP saved to {self.zip_path}")
                    download_ok = True
        except Exception as e: 
            logger.error(f"Download failed in scheduled run: {e}", exc_info=False)
        if not download_ok: 
            return

        # 2. Extract
        extract_ok = False
        try:
            if self.docs_dir.is_dir(): 
                await self.bot.loop.run_in_executor(None, shutil.rmtree, self.docs_dir)
            elif self.docs_dir.exists(): 
                await self.bot.loop.run_in_executor(None, os.remove, self.docs_dir)
            self.docs_dir.mkdir(exist_ok=True)
            def extract_sync():
                with zipfile.ZipFile(self.zip_path, 'r') as zr: 
                    zr.extractall(self.docs_dir)
            await self.bot.loop.run_in_executor(None, extract_sync)
            logger.info(f"Extraction complete into {self.docs_dir}.")
            extract_ok = True
        except Exception as e: 
            logger.error(f"Extraction failed in scheduled run: {e}", exc_info=False)
        if not extract_ok: 
            return

        # 3. Index
        try:
            success = await self.index_docs()
            if success: 
                logger.info("Scheduled sync indexing completed successfully.")
            else: 
                logger.error("Scheduled sync indexing failed, see previous errors.")
        except Exception as e: 
            logger.error(f"Failed during indexing step in scheduled run: {e}", exc_info=True)

    @sync_docs_task.before_loop
    async def before_sync_docs_task(self) -> None:
        """
        Runs once before the task loop starts its first execution.
        Sets up the database and waits for the bot to be ready.
        """
        logger.info("Running pre-sync setup actions...")
        await self.bot.wait_until_ready()
        await self.initialize_database()
        logger.info("Pre-sync setup complete. Loop will now start its first run when scheduled.")

    # --- Commands ---
    @commands.command(name='docs', help='Searches the documentation. Usage: !docs <search query>')
    async def docs_command(self, ctx: Context, *, query: Optional[str] = None):
        """
        Searches the documentation and displays results.
        
        Args:
            ctx: The command context
            query: The search query
        """
        if not query: 
            await ctx.send("Usage: `!docs <search query>`")
            return
            
        logger.info(f"Docs search from {ctx.author} for: '{query}'")
        async with ctx.typing():
            try:
                results = await self.search_documentation(query, limit=5)
                if not results: 
                    await ctx.send(f"Sorry, no documents found matching '{query}'.")
                    return
                    
                embed = discord.Embed(title=f"Search Results for '{query}'", color=discord.Color.blue())
                description_parts = []
                for i, res in enumerate(results):
                    title_escaped = discord.utils.escape_markdown(res['title'])
                    snippet_text = res.get('snippet')
                    if snippet_text and snippet_text != '...':
                        snippet_clean = snippet_text.replace('\n', ' ').strip()
                        snippet_escaped = discord.utils.escape_markdown(snippet_clean)
                        snippet_final = snippet_escaped.replace(discord.utils.escape_markdown('**'), '**')
                        display_snippet = f"> {snippet_final}"
                    else: 
                        display_snippet = "> *Match found in title or heading.*"
                    entry = f"{i+1}. **[{title_escaped}]({res['url']})**\n{display_snippet}\n"
                    description_parts.append(entry)
                    
                full_description = "".join(description_parts)
                if len(full_description) > 4096: 
                    full_description = full_description[:4090] + "\n*...results truncated.*"
                embed.description = full_description
                
                footer_text = f"Found {len(results)} result(s)." + (" Showing top 5." if len(results) == 5 else "")
                embed.set_footer(text=footer_text)
                
                await ctx.send(embed=embed)
            except Exception as e: 
                logger.error(f"Error processing !docs command for '{query}': {e}", exc_info=True)
                await ctx.send("An error occurred while searching.")

    @commands.command(name='syncdocs', help='Manually trigger documentation sync (Admin only).')
    @commands.is_owner()
    async def sync_docs_manual(self, ctx: Context):
        """
        Manually triggers documentation sync.
        
        Args:
            ctx: The command context
        """
        logger.info(f"Manual sync triggered by {ctx.author} (ID: {ctx.author.id}).")
        await ctx.send("🔄 Starting manual sync... This runs the sync logic immediately.")
        async with ctx.typing():
            try:
                # Directly call the sync logic, not the loop management function
                await self.sync_docs_task.__call__()
                await ctx.send("✅ Manual sync process finished. Check logs for success/failure details.")
            except Exception as e:
                logger.error(f"Manual sync failed: {e}", exc_info=True)
                await ctx.send(f"❌ Manual sync failed. Check logs.\nError: {e}")

    # --- Cog Specific Error Handler ---
    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError):
        """
        Handles errors specific to commands within this Cog.
        
        Args:
            ctx: The command context
            error: The error that occurred
        """
        # Handle NotOwner error specifically for the syncdocs command in this cog
        if isinstance(error, commands.NotOwner) and ctx.command == self.sync_docs_manual:
            await ctx.send("Sorry, only the bot owner can use the `syncdocs` command.")
            return # Error handled locally

        # Log other errors that occurred within this cog's commands
        if ctx.cog == self:
            # Check if it's a command invocation error to log the original traceback
            log_traceback = isinstance(error, commands.CommandInvokeError)
            logger.error(f"Error in command '{ctx.command.qualified_name if ctx.command else 'Unknown'}': {error}", exc_info=log_traceback)
        # Let the main bot error handler deal with other cases or generic messages


async def setup(bot: commands.Bot):
    """
    Load the DocumentationCog into the bot.
    
    Args:
        bot: The bot instance
    """
    await bot.add_cog(DocumentationCog(bot))
    logger.info("DocumentationCog added to bot.")