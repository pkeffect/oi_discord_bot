# ./cogs/documentation_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging
import os
import io
import re
import zipfile
import aiohttp
import aiosqlite
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Union
import frontmatter
import time

# Set up logger for this cog
logger = logging.getLogger(__name__)

def extract_title_from_markdown(content: str, fallback_filename: str = "Untitled") -> str:
    """
    Extract title from markdown content.
    Tries to extract from frontmatter first, then from first heading.
    
    Args:
        content: Markdown content
        fallback_filename: Fallback filename to use if no title found
        
    Returns:
        str: Extracted title or formatted fallback
    """
    # Try to extract from frontmatter
    try:
        parsed = frontmatter.loads(content)
        if 'title' in parsed.metadata:
            return parsed.metadata['title']
    except Exception as e:
        logger.debug(f"Error parsing frontmatter: {e}")
    
    # Try to extract from first heading
    heading_match = re.search(r'^#\s+(.*?)$', content, re.MULTILINE)
    if heading_match:
        return heading_match.group(1).strip()
    
    # Use formatted fallback if no title found
    formatted_fallback = ' '.join(word.capitalize() for word in fallback_filename.replace('-', ' ').replace('_', ' ').split())
    return formatted_fallback

def generate_doc_url(filepath: str, base_url: str) -> str:
    """
    Generate a documentation URL from a file path.
    
    Args:
        filepath: Path to the markdown file
        base_url: Base URL for the documentation
        
    Returns:
        str: Generated documentation URL
    """
    # Normalize path separators and remove .md extension
    normalized_path = filepath.replace('\\', '/').rstrip('/')
    if normalized_path.endswith('.md'):
        normalized_path = normalized_path[:-3]
    
    # Special handling for index files
    if normalized_path.endswith('/index') or normalized_path == 'index':
        normalized_path = normalized_path[:-5] if normalized_path.endswith('/index') else ''
        return f"{base_url.rstrip('/')}/{normalized_path}/"
    
    # Regular files
    return f"{base_url.rstrip('/')}/{normalized_path}"

