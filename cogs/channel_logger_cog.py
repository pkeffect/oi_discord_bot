# ./cogs/channel_logger_cog.py

import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
import logging
import json
import os
import datetime
import asyncio
import aiohttp # Needed for downloading
import re # For sanitizing filenames and finding URLs
from urllib.parse import urlparse
import mimetypes # To guess extension from content-type
from collections import defaultdict

# --- Cog Specific Logger ---
logger = logging.getLogger(__name__) # Logger name: 'cogs.channel_logger_cog'

# --- Constants ---
CONFIG_FILE = "channel_logger_config.json"
DEFAULT_LOG_DIR = "./data/channel_logs"
DEFAULT_MEDIA_DIR = os.path.join(DEFAULT_LOG_DIR, "media") # Default media location
FILE_WRITE_LOCKS = defaultdict(asyncio.Lock)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024 # 1MB chunks for downloading
# Regex to find potential URLs in message content
URL_REGEX = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')

# --- Helper for Sanitizing Filenames ---
def sanitize_filename(filename):
    """Removes or replaces characters invalid in filenames."""
    if not filename: return "downloaded_file"
    # Remove characters illegal in most filesystems
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # Optionally, replace multiple underscores/spaces with single ones
    sanitized = re.sub(r'_+', '_', sanitized).strip()
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Avoid names starting/ending with dots or underscores (can cause issues)
    sanitized = sanitized.strip('._')
    # Limit length if necessary (e.g., 200 chars) - adjust as needed
    max_len = 200
    if len(sanitized) > max_len:
        name, ext = os.path.splitext(sanitized)
        limit = max_len - len(ext) - 1 # Calculate limit for name part
        if limit < 1: limit = 1 # Ensure at least one character for the name
        sanitized = name[:limit] + "_" + ext # Truncate name part
    return sanitized if sanitized else "downloaded_file" # Fallback name


