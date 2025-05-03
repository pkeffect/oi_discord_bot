# ./utils.py

import logging
import time
import discord
import os  # Added missing import for os module used in sanitize_filename
from discord.ext import commands
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar, Awaitable
import functools
import asyncio
import re

logger = logging.getLogger(__name__)

# Type definitions for better hints
T = TypeVar('T')
CommandDecorator = Callable[[T], T]

def standardize_command_error(cog_name: str) -> CommandDecorator:
    """
    Decorator factory to standardize command error handling across cogs.
    
    Args:
        cog_name: The name of the cog for logging
        
    Returns:
        A decorator function for command error handlers
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, ctx: commands.Context, error: commands.CommandError):
            log_prefix = f"Cog '{cog_name}' - Command '{ctx.command.qualified_name if ctx.command else 'Unknown'}':"
            
            # First, let the original handler have a chance to handle specific cases
            handled = await func(self, ctx, error)
            
            # If the original handler indicated it handled the error, we're done
            if handled:
                return True
                
            # Otherwise apply standard handling
            if isinstance(error, commands.MissingRequiredArgument):
                logger.info(f"{log_prefix} Missing argument: {error.param.name}")
                await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `{ctx.prefix}help {ctx.command.qualified_name}` for usage.")
                return True
            elif isinstance(error, commands.BadArgument):
                logger.warning(f"{log_prefix} Bad argument: {error}")
                await ctx.send(f"❌ Invalid argument: {error}")
                return True
            elif isinstance(error, commands.MissingPermissions):
                logger.warning(f"{log_prefix} User {ctx.author} (ID: {ctx.author.id}) missing permissions: {error.missing_permissions}")
                await ctx.send("❌ You do not have the necessary permissions to use this command.", delete_after=10)
                return True
            elif isinstance(error, commands.CommandInvokeError):
                original = error.original
                logger.error(f"{log_prefix} Error during invocation: {original.__class__.__name__}: {original}", exc_info=True)
                await ctx.send(f"An unexpected error occurred while running the command: `{original.__class__.__name__}`. Please check the bot logs.")
                return True
            else:
                # Log other errors but don't handle them here
                logger.error(f"{log_prefix} Unhandled error: {error.__class__.__name__}: {error}", exc_info=True)
                return False
                
        return wrapper
    return decorator


class RateLimiter:
    """
    Common rate limiter implementation for all cogs.
    Tracks calls by user and enforces limits.
    """
    
    def __init__(self, max_calls: int, period: int, name: str = "default"):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum calls allowed in the period
            period: Time period in seconds
            name: Name identifier for this rate limiter instance
        """
        self.max_calls = max_calls
        self.period = period
        self.name = name
        self.calls: Dict[str, List[float]] = {}
        logger.info(f"Initialized RateLimiter '{name}': {max_calls} calls per {period} seconds")
    
    def is_rate_limited(self, user_id: str) -> bool:
        """
        Check if a user is currently rate limited.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            bool: True if user is rate limited, False otherwise
        """
        current_time = time.time()
        user_calls = self.calls.get(user_id, [])
        
        # Clear outdated calls
        user_calls = [t for t in user_calls if current_time - t < self.period]
        self.calls[user_id] = user_calls
        
        # Check if user exceeds the limit
        return len(user_calls) >= self.max_calls
    
    def add_call(self, user_id: str) -> None:
        """
        Register a call for the user.
        
        Args:
            user_id: The user ID to add a call for
        """
        if user_id not in self.calls:
            self.calls[user_id] = []
            
        self.calls[user_id].append(time.time())
        logger.debug(f"RateLimiter '{self.name}': Added call for user {user_id}, now at {len(self.calls[user_id])}/{self.max_calls}")
    
    def time_remaining(self, user_id: str) -> int:
        """
        Get seconds until the user can make another call.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            int: Seconds until rate limit expires, or 0 if not limited
        """
        if not self.is_rate_limited(user_id):
            return 0
            
        current_time = time.time()
        oldest_call = min(self.calls[user_id])
        return max(1, int(self.period - (current_time - oldest_call)))
    
    def reset_user(self, user_id: str) -> None:
        """
        Reset the rate limit for a specific user.
        
        Args:
            user_id: The user ID to reset
        """
        if user_id in self.calls:
            del self.calls[user_id]
            logger.debug(f"RateLimiter '{self.name}': Reset rate limit for user {user_id}")


def sanitize_filename(filename: str) -> str:
    """
    Removes or replaces characters invalid in filenames.
    Standardized version for use across all cogs.
    
    Args:
        filename: Original filename to sanitize
        
    Returns:
        str: Sanitized filename
    """
    if not filename: 
        return "downloaded_file"
    # Remove characters illegal in most filesystems
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # Replace multiple underscores/spaces with single ones
    sanitized = re.sub(r'_+', '_', sanitized).strip()
    sanitized = re.sub(r'\s+', '_', sanitized)
    # Avoid names starting/ending with dots or underscores
    sanitized = sanitized.strip('._')
    # Limit length if necessary
    max_len = 200
    if len(sanitized) > max_len:
        name, ext = os.path.splitext(sanitized)
        limit = max_len - len(ext) - 1  # Calculate limit for name part
        if limit < 1: 
            limit = 1  # Ensure at least one character for the name
        sanitized = name[:limit] + "_" + ext  # Truncate name part
    return sanitized if sanitized else "downloaded_file"  # Fallback name


async def send_long_message(ctx: commands.Context, content: str, max_length: int = 1900, split_char: str = "\n") -> List[discord.Message]:
    """
    Utility to send a long message split into chunks.
    
    Args:
        ctx: Command context
        content: Long message content to send
        max_length: Maximum length of each chunk
        split_char: Character to split on (to avoid breaking words/lines)
        
    Returns:
        List of sent messages
    """
    if len(content) <= max_length:
        return [await ctx.send(content)]
        
    messages = []
    current_chunk = ""
    
    # Split the content
    parts = content.split(split_char)
    
    for part in parts:
        part_with_split = part + split_char  # Add back the split character
        
        # If adding this part would make the chunk too long, send current chunk and start a new one
        if len(current_chunk) + len(part_with_split) > max_length:
            if current_chunk:  # Only send if we have content
                try:
                    messages.append(await ctx.send(current_chunk))
                except discord.HTTPException as e:
                    logger.error(f"Error sending message chunk: {e}")
                current_chunk = part_with_split
            else:
                # If a single part is too long, we need to force-split it
                if len(part_with_split) > max_length:
                    for i in range(0, len(part_with_split), max_length):
                        sub_part = part_with_split[i:i+max_length]
                        try:
                            messages.append(await ctx.send(sub_part))
                        except discord.HTTPException as e:
                            logger.error(f"Error sending message sub-chunk: {e}")
                else:
                    current_chunk = part_with_split
        else:
            current_chunk += part_with_split
    
    # Send any remaining content
    if current_chunk:
        try:
            messages.append(await ctx.send(current_chunk))
        except discord.HTTPException as e:
            logger.error(f"Error sending final message chunk: {e}")
            
    return messages