class DocumentationCog(commands.Cog, name="Documentation"):
    """
    Provides commands for searching and managing documentation.
    Downloads, indexes, and enables search through documentation files.
    """
    
    def __init__(self, bot: commands.Bot):
        """
        Initialize the Documentation cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
        self.app_dir = Path(os.getcwd())
        self.data_dir = self.app_dir / "data"
        self.docs_dir = self.app_dir / "extracted_docs"
        self.zip_path = self.app_dir / "docs.zip"
        self.db_path = self.app_dir / "data" / "docs_index.db"
        
        # Create necessary directories
        self.data_dir.mkdir(exist_ok=True)
        self.docs_dir.mkdir(exist_ok=True)
        
        # Get config from bot
        self.docs_zip_url = bot.config.get("docs_zip_url", "https://github.com/open-webui/docs/archive/refs/heads/main.zip")
        self.docs_base_url = bot.config.get("docs_base_url", "https://docs.openwebui.com/")
        self.docs_path_in_zip = bot.config.get("docs_subdir_in_zip", "docs/")
        
        # Initialize database
        self.bot.loop.create_task(self.initialize_database())
        
        # Start a background task to sync docs
        self.sync_docs_task = self.bot.loop.create_task(self.auto_sync_docs())
        
        logger.info("DocumentationCog initialized")
    
    async def cog_unload(self) -> None:
        """
        Clean up tasks when the cog is unloaded.
        """
        if hasattr(self, 'sync_docs_task') and self.sync_docs_task:
            self.sync_docs_task.cancel()
            logger.info("Docs sync task cancelled")
    
    async def initialize_database(self) -> None:
        """
        Initialize the SQLite database for documentation search.
        Creates necessary tables if they don't exist.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Create metadata table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS docs_meta (
                        id INTEGER PRIMARY KEY,
                        filepath TEXT UNIQUE,
                        title TEXT,
                        url TEXT,
                        h1_content TEXT,
                        h2_content TEXT,
                        other_headings TEXT,
                        bold_content TEXT,
                        body_content TEXT,
                        last_updated INTEGER
                    )
                """)
                
                # Create FTS (Full-Text Search) table
                await db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS docs_content USING fts5(
                        filepath, title, h1_content, h2_content, other_headings, 
                        bold_content, body_content, url,
                        content=docs_meta, content_rowid=id
                    )
                """)
                
                # Create a trigger to update FTS when main table is updated
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS docs_meta_ai AFTER INSERT ON docs_meta BEGIN
                        INSERT INTO docs_content(rowid, filepath, title, h1_content, h2_content, 
                                               other_headings, bold_content, body_content, url) 
                        VALUES (new.id, new.filepath, new.title, new.h1_content, new.h2_content, 
                               new.other_headings, new.bold_content, new.body_content, new.url);
                    END;
                """)
                
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS docs_meta_ad AFTER DELETE ON docs_meta BEGIN
                        DELETE FROM docs_content WHERE rowid = old.id;
                    END;
                """)
                
                await db.execute("""
                    CREATE TRIGGER IF NOT EXISTS docs_meta_au AFTER UPDATE ON docs_meta BEGIN
                        UPDATE docs_content SET
                            filepath = new.filepath,
                            title = new.title,
                            h1_content = new.h1_content,
                            h2_content = new.h2_content,
                            other_headings = new.other_headings,
                            bold_content = new.bold_content,
                            body_content = new.body_content,
                            url = new.url
                        WHERE rowid = old.id;
                    END;
                """)
                
                await db.commit()
                logger.info("Database initialized successfully at: %s", self.db_path)
        
        except Exception as e:
            logger.error("Error initializing database: %s", e, exc_info=True)
    
    async def auto_sync_docs(self) -> None:
        """
        Background task to periodically sync documentation.
        """
        try:
            # Wait a bit before first sync to allow bot to connect
            await asyncio.sleep(10)
            
            # Do initial sync
            await self.sync_docs()
            
            # Then sync every 24 hours
            while True:
                await asyncio.sleep(24 * 60 * 60)  # 24 hours
                logger.info("Running scheduled docs sync")
                await self.sync_docs()
        
        except asyncio.CancelledError:
            logger.info("Auto-sync docs task cancelled")
        except Exception as e:
            logger.error("Error in auto-sync docs task: %s", e, exc_info=True)
    
    async def download_docs_zip(self) -> bool:
        """
        Download documentation ZIP file.
        
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            logger.info("Downloading documentation ZIP from: %s", self.docs_zip_url)
            async with aiohttp.ClientSession() as session:
                async with session.get(self.docs_zip_url) as response:
                    if response.status != 200:
                        logger.error("Failed to download docs ZIP: HTTP %d", response.status)
                        return False
                    
                    content = await response.read()
                    with open(self.zip_path, 'wb') as f:
                        f.write(content)
                    
                    logger.info("Documentation ZIP downloaded successfully (%d bytes)", len(content))
                    return True
        
        except Exception as e:
            logger.error("Error downloading docs ZIP: %s", e, exc_info=True)
            return False
    
    async def extract_docs_zip(self) -> bool:
        """
        Extract documentation ZIP file.
        
        Returns:
            bool: True if extraction successful, False otherwise
        """
        try:
            if not self.zip_path.exists():
                logger.error("ZIP file not found at: %s", self.zip_path)
                return False
            
            # Clear existing directory
            if self.docs_dir.exists():
                shutil.rmtree(self.docs_dir)
            self.docs_dir.mkdir(exist_ok=True)
            
            logger.info("Extracting documentation ZIP to: %s", self.docs_dir)
            
            # Extract in a separate thread to avoid blocking
            await asyncio.to_thread(self._extract_zip)
            
            logger.info("Documentation ZIP extracted successfully")
            return True
        
        except Exception as e:
            logger.error("Error extracting docs ZIP: %s", e, exc_info=True)
            return False
    
    def _extract_zip(self) -> None:
        """
        Synchronous helper to extract the ZIP file.
        """
        with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
            # Get the root directory in the ZIP
            root_dirs = {name.split('/')[0] for name in zip_ref.namelist() if '/' in name}
            if len(root_dirs) == 1:
                root_dir = next(iter(root_dirs))
                
                # Check if docs_path_in_zip exists in the root directory
                if any(name.startswith(f"{root_dir}/{self.docs_path_in_zip}") for name in zip_ref.namelist()):
                    logger.info("Found docs subdirectory: %s/%s", root_dir, self.docs_path_in_zip)
                    docs_prefix = f"{root_dir}/{self.docs_path_in_zip}"
                else:
                    docs_prefix = root_dir
                
                # Extract files
                for file in zip_ref.namelist():
                    if file.startswith(docs_prefix) and file.endswith('.md'):
                        # Get relative path
                        rel_path = file[len(docs_prefix):].lstrip('/')
                        if rel_path:
                            # Create target directory
                            target_path = self.docs_dir / rel_path
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Extract file
                            with zip_ref.open(file) as source, open(target_path, 'wb') as target:
                                shutil.copyfileobj(source, target)
            else:
                # Extract all markdown files
                for file in zip_ref.namelist():
                    if file.endswith('.md'):
                        # Get target path
                        target_path = self.docs_dir / file
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Extract file
                        with zip_ref.open(file) as source, open(target_path, 'wb') as target:
                            shutil.copyfileobj(source, target)
    
    async def index_docs(self) -> Tuple[int, int]:
        """
        Index documentation files in the database.
        
        Returns:
            Tuple[int, int]: Number of files processed and number indexed
        """
        try:
            if not self.docs_dir.exists():
                logger.error("Docs directory not found at: %s", self.docs_dir)
                return 0, 0
            
            processed = 0
            indexed = 0
            
            # Get all markdown files
            markdown_files = list(self.docs_dir.glob('**/*.md'))
            logger.info("Found %d markdown files to index", len(markdown_files))
            
            async with aiosqlite.connect(self.db_path) as db:
                for filepath in markdown_files:
                    processed += 1
                    
                    try:
                        # Get relative path
                        rel_path = str(filepath.relative_to(self.docs_dir))
                        
                        # Read file content
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Extract title and sections
                        title = extract_title_from_markdown(content, fallback_filename=filepath.stem)
                        h1_content = self._extract_heading_content(content, 1)
                        h2_content = self._extract_heading_content(content, 2)
                        other_headings = self._extract_heading_content(content, 3, 6)
                        bold_content = self._extract_bold_content(content)
                        body_content = self._clean_markdown(content)
                        
                        # Generate URL
                        url = generate_doc_url(rel_path, self.docs_base_url)
                        
                        # Check if file already indexed
                        cursor = await db.execute(
                            "SELECT id, last_updated FROM docs_meta WHERE filepath = ?",
                            (rel_path,)
                        )
                        result = await cursor.fetchone()
                        
                        file_mtime = int(filepath.stat().st_mtime)
                        
                        if result:
                            doc_id, last_updated = result
                            
                            # Update if file changed
                            if last_updated < file_mtime:
                                await db.execute(
                                    """
                                    UPDATE docs_meta 
                                    SET title = ?, url = ?, h1_content = ?, h2_content = ?,
                                        other_headings = ?, bold_content = ?, body_content = ?,
                                        last_updated = ?
                                    WHERE id = ?
                                    """,
                                    (title, url, h1_content, h2_content, other_headings,
                                     bold_content, body_content, file_mtime, doc_id)
                                )
                                indexed += 1
                        else:
                            # Insert new document
                            await db.execute(
                                """
                                INSERT INTO docs_meta 
                                (filepath, title, url, h1_content, h2_content, other_headings,
                                 bold_content, body_content, last_updated)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (rel_path, title, url, h1_content, h2_content, other_headings,
                                 bold_content, body_content, file_mtime)
                            )
                            indexed += 1
                    
                    except Exception as e:
                        logger.error("Error indexing file %s: %s", filepath, e)
                
                await db.commit()
                logger.info("Indexed %d out of %d markdown files", indexed, processed)
                return processed, indexed
        
        except Exception as e:
            logger.error("Error indexing docs: %s", e, exc_info=True)
            return 0, 0
    
    def _extract_heading_content(self, content: str, level: int, max_level: Optional[int] = None) -> str:
        """
        Extract content from headings at specified level.
        
        Args:
            content: Markdown content
            level: Heading level to extract (1-6)
            max_level: Optional maximum level for range extraction
            
        Returns:
            str: Extracted heading content
        """
        try:
            if max_level:
                pattern = '|'.join([f"^{'#' * l}\\s+(.*?)$" for l in range(level, max_level + 1)])
            else:
                pattern = f"^{'#' * level}\\s+(.*?)$"
            
            matches = re.findall(pattern, content, re.MULTILINE)
            
            # FIX: Handle both string and tuple results from re.findall
            if matches and isinstance(matches[0], tuple):
                # If matches contains tuples, extract the first non-empty group from each tuple
                extracted = []
                for match in matches:
                    for group in match:
                        if group:  # Use the first non-empty group
                            extracted.append(group)
                            break
                return ' '.join(extracted)
            else:
                # If matches contains strings, join them directly
                return ' '.join(matches)
        except Exception as e:
            logger.warning(f"Error extracting heading content at level {level}: {e}")
            return ""
    
    def _extract_bold_content(self, content: str) -> str:
        """
        Extract bold content from markdown.
        
        Args:
            content: Markdown content
            
        Returns:
            str: Extracted bold content
        """
        try:
            # Match both **bold** and __bold__ formats
            bold_pattern = r'\*\*(.*?)\*\*|__(.*?)__'
            matches = re.findall(bold_pattern, content)
            
            # Each match is a tuple with two groups
            # FIX: Handle empty groups more safely
            result = []
            for match in matches:
                if isinstance(match, tuple):
                    # Find the first non-empty group
                    for group in match:
                        if group:
                            result.append(group)
                            break
                else:
                    # Direct string match
                    result.append(match)
            
            return ' '.join(result)
        except Exception as e:
            logger.warning(f"Error extracting bold content: {e}")
            return ""
    
    def _clean_markdown(self, content: str) -> str:
        """
        Clean markdown content for indexing.
        
        Args:
            content: Markdown content
            
        Returns:
            str: Cleaned content
        """
        try:
            # Remove code blocks
            content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
            
            # Remove inline code
            content = re.sub(r'`.*?`', '', content)
            
            # Remove links but keep text
            content = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', content)
            
            # Remove images
            content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
            
            # Remove HTML tags
            content = re.sub(r'<.*?>', '', content)
            
            # Remove multiple spaces and newlines
            content = re.sub(r'\s+', ' ', content).strip()
            
            return content
        except Exception as e:
            logger.warning(f"Error cleaning markdown: {e}")
            return content  # Return original content if cleaning fails
    
    async def search_documentation(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search documentation in the database.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of search results
        """
        try:
            if not self.db_path.exists():
                logger.error("Database not found at: %s", self.db_path)
                return []
            
            # Clean up the query
            query = query.strip()
            if not query:
                return []
            
            # Use FTS5 with bm25 ranking
            search_query = ' OR '.join(word for word in query.split())
            
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                cursor = await db.execute(
                    """
                    SELECT
                        filepath, title, url, h1_content, h2_content,
                        snippet(docs_content, 2, '<b>', '</b>', '...', 20) as title_snippet,
                        snippet(docs_content, 3, '<b>', '</b>', '...', 20) as h1_snippet,
                        snippet(docs_content, 4, '<b>', '</b>', '...', 20) as h2_snippet,
                        snippet(docs_content, 7, '<b>', '</b>', '...', 20) as body_snippet,
                        bm25(docs_content) as rank
                    FROM docs_content
                    WHERE docs_content MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (search_query, limit)
                )
                
                rows = await cursor.fetchall()
                
                # Convert rows to dictionaries
                results = []
                for row in rows:
                    results.append({
                        'filepath': row['filepath'],
                        'title': row['title'],
                        'url': row['url'],
                        'h1_content': row['h1_content'],
                        'h2_content': row['h2_content'],
                        'title_snippet': row['title_snippet'],
                        'h1_snippet': row['h1_snippet'],
                        'h2_snippet': row['h2_snippet'],
                        'body_snippet': row['body_snippet'],
                        'rank': row['rank']
                    })
                
                return results
        
        except Exception as e:
            logger.error("Error searching documentation: %s", e, exc_info=True)
            return []
    
    @commands.command(name="docs", aliases=["doc", "search_docs"], help="Search through the documentation. Usage: !docs <query>")
    async def docs_command(self, ctx: Context, *, query: str = None) -> None:
        """
        Search documentation and display results.
        
        Args:
            ctx: Command context
            query: Search query
        """
        if not query:
            await ctx.send("Please provide a search query.\nUsage: `!docs <query>`\nExample: `!docs installation`")
            return
        
        logger.info("Documentation search requested by %s: '%s'", ctx.author, query)
        
        async with ctx.typing():
            # Check if database exists
            if not self.db_path.exists():
                await ctx.send("❌ Documentation database not found. Please wait while I sync documentation (`!syncdocs`).")
                await self.sync_docs()
                if not self.db_path.exists():
                    await ctx.send("❌ Failed to create documentation database. Please contact an administrator.")
                    return
            
            # Search documentation
            results = await self.search_documentation(query)
            
            if not results:
                await ctx.send(f"No documentation found for query: `{query}`.\nTry a different search term or check the documentation at {self.docs_base_url}")
                return
            
            # Create an embed for results
            embed = discord.Embed(
                title=f"Documentation Search Results for '{query}'",
                color=discord.Color.blue(),
                url=f"{self.docs_base_url}"
            )
            
            # Add results to embed
            for i, result in enumerate(results[:5]):  # Limit to 5 results in embed
                title = result['title']
                url = result['url']
                
                # Get best snippet
                snippet = result['body_snippet']
                if result['title_snippet'] and '<b>' in result['title_snippet']:
                    snippet = result['title_snippet']
                elif result['h1_snippet'] and '<b>' in result['h1_snippet']:
                    snippet = result['h1_snippet']
                elif result['h2_snippet'] and '<b>' in result['h2_snippet']:
                    snippet = result['h2_snippet']
                
                # Clean up snippet
                snippet = snippet.replace('<b>', '**').replace('</b>', '**')
                
                # Add field
                embed.add_field(
                    name=f"{i+1}. {title}",
                    value=f"[View Documentation]({url})\n{snippet}",
                    inline=False
                )
            
            # Add footer
            if len(results) > 5:
                embed.set_footer(text=f"Showing 5 of {len(results)} results. View more at {self.docs_base_url}")
            else:
                embed.set_footer(text=f"Found {len(results)} results.")
            
            await ctx.send(embed=embed)
    
    @commands.command(name="syncdocs", help="(Admin Only) Manually sync documentation.")
    @commands.has_permissions(administrator=True)
    async def sync_docs_command(self, ctx: Context) -> None:
        """
        Manually trigger documentation sync.
        
        Args:
            ctx: Command context
        """
        logger.info("Manual documentation sync requested by %s", ctx.author)
        
        message = await ctx.send("⌛ Syncing documentation... This may take a few minutes.")
        
        async with ctx.typing():
            success = await self.sync_docs()
            
            if success:
                await message.edit(content="✅ Documentation sync completed successfully!")
            else:
                await message.edit(content="❌ Documentation sync failed. Check logs for details.")
    
    async def sync_docs(self) -> bool:
        """
        Sync documentation: download, extract, and index.
        
        Returns:
            bool: True if sync successful, False otherwise
        """
        try:
            logger.info("Starting documentation sync")
            
            # Download ZIP
            if not await self.download_docs_zip():
                logger.error("Failed to download documentation ZIP")
                return False
            
            # Extract ZIP
            if not await self.extract_docs_zip():
                logger.error("Failed to extract documentation ZIP")
                return False
            
            # Index docs
            processed, indexed = await self.index_docs()
            
            if processed > 0:
                logger.info("Documentation sync completed: %d files processed, %d indexed", processed, indexed)
                return True
            else:
                logger.error("No documentation files found for indexing")
                return False
        
        except Exception as e:
            logger.error("Error during documentation sync: %s", e, exc_info=True)
            return False


async def setup(bot: commands.Bot) -> None:
    """
    Load the DocumentationCog into the bot.
    
    Args:
        bot: The bot instance
    """
    try:
        # Check required libraries are available
        import frontmatter
        import aiosqlite
        import aiohttp
        
        # Create and add the cog
        await bot.add_cog(DocumentationCog(bot))
        logger.info("DocumentationCog loaded successfully")
    except ImportError as e:
        logger.critical("Missing required library for DocumentationCog: %s. Cog will not load.", e)
        raise commands.ExtensionFailed("DocumentationCog", f"Missing dependency: {e}")
    except Exception as e:
        logger.critical("Failed to load DocumentationCog: %s", e, exc_info=True)
        raise commands.ExtensionFailed("DocumentationCog", f"Initialization error: {e}")