class ChannelLoggerCog(commands.Cog, name="ChannelLogger"):
    """Logs messages and optionally downloads media from specified channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_directory = DEFAULT_LOG_DIR
        self.log_format = "{timestamp} [{author_name} ({author_id})] {message_content}{attachments_info}"
        self.download_media = False
        self.media_directory = DEFAULT_MEDIA_DIR
        self.server_channel_map = {}
        self.is_ready = False
        self._session: aiohttp.ClientSession | None = None

        self.load_config()
        self.ensure_log_dir()
        if self.download_media:
            self.ensure_media_dir()

        self.bot.loop.create_task(self.initialize_session())

        self.is_ready = True
        logger.info("ChannelLoggerCog initialized.")

    async def initialize_session(self):
        """Creates the aiohttp session."""
        # Consider adding connector limits if downloading heavily
        # connector = aiohttp.TCPConnector(limit=20) # Example limit
        self._session = aiohttp.ClientSession() #connector=connector)
        logger.info("aiohttp session for media downloads initialized.")

    async def cog_unload(self):
        """Clean up the session when the cog is unloaded."""
        if self._session:
            await self._session.close()
            logger.info("aiohttp session closed.")

    # --- Configuration Handling ---
    # (load_config, ensure_log_dir, ensure_media_dir remain largely the same as previous version)
    # --- Make sure load_config sets self.download_media and self.media_directory ---
    def load_config(self):
        """Loads configuration from the JSON file."""
        logger.info(f"Attempting to load configuration from {CONFIG_FILE}...")
        try:
            if not os.path.exists(CONFIG_FILE):
                logger.error(f"Configuration file {CONFIG_FILE} not found! Logging and media download disabled.")
                self.server_channel_map = {}
                self.download_media = False
                return

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            self.log_directory = config_data.get("log_directory", DEFAULT_LOG_DIR)
            self.log_format = config_data.get("log_format", self.log_format)
            self.download_media = config_data.get("download_media", False)
            self.media_directory = config_data.get("media_directory", os.path.join(self.log_directory, "media")) # Default relative to log dir


            # Convert keys (server IDs) to ints and values (channel IDs) to ints
            raw_server_map = config_data.get("servers", {})
            self.server_channel_map = {}
            for server_id_str, channel_list_str in raw_server_map.items():
                try:
                    server_id = int(server_id_str)
                    if isinstance(channel_list_str, list):
                         valid_channels = []
                         for chan_id_str in channel_list_str:
                              try: valid_channels.append(int(chan_id_str))
                              except (ValueError, TypeError): logger.warning(f"Invalid channel ID '{chan_id_str}' for server {server_id}. Skipping.")
                         if valid_channels: self.server_channel_map[server_id] = valid_channels
                         else: logger.warning(f"Server ID {server_id} has no valid channel IDs listed. Skipping server.")
                except (ValueError, TypeError):
                    logger.warning(f"Invalid server ID '{server_id_str}' in config. Skipping.")

            if not self.server_channel_map:
                logger.warning("No valid server/channel configurations loaded. Logging is effectively disabled.")
            else:
                logger.info(f"Configuration loaded. Monitoring {len(self.server_channel_map)} servers.")
                logger.debug(f"Loaded channel map: {self.server_channel_map}")
                logger.info(f"Media downloading: {'Enabled' if self.download_media else 'Disabled'}")
                if self.download_media:
                     logger.info(f"Media directory: {self.media_directory}")


        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {CONFIG_FILE}: {e}. Logging disabled.")
            self.server_channel_map = {}
            self.download_media = False
        except Exception as e:
            logger.exception(f"An unexpected error occurred loading config: {e}. Logging disabled.")
            self.server_channel_map = {}
            self.download_media = False

    def ensure_log_dir(self):
        """Creates the log directory if it doesn't exist."""
        try:
            os.makedirs(self.log_directory, exist_ok=True)
            logger.info(f"Ensured log directory exists: {self.log_directory}")
        except OSError as e:
            logger.error(f"Failed to create log directory {self.log_directory}: {e}. Logging may fail.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred ensuring log directory: {e}")

    def ensure_media_dir(self):
        """Creates the base media directory if it doesn't exist."""
        if not self.media_directory:
             logger.error("Media directory path is not set. Cannot ensure directory.")
             return
        try:
            os.makedirs(self.media_directory, exist_ok=True)
            logger.info(f"Ensured base media directory exists: {self.media_directory}")
        except OSError as e:
            logger.error(f"Failed to create media directory {self.media_directory}: {e}. Media downloading may fail.")
        except Exception as e:
            logger.exception(f"An unexpected error occurred ensuring media directory: {e}")

    # --- Logging Logic ---
    # (_write_to_log and log_message remain the same as previous version)
    async def _write_to_log(self, file_path: str, log_entry: str):
        """Appends a log entry to the specified file, handling locking and errors."""
        async with FILE_WRITE_LOCKS[file_path]:
            try:
                # Ensure the specific log file's directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(log_entry + '\n')
            except IOError as e:
                logger.error(f"IOError writing to log file {file_path}: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error writing to log file {file_path}: {e}")


    async def log_message(self, message: discord.Message):
        """Formats and logs a single message."""
        if not message.guild: return

        guild_id = message.guild.id
        channel_id = message.channel.id
        log_file_path = os.path.join(self.log_directory, f"{guild_id}-{channel_id}.log")

        timestamp = message.created_at.replace(tzinfo=datetime.timezone.utc).isoformat()
        author_name = f"{message.author.name}#{message.author.discriminator}"
        author_id = message.author.id
        message_content = message.content

        attachments_info = ""
        if message.attachments:
            # Store relative path in log if downloaded? Maybe too complex. Stick to filename.
            attach_list = [f"[Attachment: {att.filename} ({att.size // 1024} KB)]" for att in message.attachments]
            attachments_info = " " + " ".join(attach_list)

        try:
             log_entry = self.log_format.format(
                 timestamp=timestamp,
                 author_name=author_name,
                 author_id=author_id,
                 message_content=message_content,
                 attachments_info=attachments_info
            )
        except KeyError as e:
             logger.warning(f"Invalid placeholder {e} in log_format string. Using default format for message {message.id}.")
             log_entry = f"{timestamp} [{author_name} ({author_id})] {message_content}{attachments_info}"

        asyncio.create_task(self._write_to_log(log_file_path, log_entry))


    # --- Media Downloading Logic ---

    def _get_dated_media_path(self, message_timestamp: datetime.datetime) -> str:
        """Returns the absolute path to the media subdirectory for a given date."""
        date_str = message_timestamp.strftime('%Y-%m-%d')
        return os.path.join(self.media_directory, date_str)

    def _determine_file_extension(self, content_type: str | None, url: str) -> str:
        """Determines file extension from content-type or URL, similar to provided example."""
        if not content_type: content_type = ""
        content_type = content_type.split(';')[0].strip().lower() # Get primary type

        logger.debug(f"Determining extension for content-type='{content_type}', url='{url}'")

        # Prioritize content-type using mimetypes module
        ext = mimetypes.guess_extension(content_type, strict=False)
        if ext:
            logger.debug(f"Guessed extension '{ext}' from content-type '{content_type}'")
            # Common fixes for mimetypes results
            if ext == '.jpe': ext = '.jpg'
            return ext

        # Fallback: Check URL path extension
        parsed_url = urlparse(url)
        path_ext = os.path.splitext(parsed_url.path)[1].lower()
        if path_ext and len(path_ext) > 1: # Ensure it's not just "."
            logger.debug(f"Using extension '{path_ext}' from URL path")
            return path_ext

        # Fallback: Check common media types in URL itself (less reliable)
        url_lower = url.lower()
        for common_ext in ['.gif', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.mov', '.mp3', '.wav', '.ogg']:
            if common_ext in url_lower:
                 logger.debug(f"Using extension '{common_ext}' found in URL string")
                 return common_ext

        logger.warning(f"Could not determine specific extension for {url} (Content-Type: {content_type}). Using '.bin'")
        return '.bin' # Default fallback


    async def _download_media(self, url: str, target_filepath_base: str):
        """
        Downloads media, determines correct extension, ensures unique filename, and saves.
        target_filepath_base should be the path *without* an extension determined yet.
        e.g., /path/to/media/YYYY-MM-DD/messageID_sanitizedOriginalName
        """
        if not self._session:
            logger.error("aiohttp session not ready, cannot download.")
            return

        final_filepath = None # Track the actual path saved
        try:
            logger.info(f"Attempting to download: {url}")
            async with self._session.get(url) as response:
                response.raise_for_status() # Error for bad status codes

                content_type = response.headers.get('Content-Type')
                logger.debug(f"Download response Content-Type: {content_type}")

                # Determine final extension *after* getting headers
                extension = self._determine_file_extension(content_type, url)
                final_filepath = target_filepath_base + extension

                # --- Check if file already exists (using final path with extension) ---
                if os.path.exists(final_filepath):
                    logger.info(f"Media file already exists, skipping download: {os.path.basename(final_filepath)}")
                    return

                # Ensure the specific daily directory exists right before writing
                target_dir = os.path.dirname(final_filepath)
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except OSError as e:
                     logger.error(f"OSError creating directory {target_dir}: {e}. Skipping download.")
                     return # Cannot save if dir creation fails

                logger.info(f"Downloading to: {final_filepath}")
                # Save using streaming
                async with FILE_WRITE_LOCKS[final_filepath]: # Lock based on the final file path
                    with open(final_filepath, 'wb') as f:
                        while True:
                            chunk = await response.content.read(DOWNLOAD_CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                logger.info(f"Successfully downloaded: {os.path.basename(final_filepath)}")

        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error downloading {url}: Status {e.status}, Message: {e.message}")
        except aiohttp.ClientError as e:
            logger.error(f"Client error downloading {url}: {e}")
        except asyncio.TimeoutError:
             logger.error(f"Timeout error downloading {url}")
        except IOError as e:
            logger.error(f"IOError saving downloaded file to {final_filepath or target_filepath_base}: {e}")
        except Exception as e:
            # Clean up partially downloaded file if error occurred during write
            if final_filepath and os.path.exists(final_filepath):
                 try: os.remove(final_filepath)
                 except Exception as rm_err: logger.error(f"Failed to remove partial download {final_filepath}: {rm_err}")
            logger.exception(f"Unexpected error downloading {url}: {e}")


    async def _extract_tenor_gif_url(self, tenor_page_url: str) -> str | None:
        """Async version to extract direct media URL from Tenor page."""
        if not self._session: return None
        logger.info(f"Attempting to extract media from Tenor URL: {tenor_page_url}")
        try:
            async with self._session.get(tenor_page_url) as response:
                response.raise_for_status()
                html_content = await response.text()

                # Try various regex patterns (similar to your sync example)
                # Prioritize MP4/WebM as they are often higher quality than GIF
                patterns = [
                    r'<meta property="og:video" content="([^"]+\.(?:mp4|webm))"', # og:video (MP4/WebM)
                    r'"contentUrl":\s*"(https://media\.tenor\.com/[^"]+\.(?:mp4|webm))"', # JSON-LD (MP4/WebM)
                    r'(https://media\.tenor\.com/[^"\']+\.(?:mp4|webm))', # Direct media search (MP4/WebM)
                    r'<meta property="og:image" content="([^"]+\.gif)"', # og:image (GIF only)
                    r'"contentUrl":\s*"(https://media\.tenor\.com/[^"]+\.gif)"', # JSON-LD (GIF only)
                    r'(https://media\.tenor\.com/[^"\']+\.gif)', # Direct GIF search
                ]

                for pattern in patterns:
                    match = re.search(pattern, html_content)
                    if match:
                        media_url = match.group(1)
                        logger.info(f"Found Tenor media URL using pattern '{pattern[:20]}...': {media_url}")
                        return media_url

                logger.warning(f"No direct media URL found in Tenor page: {tenor_page_url}")
                return None

        except Exception as e:
            logger.error(f"Error extracting Tenor URL for {tenor_page_url}: {e}")
            return None


    async def schedule_media_download(self, url: str, message: discord.Message, base_filename: str | None = None):
        """Schedules a download if media downloading is enabled and file doesn't exist."""
        if not self.download_media or not self.media_directory:
            return

        try:
            # Determine filename base if not provided (e.g., for content URLs)
            if not base_filename:
                parsed_url = urlparse(url)
                path_filename = os.path.basename(parsed_url.path)
                if path_filename and path_filename != '/' and '.' in path_filename: # Basic check for filename in path
                    base_filename = path_filename
                else: # Generate a name if URL doesn't give one
                     base_filename = f"content_url_{message.id}" # Needs extension later
                logger.debug(f"Generated base filename for content URL: {base_filename}")


            # Get dated path and sanitize the base filename part (without extension)
            target_dir = self._get_dated_media_path(message.created_at)
            name_part, _ = os.path.splitext(base_filename) # Separate potential original ext
            sanitized_name = sanitize_filename(name_part)

            # Construct target path *base* (without final extension yet)
            # Extension will be determined during download from Content-Type
            target_filepath_base = os.path.join(target_dir, f"{message.id}_{sanitized_name}")

            # --- Existence Check ---
            # Since we don't know the *exact* extension yet, we check if *any* file
            # with this base name exists. This is a simplification. A more complex
            # check could list the directory and match messageID_sanitizedName.*
            # For now, we'll let the download function handle the final check after extension is known.
            # if os.path.exists(target_filepath_base + ".*"): # This glob doesn't work directly
            #    logger.info(f"Potential media file already exists for base {target_filepath_base}, download will perform final check.")
            #    pass # Let download handle final check

            # Schedule the actual download task
            logger.debug(f"Scheduling download for URL: {url}, Base Path: {target_filepath_base}")
            asyncio.create_task(self._download_media(url, target_filepath_base))

        except Exception as e:
            logger.exception(f"Error scheduling download for URL {url} from message {message.id}: {e}")


    # --- Event Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for messages, logs them, and optionally downloads media."""
        if not self.is_ready: return
        if message.author.bot: return
        if not message.guild: return

        guild_id = message.guild.id
        channel_id = message.channel.id

        if guild_id in self.server_channel_map and channel_id in self.server_channel_map[guild_id]:
            logger.debug(f"Processing message {message.id} from {guild_id}-{channel_id}")

            # Log the message text
            await self.log_message(message)

            # --- Media Handling ---
            if self.download_media:
                # 1. Process Attachments
                if message.attachments:
                    logger.debug(f"Found {len(message.attachments)} attachments for message {message.id}.")
                    for attachment in message.attachments:
                        await self.schedule_media_download(attachment.url, message, base_filename=attachment.filename)

                # 2. Process Links in Content (e.g., Tenor, direct image/video links)
                processed_urls = set(att.url for att in message.attachments) # Avoid re-downloading attachment URLs if also in content
                try:
                    # Find all potential URLs in the message content
                    found_urls = URL_REGEX.findall(message.content)
                    if found_urls:
                        logger.debug(f"Found {len(found_urls)} potential URLs in message {message.id} content.")
                        for url in found_urls:
                            if url in processed_urls: continue # Skip if already processed as attachment

                            logger.debug(f"Checking content URL: {url}")
                            # Simple check for common image/video extensions or known domains
                            is_media_link = any(ext in url.lower() for ext in ['.gif', '.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.mov'])
                            is_tenor_link = 'tenor.com/view/' in url

                            if is_media_link:
                                await self.schedule_media_download(url, message)
                                processed_urls.add(url)
                            elif is_tenor_link:
                                direct_media_url = await self._extract_tenor_gif_url(url)
                                if direct_media_url:
                                    await self.schedule_media_download(direct_media_url, message, base_filename=f"tenor_{message.id}") # Provide base name
                                    processed_urls.add(url) # Mark original tenor link as processed
                                    processed_urls.add(direct_media_url) # Mark direct link as processed
                except Exception as e:
                    logger.error(f"Error processing content URLs for message {message.id}: {e}")


    # --- Admin Commands ---
    # (reload_logger_config and logger_status remain the same as previous version)
    @commands.command(name="reload_logger_config", help="(Admin Only) Reload channel logger configuration.")
    @commands.has_permissions(administrator=True)
    async def reload_logger_config(self, ctx: Context):
        """Reloads the configuration from channel_logger_config.json."""
        logger.info(f"Reload requested by {ctx.author} (ID: {ctx.author.id})")
        self.is_ready = False
        self.load_config()
        self.ensure_log_dir()
        if self.download_media: # Only ensure media dir if enabled after reload
            self.ensure_media_dir()
        # Re-initialize session if needed (though usually not necessary unless config changes dramatically)
        # if self._session and self._session.closed:
        #     self.bot.loop.create_task(self.initialize_session())
        self.is_ready = True
        await ctx.send("✅ Channel logger configuration reloaded.")

    @commands.command(name="logger_status", help="Show which channels are being logged.")
    @commands.has_permissions(manage_messages=True) # Allow mods to check status
    async def logger_status(self, ctx: Context):
        """Displays the currently monitored servers and channels."""
        if not self.server_channel_map:
             await ctx.send("Channel logging is currently disabled or no channels are configured.")
             return

        embed = discord.Embed(title="Channel Logger Status", color=discord.Color.blue())
        embed.add_field(name="Text Log Directory", value=f"`{self.log_directory}`", inline=False)
        media_status = f"{'Enabled' if self.download_media else 'Disabled'}"
        if self.download_media:
             media_status += f" (Saving to `{self.media_directory}`)"
        embed.add_field(name="Media Downloading", value=media_status, inline=False)


        status_text = ""
        monitored_servers = 0
        monitored_channels = 0

        guilds_processed = set() # To avoid duplicate server names if multiple channels in one server
        for guild_id, channel_ids in self.server_channel_map.items():
             guild = self.bot.get_guild(guild_id)
             guild_name = guild.name if guild else f"Unknown Server ({guild_id})"
             if guild_id not in guilds_processed:
                  status_text += f"\n**{guild_name}** (ID: {guild_id}):\n"
                  guilds_processed.add(guild_id)
                  monitored_servers += 1

             channel_names = []
             for chan_id in channel_ids:
                  channel = self.bot.get_channel(chan_id) # Works for text/voice/forum etc.
                  channel_names.append(f"`#{channel.name if channel else f'Unknown Channel ({chan_id})'}`")
                  monitored_channels +=1
             status_text += "  Logging Channels: " + ", ".join(channel_names) + "\n"

        # Handle potential overflow in embed field
        field_name = f"Monitored Servers ({monitored_servers}) / Channels ({monitored_channels})"
        if len(status_text) > 1024:
             status_text = status_text[:1020] + "\n..."
        if not status_text: # If map exists but somehow no text generated
             status_text = "No channels seem to be configured correctly."

        embed.add_field(name=field_name, value=status_text, inline=False)
        await ctx.send(embed=embed)

    # --- Error Handling ---
    # (on_command_error remains the same)
    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError):
        """Handles errors specific to commands within this Cog."""
        if ctx.cog is not self or not ctx.command: return

        log_prefix = f"Cog '{self.qualified_name}' - Command '{ctx.command.qualified_name}':"

        if isinstance(error, commands.MissingPermissions):
            logger.warning(f"{log_prefix} User {ctx.author} (ID: {ctx.author.id}) missing permissions: {error.missing_permissions}")
            await ctx.send("❌ You do not have the necessary permissions to use this command.", delete_after=10)
        elif isinstance(error, commands.CommandInvokeError):
             original = error.original
             logger.error(f"{log_prefix} Error during invocation: {original.__class__.__name__}: {original}", exc_info=True)
             await ctx.send(f"An unexpected error occurred: `{original.__class__.__name__}`.")
        else:
            logger.error(f"{log_prefix} Unexpected error: {error}", exc_info=True)


# --- Setup Function ---
async def setup(bot: commands.Bot):
    """Loads the ChannelLoggerCog."""
    # Ensure necessary libraries are available
    try:
         import aiohttp
         import re
         import mimetypes
    except ImportError as e:
         logger.error(f"Missing required library for ChannelLoggerCog: {e}. Cog may not function correctly.")
         # Optionally prevent loading if dependencies are missing
         # raise commands.ExtensionFailed("ChannelLoggerCog", e) from e

    await bot.add_cog(ChannelLoggerCog(bot))
    logger.info("ChannelLogger Cog loaded successfully.")