# ./cogs/openwebui_cog.py

import discord
from discord.ext import commands
from discord.ext.commands import Context
import logging
import aiohttp
import json
import asyncio
import socket
import os
import time
import re
import base64
from urllib.parse import urljoin, urlparse
from collections import defaultdict
from typing import Dict, List, Optional, Union, Tuple, Any, DefaultDict

# Set up logger for this cog
logger = logging.getLogger(__name__)

# Constants
API_TIMEOUT_SECONDS = 180  # 3 minutes for potentially long LLM responses
MAX_RESPONSE_LENGTH = 1950  # Discord message limit is 2000, leave a buffer
CONNECTION_TIMEOUT = 15  # Seconds to wait for initial connection & simple requests
DIAGNOSTIC_TIMEOUT = 10  # Shorter timeout for diagnostic checks
SECRET_MASK_PATTERN = r"eyJ|sk-|pk-|xf-|fk-|ak-|mk-|lk-"  # Common API key prefixes

class SecurityUtils:
    """
    Utility class for security-related functions.
    Handles sensitive data masking and validation.
    """
    
    @staticmethod
    def mask_sensitive_value(value: str) -> str:
        """
        Returns a securely masked version of a sensitive value.
        
        Args:
            value: The sensitive value to mask
            
        Returns:
            str: A masked representation of the value
        """
        if not value:
            return "<empty>"
        
        # Check if it's potentially a JWT or API key with common patterns
        if re.search(SECRET_MASK_PATTERN, value):
            # Show minimal parts for keys that match known patterns
            if len(value) <= 8:
                return "***" 
            else:
                # Show only first 3 and last 3 characters
                return f"{value[:3]}...{value[-3:]}"
        else:
            # For other strings, show more context but still mask
            if len(value) <= 6:
                return "***" 
            elif len(value) <= 12:
                return f"{value[:2]}...{value[-2:]}"
            else:
                return f"{value[:3]}...{value[-3:]}"
        
    @staticmethod
    def is_valid_jwt_format(token: str) -> bool:
        """
        Performs basic validation of JWT token format (without verifying signature).
        
        Args:
            token: The JWT token to validate
            
        Returns:
            bool: True if token has valid JWT format, False otherwise
        """
        if not token:
            return False
            
        # JWT format: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return False
            
        # Check if all parts look like base64url encoded strings
        try:
            for part in parts[:2]:  # Only check header and payload
                # Add padding if needed
                padding = '=' * (4 - len(part) % 4) if len(part) % 4 != 0 else ''
                # Replace URL-safe chars and add padding
                part = part.replace('-', '+').replace('_', '/') + padding
                # Try to decode
                base64.b64decode(part)
            return True
        except Exception:
            return False
    
    @staticmethod
    def sanitize_url_for_logging(url: str) -> str:
        """
        Sanitizes URLs that might contain tokens or keys in the query string.
        
        Args:
            url: The URL to sanitize
            
        Returns:
            str: Sanitized URL with potential credentials masked
        """
        if not url:
            return "<empty_url>"
            
        try:
            parsed = urlparse(url)
            # Check for credentials in netloc (user:pass@hostname)
            if '@' in parsed.netloc:
                # Mask username/password in URL
                userpass, host = parsed.netloc.split('@', 1)
                parsed = parsed._replace(netloc=f"***@{host}")
                
            # Check and mask tokens in query parameters
            if parsed.query:
                query_parts = parsed.query.split('&')
                sanitized_parts = []
                
                for part in query_parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        # Check if parameter might be sensitive
                        if any(s in key.lower() for s in ['key', 'token', 'secret', 'password', 'auth']):
                            if value:
                                sanitized_parts.append(f"{key}=***")
                            else:
                                sanitized_parts.append(part)
                        else:
                            sanitized_parts.append(part)
                    else:
                        sanitized_parts.append(part)
                
                # Rebuild the URL with sanitized query
                parsed = parsed._replace(query='&'.join(sanitized_parts))
                
            return parsed.geturl()
        except Exception:
            # If parsing fails, just return a generic masked URL
            return re.sub(r'(https?://[^/?#]+)(.*)', r'\1/***', url)


class RateLimiter:
    """
    Rate limiter for API calls to prevent abuse.
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
        self.calls: DefaultDict[str, List[float]] = defaultdict(list)
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
        # Clear outdated calls
        self.calls[user_id] = [t for t in self.calls[user_id] 
                              if current_time - t < self.period]
        
        # Check if user exceeds the limit
        return len(self.calls[user_id]) >= self.max_calls
    
    def add_call(self, user_id: str) -> None:
        """
        Register a call for the user.
        
        Args:
            user_id: The user ID to add a call for
        """
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
        return max(1, int(self.period - (current_time - oldest_call)) + 1)  # +1 for safety
    
    def reset_user(self, user_id: str) -> None:
        """
        Reset the rate limit for a specific user.
        
        Args:
            user_id: The user ID to reset
        """
        if user_id in self.calls:
            del self.calls[user_id]
            logger.debug(f"RateLimiter '{self.name}': Reset rate limit for user {user_id}")


class RegenerateView(discord.ui.View):
    """
    Discord UI View for regenerating LLM responses.
    Provides a button to regenerate the response with the same prompt.
    """
    
    def __init__(self, cog: 'OpenWebUICog', prompt: str, model: str, original_ctx: Context):
        """
        Initialize the regenerate view.
        
        Args:
            cog: The OpenWebUICog instance
            prompt: The prompt to regenerate a response for
            model: The model to use
            original_ctx: The original command context
        """
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.prompt = prompt
        self.model = model
        self.original_ctx = original_ctx
        
    @discord.ui.button(label="Regenerate Response", style=discord.ButtonStyle.primary)
    async def regenerate_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Handle regenerate button click.
        
        Args:
            interaction: The button interaction
            button: The button that was clicked
        """
        await interaction.response.defer(thinking=True)
        # Call the LLM again with the same prompt
        result = await self.cog.try_all_chat_endpoints(self.prompt, self.model)
        
        if result.get("success"):
            content = result.get("content", "")
            # Create a new regenerate view for the new response
            new_view = RegenerateView(self.cog, self.prompt, self.model, self.original_ctx)
            
            if len(content) <= MAX_RESPONSE_LENGTH:
                await interaction.followup.send(content, view=new_view)
            else:
                # Truncate and indicate it was truncated
                truncated_content = content[:MAX_RESPONSE_LENGTH] + "\n\n*[Response truncated due to Discord length limit]*"
                await interaction.followup.send(truncated_content, view=new_view)
        else:
            # Format error message
            error_embed = self.cog.create_error_embed(
                result.get('error', 'Unknown Error'),
                f"Failed to regenerate response using model {self.model}",
                result.get('details', 'No details available.')
            )
            await interaction.followup.send(embed=error_embed)


class ModelSelectView(discord.ui.View):
    """
    Discord UI View for selecting different LLM models.
    Provides a dropdown to select a model for the same prompt.
    """
    
    def __init__(self, cog: 'OpenWebUICog', prompt: str, original_ctx: Context, available_models: List[str]):
        """
        Initialize the model select view.
        
        Args:
            cog: The OpenWebUICog instance
            prompt: The prompt to use
            original_ctx: The original command context
            available_models: List of available model names
        """
        super().__init__(timeout=180)
        self.cog = cog
        self.prompt = prompt
        self.original_ctx = original_ctx
        
        # Create model select options
        options = [discord.SelectOption(label="Default", description="Use default model")]
        
        # Add available models (limit to 25 due to Discord constraints)
        for model in available_models[:24]:  # 25 total including Default
            if len(model) > 25:  # Discord option label length limit
                label = model[:22] + "..."
                description = f"Model: {model}"[:100]  # Limit description length
            else:
                label = model
                description = None
                
            options.append(discord.SelectOption(label=label, value=model, description=description))
        
        # Add the select menu to the view
        self.add_item(ModelSelector(options, self.cog, self.prompt))


class ModelSelector(discord.ui.Select):
    """
    Discord UI Select for choosing a model.
    Handles model selection and response generation.
    """
    
    def __init__(self, options: List[discord.SelectOption], cog: 'OpenWebUICog', prompt: str):
        """
        Initialize the model selector.
        
        Args:
            options: List of model options
            cog: The OpenWebUICog instance
            prompt: The prompt to use
        """
        super().__init__(
            placeholder="Select a model",
            min_values=1,
            max_values=1,
            options=options
        )
        self.cog = cog
        self.prompt = prompt
    
    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Handle model selection.
        
        Args:
            interaction: The selection interaction
        """
        await interaction.response.defer(thinking=True)
        model = self.values[0]
        
        # Handle "Default" special case
        if model == "Default":
            model = self.cog.default_model
            
        # Call the LLM with the selected model
        result = await self.cog.try_all_chat_endpoints(self.prompt, model)
        
        if result.get("success"):
            content = result.get("content", "")
            view = RegenerateView(self.cog, self.prompt, model, interaction)
            
            if len(content) <= MAX_RESPONSE_LENGTH:
                await interaction.followup.send(f"**Model: {model}**\n\n{content}", view=view)
            else:
                # Truncate and indicate it was truncated
                truncated_content = content[:MAX_RESPONSE_LENGTH] + "\n\n*[Response truncated due to Discord length limit]*" 
                await interaction.followup.send(f"**Model: {model}**\n\n{truncated_content}", view=view)
        else:
            # Format error message
            error_embed = self.cog.create_error_embed(
                result.get('error', 'Unknown Error'),
                f"Failed with model {model}",
                result.get('details', 'No details available.')
            )
            await interaction.followup.send(embed=error_embed)


class OpenWebUICog(commands.Cog, name="OpenWebUI"):
    """
    Interact with an OpenWebUI instance using its API.
    Provides commands for asking questions, listing models, and diagnostics.
    """

    def __init__(self, bot: commands.Bot):
        """
        Initialize the OpenWebUI cog.
        
        Args:
            bot: The bot instance
        """
        self.bot = bot
        # Access config from the bot instance
        self.config = getattr(bot, 'config', {})
        if hasattr(bot, 'config_manager'):
            self.config_manager = bot.config_manager
        else:
            self.config_manager = None

        # --- Configuration Loading ---
        self.api_base_url = self.config.get("openwebui_api_url")
        self.default_model = self.config.get("openwebui_default_model")

        self.api_key = None
        self.jwt_token = None

        # Flexible Authentication Key/Token Discovery
        possible_api_key_names = [
            "openwebui_api_key", "open_webui_api_key", "openwebui_token",
            "open_webui_token", "api_key"
        ]
        possible_jwt_names = ["openwebui_jwt_token", "open_webui_jwt_token", "jwt_token"]

        # Prioritize API Key
        for key_name in possible_api_key_names:
            key_value = self.config.get(key_name)
            if key_value:
                logger.info(f"Found API authentication key/token in config key: {key_name}")
                self.api_key = str(key_value).strip()
                break

        # Check for JWT if no specific API key found yet
        if not self.api_key:
            for key_name in possible_jwt_names:
                key_value = self.config.get(key_name)
                if key_value:
                    logger.info(f"Found JWT token in config key: {key_name}")
                    self.jwt_token = str(key_value).strip()
                    break

        # Heuristic: If a very long "API key" was found, treat it as JWT and clear API key
        if self.api_key and len(self.api_key) > 100:
            logger.info("Detected API key is very long (>100 chars), assuming it's a JWT token.")
            self.jwt_token = self.api_key
            self.api_key = None

        # --- API Endpoint Configuration ---
        # Default endpoint (OpenAI compatible, often preferred)
        self.api_endpoint = "/api/chat/completions"
        # Alternative endpoints to try sequentially if the primary one fails
        self.alternative_endpoints = [
            "/openai/chat/completions",
            "/v1/chat/completions",
            "/api/v1/chat/completions",
            "/ollama/api/chat",
            "/ollama/v1/chat/completions",
        ]
        
        # --- Conversation Management ---
        self.conversations = {}
        self.conversation_timeout = 1800  # 30 minutes of inactivity
        self.cleanup_task = self.bot.loop.create_task(self.cleanup_old_conversations())
        
        # --- Rate Limiting ---
        self.ask_limiter = RateLimiter(5, 60, "ask_command")  # 5 calls per minute
        self.model_list_limiter = RateLimiter(10, 60, "model_list")  # 10 calls per minute

        # Validate configuration on initialization
        self._validate_config()
        
    async def cog_unload(self) -> None:
        """
        Clean up resources when the cog is unloaded.
        """
        # Cancel cleanup task when cog is unloaded
        if hasattr(self, 'cleanup_task') and self.cleanup_task:
            self.cleanup_task.cancel()

    def _validate_config(self) -> None:
        """
        Performs initial validation of essential configuration and securely logs configuration state.
        """
        if not self.api_base_url:
            logger.error("CRITICAL: OPENWEBUI_API_URL is not configured in the bot's config!")
            logger.error("OpenWebUI Cog will be NON-FUNCTIONAL until this is set.")
            return

        logger.info(f"OpenWebUI Cog configured with API Base URL: {self.api_base_url}")
        if self.default_model:
            logger.info(f"Default model set to: {self.default_model}")
        else:
            logger.warning("OPENWEBUI_DEFAULT_MODEL is not set. Users must specify a model ID in the `!ask` command.")

        # Log authentication configuration securely
        if self.api_key:
            masked_key = SecurityUtils.mask_sensitive_value(self.api_key)
            logger.info(f"Using API Key authentication (masked: {masked_key})")
            
            # Validate API key format
            if len(self.api_key) < 8:
                logger.warning("API Key seems unusually short. This may not be a valid key.")
        elif self.jwt_token:
            masked_token = SecurityUtils.mask_sensitive_value(self.jwt_token)
            logger.info(f"Using JWT Token authentication (masked: {masked_token})")
            
            # Basic JWT structure validation (header.payload.signature)
            if not SecurityUtils.is_valid_jwt_format(self.jwt_token):
                logger.warning("JWT Token does not appear to have a valid format (header.payload.signature).")
        else:
            logger.warning("No API Key or JWT Token configured. Requests will be sent unauthenticated.")
            logger.warning("If your OpenWebUI requires authentication, commands will likely fail.")

        # Basic URL Parsing Check
        try:
            parsed_url = urlparse(self.api_base_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.error(f"Invalid OPENWEBUI_API_URL format: '{self.api_base_url}'. Missing scheme (http/https) or host.")
            else:
                logger.info(f"API URL parsed successfully: Scheme='{parsed_url.scheme}', Host='{parsed_url.netloc}'")
                # Log potential Docker-specific hostnames
                if parsed_url.hostname in ('host.docker.internal', 'docker.host.internal'):
                    logger.warning(f"Using Docker-specific hostname '{parsed_url.hostname}'. Ensure proper Docker network setup between bot and OpenWebUI containers.")
                
                # Security recommendation for production use
                if parsed_url.scheme == 'http' and not parsed_url.hostname in ('localhost', '127.0.0.1'):
                    logger.warning("Using unencrypted HTTP for a non-localhost connection. Consider using HTTPS for better security.")
        except ValueError as e:
            logger.error(f"Error parsing OPENWEBUI_API_URL '{self.api_base_url}': {e}")

    async def cleanup_old_conversations(self) -> None:
        """
        Periodically clean up expired conversations.
        """
        while not self.bot.is_closed():
            try:
                current_time = asyncio.get_event_loop().time()
                expired_users = []
                
                for user_id, convo in self.conversations.items():
                    if current_time - convo["last_updated"] > self.conversation_timeout:
                        expired_users.append(user_id)
                        
                for user_id in expired_users:
                    del self.conversations[user_id]
                    
                if expired_users:
                    logger.info(f"Cleaned up {len(expired_users)} expired conversations")
                    
                await asyncio.sleep(300)  # Check every 5 minutes
            except asyncio.CancelledError:
                logger.info("Conversation cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in conversation cleanup: {e}")
                await asyncio.sleep(60)  # Retry sooner if there was an error

    def get_conversation(self, user_id: str) -> Dict[str, Any]:
        """
        Get a user's conversation or create one.
        
        Args:
            user_id: The user ID
            
        Returns:
            Dict containing the conversation data
        """
        if user_id not in self.conversations:
            self.conversations[user_id] = {
                "messages": [],
                "last_updated": asyncio.get_event_loop().time(),
                "model": self.default_model
            }
        return self.conversations[user_id]
    
    def update_conversation(self, user_id: str, user_msg: str, assistant_msg: str, model: Optional[str] = None) -> None:
        """
        Update a conversation with new messages.
        
        Args:
            user_id: The user ID
            user_msg: The user's message
            assistant_msg: The assistant's response
            model: Optional model used for the conversation
        """
        convo = self.get_conversation(user_id)
        convo["messages"].append({"role": "user", "content": user_msg})
        convo["messages"].append({"role": "assistant", "content": assistant_msg})
        convo["last_updated"] = asyncio.get_event_loop().time()
        if model:
            convo["model"] = model

    async def _check_network_connectivity(self, url_to_check: str) -> Optional[str]:
        """
        Tests basic network connectivity (DNS, TCP) to the target host and port.
        
        Args:
            url_to_check: The URL to check connectivity to
            
        Returns:
            str: Error message if connectivity check failed, None if successful
        """
        try:
            parsed_url = urlparse(url_to_check)
            hostname = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)

            if not hostname:
                return f"Invalid URL: Could not extract hostname from '{url_to_check}'."

            # 1. Test DNS Resolution
            logger.debug(f"Testing DNS resolution for {hostname}...")
            start_time = asyncio.get_event_loop().time()
            try:
                # Use loop.getaddrinfo for async DNS resolution
                resolved_ip_info = await self.bot.loop.getaddrinfo(hostname, port, family=socket.AF_INET)
                resolved_ip = resolved_ip_info[0][4][0]
                dns_time = asyncio.get_event_loop().time() - start_time
                logger.info(f"DNS resolution successful for {hostname} -> {resolved_ip} ({dns_time:.3f}s)")
            except socket.gaierror as e:
                logger.error(f"DNS resolution failed for {hostname}: {e}")
                return f"DNS resolution failed for `{hostname}`: {e}. Check DNS settings for the bot's container/host."
            except Exception as e:
                logger.error(f"Unexpected error during DNS resolution for {hostname}: {e}")
                return f"Unexpected error during DNS resolution for `{hostname}`: {e}"

            # 2. Test TCP Connection
            logger.debug(f"Testing TCP connection to {hostname}:{port}...")
            start_time = asyncio.get_event_loop().time()
            conn = asyncio.open_connection(hostname, port)
            try:
                reader, writer = await asyncio.wait_for(conn, timeout=CONNECTION_TIMEOUT)
                conn_time = asyncio.get_event_loop().time() - start_time
                writer.close()
                await writer.wait_closed()
                logger.info(f"TCP connection successful to {hostname}:{port} ({conn_time:.3f}s)")
                return None  # Success
            except asyncio.TimeoutError:
                logger.error(f"TCP connection to {hostname}:{port} timed out after {CONNECTION_TIMEOUT}s.")
                return f"TCP connection timed out after {CONNECTION_TIMEOUT}s connecting to `{hostname}:{port}`. Check firewall rules or if the service is running/listening."
            except ConnectionRefusedError:
                logger.error(f"TCP connection refused by {hostname}:{port}.")
                return f"TCP connection refused by `{hostname}:{port}`. Ensure the OpenWebUI service is running and accessible on that port."
            except OSError as e:
                logger.error(f"TCP connection error to {hostname}:{port}: {e}")
                return f"TCP connection failed to `{hostname}:{port}`: {e}. Check network routes and firewall rules."
            except Exception as e:
                logger.error(f"Unexpected error during TCP connection to {hostname}:{port}: {e}")
                return f"Unexpected error during TCP connection to `{hostname}:{port}`: {e}"

        except Exception as e:
            logger.error(f"Error during connectivity check for '{url_to_check}': {e}", exc_info=True)
            return f"Unexpected error during connectivity check: {e}"

    async def _perform_api_request(self, method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout_secs: Optional[int] = None) -> Tuple[int, Optional[Union[Dict[str, Any], str]]]:
        """
        Helper to perform an authenticated API request and return status code and response body.
        
        Args:
            method: HTTP method to use
            endpoint: API endpoint to call
            payload: Optional request payload
            timeout_secs: Optional request timeout in seconds
            
        Returns:
            Tuple of (status_code, response_data)
        """
        if not self.api_base_url:
            return 503, {"error": "API Base URL not configured"}  # Service Unavailable

        full_url = urljoin(self.api_base_url, endpoint)
        headers = {'Accept': 'application/json'}  # Expect JSON responses
        if method.upper() in ['POST', 'PUT', 'PATCH'] and payload is not None:
            headers['Content-Type'] = 'application/json'

        # Add Authentication header if configured
        auth_method = "None"
        if self.jwt_token:
            headers['Authorization'] = f"Bearer {self.jwt_token}"
            auth_method = "JWT Token"
        elif self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"  # Standard Bearer for API keys too
            auth_method = "API Key"

        safe_url = SecurityUtils.sanitize_url_for_logging(full_url)
        logger.debug(f"Making {method} request to: {safe_url}")
        logger.debug(f"Auth Method: {auth_method}")
        
        if payload:
            # Avoid logging potentially large prompts directly, show structure/keys
            if "messages" in payload and isinstance(payload["messages"], list):
                messages_info = f"[{len(payload['messages'])} messages]"
                log_payload = {**payload, "messages": messages_info}
            else:
                log_payload = payload
                
            logger.debug(f"Payload: {json.dumps(log_payload)}")

        request_timeout = timeout_secs if timeout_secs is not None else API_TIMEOUT_SECONDS

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=request_timeout)) as session:
                async with session.request(method.upper(), full_url, headers=headers, json=payload) as response:
                    status_code = response.status
                    response_text = await response.text()
                    logger.debug(f"Response Status: {status_code}")
                    
                    # Log response preview, but avoid logging too much data
                    if len(response_text) > 500:
                        logger.debug(f"Response Body Preview (truncated): {response_text[:500]}...")
                    else:
                        logger.debug(f"Response Body: {response_text}")

                    # Attempt to parse JSON, return text if it fails
                    try:
                        # Handle empty response body for statuses like 204 No Content
                        if status_code == 204 or not response_text:
                            return status_code, None
                        response_data = json.loads(response_text)
                        return status_code, response_data
                    except json.JSONDecodeError:
                        logger.warning(f"Response from {endpoint} was not valid JSON (Status: {status_code}). Returning raw text.")
                        return status_code, response_text

        except asyncio.TimeoutError:
            logger.error(f"{method} request to {endpoint} timed out after {request_timeout} seconds.")
            return 504, {"error": "Request timed out", "details": f"The request to {endpoint} took longer than {request_timeout}s to complete."}
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error during {method} request to {endpoint}: {e}")
            # Extract hostname for clearer error message
            target_host = urlparse(full_url).netloc
            return 503, {"error": "Connection error", "details": f"Could not connect to {target_host}: {e}"}
        except aiohttp.ClientError as e:
            logger.error(f"Client error during {method} request to {endpoint}: {e}", exc_info=True)
            return 500, {"error": "HTTP Client error", "details": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error during {method} request to {endpoint}: {e}", exc_info=True)
            return 500, {"error": "Unexpected server error", "details": str(e)}

async def send_prompt_to_api(self, prompt: str, model: str, endpoint_override: Optional[str] = None, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Sends a prompt to the OpenWebUI API, handling endpoint selection and response parsing.
        
        Args:
            prompt: The prompt to send
            model: The model to use
            endpoint_override: Optional endpoint to use instead of the default
            conversation_history: Optional conversation history to include
            
        Returns:
            Dict containing the result
        """
        if not self.api_base_url:
            return {"success": False, "error": "Configuration Error", "details": "OpenWebUI API URL is not configured."}
        if not model:
            return {"success": False, "error": "Configuration Error", "details": "No model specified and no default model configured."}

        api_endpoint = endpoint_override or self.api_endpoint

        # Prepare payload with conversation history if provided
        if conversation_history:
            payload = {
                "model": model,
                "messages": conversation_history + [{"role": "user", "content": prompt}],
                "stream": False
            }
        else:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }

        status_code, response_data = await self._perform_api_request("POST", api_endpoint, payload)

        # --- Response Handling ---
        if status_code == 200 and isinstance(response_data, dict):
            # Try parsing different successful response structures
            content = None
            # 1. OpenAI standard format
            if 'choices' in response_data and isinstance(response_data['choices'], list) and response_data['choices']:
                message = response_data['choices'][0].get('message', {})
                content = message.get('content')
            # 2. Ollama direct format / Some OpenWebUI variations
            elif 'message' in response_data and isinstance(response_data['message'], dict):
                content = response_data['message'].get('content')
            # 3. Direct content key (less common)
            elif 'content' in response_data:
                content = response_data.get('content')
            # 4. Ollama non-streaming response (if 'stream: false' wasn't respected fully)
            elif 'response' in response_data:
                content = response_data.get('response')

            if content is not None:
                logger.info(f"Successfully received response from model '{model}' via endpoint '{api_endpoint}'")
                return {"success": True, "content": str(content).strip(), "endpoint": api_endpoint}
            else:
                logger.warning(f"API returned status 200 from {api_endpoint}, but response format was unexpected.")
                logger.warning(f"Response Data: {str(response_data)[:500]}...")
                return {
                    "success": False, "error": "Unexpected Response Format",
                    "details": f"API returned success (200) but the response structure didn't contain expected 'content'. Check logs.",
                    "status_code": status_code, "endpoint": api_endpoint, "raw_response": str(response_data)[:500]
                }

        # --- Error Handling ---
        error_details_str = str(response_data)  # Default to string representation
        error_msg = f"API request failed with status {status_code}"

        # Try to extract a more specific error message from JSON response
        if isinstance(response_data, dict):
            error_details_str = json.dumps(response_data)  # Use JSON string if it's a dict
            error_nested = response_data.get('error') or response_data.get('detail')  # Check common error keys
            if isinstance(error_nested, dict) and 'message' in error_nested:
                error_msg = error_nested['message']
            elif isinstance(error_nested, str):
                error_msg = error_nested

        log_message = f"API request to {api_endpoint} failed. Status: {status_code}. Response: {error_details_str[:500]}..."

        if status_code in [401, 403]:
            logger.error(log_message)
            return {
                "success": False, "error": f"Authentication Error ({status_code})",
                "details": f"Authentication failed. Check if API Key/JWT Token is correct and required. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code == 404:
            logger.error(log_message)
            return {
                "success": False, "error": f"Endpoint Not Found ({status_code})",
                "details": f"The endpoint `{api_endpoint}` was not found on the server. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code == 400:  # Bad Request (e.g., model not found, invalid prompt format)
            logger.error(log_message)
            # Check for common 'model not found' error
            if "model" in error_msg.lower() and ("not found" in error_msg.lower() or "no such file" in error_msg.lower()):
                error_title = f"Model Not Found ({status_code})"
                error_details_fmt = f"The requested model '{model}' was not found or available on the server via `{api_endpoint}`. Server response: `{error_msg}`"
            else:
                error_title = f"Bad Request ({status_code})"
                error_details_fmt = f"The server rejected the request as invalid. Server response: `{error_msg}`"

            return {
                "success": False, "error": error_title,
                "details": error_details_fmt,
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code == 405:  # Method Not Allowed
            logger.error(log_message)
            return {
                "success": False, "error": f"Method Not Allowed ({status_code})",
                "details": f"The endpoint `{api_endpoint}` does not support the POST method. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code == 503:  # Service Unavailable (often from our _perform_api_request connection error handling)
            logger.error(log_message)
            return {
                "success": False, "error": f"Service Unavailable ({status_code})",
                "details": f"Could not connect to the API server. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code == 504:  # Gateway Timeout (often from our _perform_api_request timeout handling)
            logger.error(log_message)
            return {
                "success": False, "error": f"Request Timeout ({status_code})",
                "details": f"The request timed out waiting for the API server. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        elif status_code >= 500:  # Other Server Errors
            logger.error(log_message)
            return {
                "success": False, "error": f"Server Error ({status_code})",
                "details": f"The API server encountered an internal error. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }
        else:  # Other client-side errors (4xx)
            logger.error(log_message)
            return {
                "success": False, "error": f"API Request Failed ({status_code})",
                "details": f"An unexpected error occurred. Server response: `{error_msg}`",
                "status_code": status_code, "endpoint": api_endpoint
            }

async def try_all_chat_endpoints(self, prompt: str, model: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Tries the primary chat endpoint, then alternatives, returning the first success or aggregated errors.
        
    Args:
        prompt: The prompt to send
        model: The model to use
        conversation_history: Optional conversation history to include
            
    Returns:
        Dict containing the result
    """
    # Deduplicate endpoints (in case default is also in alternatives)
    endpoints_to_try = [self.api_endpoint] + [ep for ep in self.alternative_endpoints if ep != self.api_endpoint]
    attempt_results = {}

    for i, endpoint in enumerate(endpoints_to_try):
        logger.info(f"Attempting chat request to endpoint #{i+1}/{len(endpoints_to_try)}: {endpoint}")
        result = await self.send_prompt_to_api(prompt, model, endpoint_override=endpoint, conversation_history=conversation_history)
        attempt_results[endpoint] = result  # Store result for this endpoint

        if result.get("success"):
            logger.info(f"Successfully got chat response from endpoint: {endpoint}. Setting as primary for future requests.")
            self.api_endpoint = endpoint  # Update the default endpoint to the working one
            return result  # Return the successful result immediately
                
        else:
            logger.warning(f"Chat request failed for endpoint {endpoint}: {result.get('error')} ({result.get('status_code', 'N/A')}) - {result.get('details')}")
            # Don't stop, try the next endpoint unless it's an auth error that will likely repeat
            if result.get("status_code") in [401, 403]:
                logger.warning("Authentication error detected. Subsequent endpoint attempts might also fail.")
                # Consider stopping early if needed, but for now we try all

        # If loop finishes, all endpoints failed
        logger.error("All configured chat API endpoints failed.")
        # Compile a summary error message
        error_summary = "Failed to get response from OpenWebUI after trying all configured endpoints:\n\n"
        for endpoint, res in attempt_results.items():
            error_summary += f"- **`{endpoint}`**: {res.get('error', 'Unknown Error')} ({res.get('status_code', 'N/A')}) - {res.get('details', 'No details')}\n"

        # Optionally run a basic network check if all fail
        network_check_result = await self._check_network_connectivity(self.api_base_url)
        if network_check_result:
            error_summary += f"\n**Network Connectivity Check:**\n- ❌ {network_check_result}\n"
        else:
            error_summary += "\n**Network Connectivity Check:**\n- ✅ Basic DNS and TCP connection seem OK.\n"

        return {
            "success": False,
            "error": "All API Endpoints Failed",
            "details": error_summary,
            "all_results": attempt_results  # Include detailed results for debugging
        }

    def create_error_embed(self, title: str, description: str, details: str) -> discord.Embed:
        """
        Creates a standardized error embed for consistent error reporting.
        
        Args:
            title: Error title
            description: Short error description
            details: Detailed error message
            
        Returns:
            discord.Embed: Formatted error embed
        """
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red()
        )
        
        # Add details, limiting length
        details_field_value = details
        if len(details_field_value) > 1020:
            details_field_value = details_field_value[:1020] + "..."
        embed.add_field(name="Details", value=f"```{details_field_value}```", inline=False)
        
        embed.add_field(name="Troubleshooting", value="Try `!diagnose_api` or `!openwebui_models` for more information.", inline=False)
        
        # Add timestamp for error reference
        embed.timestamp = datetime.datetime.now()
        
        return embed

    # --- Discord Commands ---
    @commands.command(name='ask', aliases=['chat', 'llm'], help='Ask a question to the configured LLM.\nUsage: `!ask [optional_model_id] <your prompt>`')
    async def ask_command(self, ctx: Context, *, argument_string: Optional[str] = None) -> None:
        """
        Sends a prompt to the configured OpenWebUI LLM, allowing optional model override.
        
        Args:
            ctx: The command context
            argument_string: The prompt with optional model ID prefix
        """
        # Check if user is rate limited
        user_id = str(ctx.author.id)
        if self.ask_limiter.is_rate_limited(user_id):
            time_left = self.ask_limiter.time_remaining(user_id)
            await ctx.send(f"⏳ Rate limit reached. Please try again in {time_left} seconds.", 
                          delete_after=10)
            return
            
        # Register this call
        self.ask_limiter.add_call(user_id)
        
        if not self.api_base_url:
            await ctx.send("❌ **Error:** The OpenWebUI API integration is not configured (missing API URL).")
            return

        if not argument_string:
            await ctx.send(f"Usage: `{ctx.prefix}{ctx.invoked_with} [optional_model_id] <your prompt>`\nExample: `{ctx.prefix}{ctx.invoked_with} llama3:latest Tell me a joke`")
            return

        # Argument Parsing: Check if the first word looks like a model ID
        args = argument_string.split()
        model_to_use = self.default_model
        prompt = argument_string  # Default prompt is the full string

        # Simple check: if first word contains ':' or '/' and there's more than one word
        potential_model = args[0]
        # Allow single-word model IDs if they contain typical separators
        if len(args) >= 1 and (':' in potential_model or '/' in potential_model):
            # Check if it's likely a model ID even if it's the only argument
            if len(args) == 1:
                # If it's the only word, treat it as part of the prompt
                pass
            else:  # More than one word, first looks like model ID
                model_to_use = potential_model
                prompt = " ".join(args[1:])
                logger.info(f"User specified model override: '{model_to_use}'")

        if not model_to_use:
            # No override detected AND no default model configured
            await ctx.send(f"❌ **Error:** No default model is set, and no model was specified. Please specify a model ID before your prompt.\nExample: `{ctx.prefix}{ctx.invoked_with} llama3:latest {prompt}`\nUse `{ctx.prefix}openwebui_models` to see available models.")
            return

        logger.info(f"LLM request from {ctx.author} (ID: {ctx.author.id}): Model='{model_to_use}', Prompt='{prompt[:100]}...'")

        # Get user's conversation
        convo = self.get_conversation(user_id)

        async with ctx.typing():
            try:
                # Use conversation history with the API
                result = await self.try_all_chat_endpoints(
                    prompt, 
                    model_to_use,
                    conversation_history=convo["messages"]
                )

                if result.get("success"):
                    content = result.get("content", "")
                    logger.info(f"LLM response length: {len(content)} chars.")
                    
                    # Update conversation with the new exchange
                    self.update_conversation(user_id, prompt, content, model_to_use)
                    
                    if len(content) == 0:
                        await ctx.send("Received an empty response from the model.")
                    elif len(content) <= MAX_RESPONSE_LENGTH:
                        # Create UI components
                        view = RegenerateView(self, prompt, model_to_use, ctx)
                        await ctx.send(content, view=view)
                    else:
                        logger.warning(f"Response truncated from {len(content)} to {MAX_RESPONSE_LENGTH} chars.")
                        view = RegenerateView(self, prompt, model_to_use, ctx)
                        await ctx.send(content[:MAX_RESPONSE_LENGTH] + "\n\n*[Response truncated due to Discord length limit]*", view=view)
                else:
                    # Handle failure after trying all endpoints
                    error_title = result.get('error', 'Unknown API Error')
                    error_details = result.get('details', 'No details provided.')
                    logger.error(f"Failed ask command: {error_title} - Details: {error_details[:500]}...")

                    # Format a user-friendly error message using the standard method
                    error_embed = self.create_error_embed(
                        error_title,
                        f"Failed to get a response from the OpenWebUI API for model `{model_to_use}`.",
                        error_details
                    )

                    # Add specific advice based on error patterns
                    if "Authentication Error" in error_title:
                        error_embed.add_field(name="Auth Tip", value="Check API key/token config (`!debug_env`) or use `!set_api_key`/`!set_jwt_token` (admin).", inline=False)
                    elif "Model Not Found" in error_title:
                        error_embed.add_field(name="Model Tip", value=f"Ensure model `{model_to_use}` exists and is loaded. Use `!openwebui_models` to check.", inline=False)
                    elif "Connection error" in error_title or "timed out" in error_details or "Service Unavailable" in error_title:
                        error_embed.add_field(name="Connection Tip", value="Check if the OpenWebUI server at the configured URL is running and accessible from the bot. Check URL and firewalls.", inline=False)

                    await ctx.send(embed=error_embed)

            except Exception as e:
                logger.exception(f"Unhandled exception in ask_command for prompt '{prompt[:50]}...'")
                await ctx.send(f"An unexpected internal error occurred: `{e}`. Please check the bot logs.")

    @commands.command(name='clear_chat', help='Clear your conversation history with the bot')
    async def clear_conversation(self, ctx: Context) -> None:
        """
        Clear a user's conversation history.
        
        Args:
            ctx: The command context
        """
        user_id = str(ctx.author.id)
        if user_id in self.conversations:
            del self.conversations[user_id]
            await ctx.send("✅ Your conversation history has been cleared.")
        else:
            await ctx.send("No active conversation found.")

    @commands.command(name='openwebui_models', aliases=['list_models', 'models'], help='List available models from the OpenWebUI instance.')
    async def list_models(self, ctx: Context) -> None:
        """
        Fetches and lists available models by trying various known API endpoints.
        
        Args:
            ctx: The command context
        """
        # Check if user is rate limited
        user_id = str(ctx.author.id)
        if self.model_list_limiter.is_rate_limited(user_id):
            time_left = self.model_list_limiter.time_remaining(user_id)
            await ctx.send(f"⏳ Rate limit reached. Please try again in {time_left} seconds.", 
                          delete_after=10)
            return
            
        # Register this call
        self.model_list_limiter.add_call(user_id)
        
        if not self.api_base_url:
            await ctx.send("❌ **Error:** OpenWebUI API URL is not configured.")
            return

        initial_msg = await ctx.send("⏳ Fetching available models from OpenWebUI...")

        # Define potential model listing endpoints, ordered by likelihood/preference
        model_endpoints = [
            "/api/v1/models",
            "/ollama/api/tags",
            "/v1/models",
            "/openai/v1/models",
            "/api/models",
            "/openai/models",
        ]

        endpoint_errors = {}
        available_models = []
        
        async with ctx.typing():
            for endpoint in model_endpoints:
                logger.info(f"Attempting to fetch models from endpoint: {endpoint}")
                # Use a reasonable timeout for listing models
                status_code, response_data = await self._perform_api_request("GET", endpoint, timeout_secs=CONNECTION_TIMEOUT)

                if status_code == 200 and isinstance(response_data, (dict, list)):  # Allow list response too
                    models_list = []
                    # --- Try different common response structures ---
                    # 1. Ollama / Newer OpenWebUI: {"models": [{"name": "...", "details": {...}}, ...]}
                    if isinstance(response_data, dict) and "models" in response_data and isinstance(response_data["models"], list):
                        models_list = response_data["models"]
                        logger.info(f"Parsed {len(models_list)} models using 'models' key from {endpoint}.")
                    # 2. OpenAI compatible: {"data": [{"id": "...", ...}, ...]}
                    elif isinstance(response_data, dict) and "data" in response_data and isinstance(response_data["data"], list):
                        for model_info in response_data["data"]:
                            if isinstance(model_info, dict) and "id" in model_info:
                                # Adapt OpenAI format to Ollama-like for consistency downstream
                                models_list.append({"name": model_info["id"], **model_info})
                        logger.info(f"Parsed {len(models_list)} models using 'data' key from {endpoint}.")
                    # 3. Simple list of model dicts (Ollama /tags might return this directly)
                    elif isinstance(response_data, list):
                        models_list = [item for item in response_data if isinstance(item, dict) and ('id' in item or 'name' in item)]
                        logger.info(f"Parsed {len(models_list)} models from a direct list response from {endpoint}.")

                    # --- Format and Send ---
                    if models_list:
                        # Store model names for potential UI selection
                        model_names = []
                        for model in models_list:
                            if "name" in model:
                                model_names.append(model["name"])
                            elif "id" in model:
                                model_names.append(model["id"])
                        available_models.extend(model_names)
                                
                        models_str = f"## Available Models (from `{endpoint}`)\n\n"
                        for model in sorted(models_list, key=lambda x: x.get('name', '') or x.get('id', '')):  # Sort alphabetically
                            name = model.get('name') or model.get('id', 'Unknown ID')
                            details = []
                            # Add size if available (Ollama format)
                            if 'size' in model and isinstance(model['size'], (int, float)):
                                gb_size = model['size'] / (1024**3)
                                details.append(f"{gb_size:.2f} GB")
                            # Add modified time if available (Ollama format)
                            if 'modified_at' in model:
                                mod_at = model['modified_at']
                                if isinstance(mod_at, str) and len(mod_at) >= 10:
                                    details.append(f"Modified: {mod_at[:10]}")  # Date only
                            # Add owner if available (OpenAI format)
                            if 'owned_by' in model:
                                details.append(f"Owner: {model['owned_by']}")

                            models_str += f"- `{name}`"
                            if details:
                                models_str += f" ({', '.join(details)})"
                            models_str += "\n"

                        if len(models_str) > MAX_RESPONSE_LENGTH:
                            models_str = models_str[:MAX_RESPONSE_LENGTH - 50] + "\n... *(list truncated)*"

                        try:
                            await initial_msg.edit(content=models_str)
                            
                            # If we have model names, offer model selection for a prompt
                            if available_models and len(available_models) > 1:
                                await ctx.send("Would you like to try one of these models? Use `!ask <model> <prompt>` to specify a model.")
                                
                            return  # Success!
                        except discord.HTTPException as e:
                            logger.error(f"Failed to edit models list message: {e}")
                            await ctx.send(models_str)  # Fallback to sending new message
                            return

                    else:
                        logger.warning(f"Endpoint {endpoint} returned 200 OK but no models found or structure unrecognized.")
                        endpoint_errors[endpoint] = f"Status {status_code}, empty or unrecognized format"
                        # Continue to next endpoint

                elif status_code == 404:
                    logger.info(f"Endpoint {endpoint} not found (404). Trying next.")
                    endpoint_errors[endpoint] = f"Status {status_code} (Not Found)"
                    continue
                elif status_code in [401, 403]:
                    logger.warning(f"Authentication error ({status_code}) accessing {endpoint}.")
                    endpoint_errors[endpoint] = f"Status {status_code} (Authentication Failed)"
                    # Might be worth stopping if auth fails consistently, but let's try others for now
                    continue
                else:  # Other errors
                    logger.warning(f"Failed to fetch models from {endpoint}. Status: {status_code}. Response: {str(response_data)[:200]}...")
                    error_detail = f"Status {status_code}"
                    if isinstance(response_data, dict) and 'error' in response_data:
                        error_detail += f" - {response_data['error']}"
                    elif isinstance(response_data, str) and len(response_data) < 100:
                        error_detail += f" - {response_data}"
                    endpoint_errors[endpoint] = error_detail
                    continue  # Try next endpoint

            # If loop finishes, all endpoints failed
            logger.error("Failed to fetch models from all attempted endpoints.")
            error_details_str = "\n".join([f"- `{ep}`: {err}" for ep, err in endpoint_errors.items()])
            final_content = (f"❌ **Error:** Failed to fetch models from any known OpenWebUI endpoint.\n"
                           f"**Errors encountered:**\n{error_details_str}\n\n"
                           f"Ensure the OpenWebUI server is running and accessible. You might need to check authentication (`!test_auth`) or use `!diagnose_api`.")
            try:
                await initial_msg.edit(content=final_content)
            except discord.HTTPException as e:
                logger.error(f"Failed to edit final models error message: {e}")
                await ctx.send(final_content)  # Fallback

    @commands.command(name='diagnose_api', help='Run detailed diagnostics on the OpenWebUI API connection.')
    async def diagnose_api(self, ctx: Context) -> None:
        """
        Performs network and API endpoint checks for troubleshooting.
        
        Args:
            ctx: The command context
        """
        if not self.api_base_url:
            await ctx.send("❌ **Error:** OpenWebUI API URL (`OPENWEBUI_API_URL`) is not configured.")
            return

        # --- Send initial status message and store it ---
        initial_text = f"⚙️ Running diagnostics for OpenWebUI API at `{self.api_base_url}`..."
        try:
            status_message = await ctx.send(initial_text)
        except discord.Forbidden:
            await ctx.send("❌ Error: I don't have permission to send messages in this channel.")
            return
        except Exception as e:
            await ctx.send(f"❌ Error sending initial status message: {e}")
            logger.error(f"Failed to send initial diagnose_api message: {e}", exc_info=True)
            return

        report_embed = discord.Embed(title="OpenWebUI API Diagnostic Report", color=discord.Color.blue())
        report_embed.description = f"Testing connection and configuration for `{self.api_base_url}`."

        # Use ctx.typing() for the whole duration
        async with ctx.typing():
            try:  # Wrap the main logic in try/except to handle errors during diagnostics

                # 1. Configuration Summary
                config_summary = f"**Base URL:** `{self.api_base_url}`\n"
                config_summary += f"**Default Model:** `{self.default_model or 'Not Set'}`\n"
                auth_status = "None"
                if self.jwt_token: 
                    auth_status = "JWT Token Configured"
                elif self.api_key: 
                    auth_status = "API Key Configured"
                config_summary += f"**Authentication:** `{auth_status}`\n"
                config_summary += f"**Primary Chat Endpoint:** `{self.api_endpoint}`\n"
                report_embed.add_field(name="Configuration", value=config_summary, inline=False)
                # --- Edit the bot's message ---
                await status_message.edit(content=initial_text, embed=report_embed)

                # 2. Network Connectivity Check
                network_status = "Testing..."
                report_embed.add_field(name="Network Connectivity", value=network_status, inline=False)
                # --- Edit the bot's message ---
                await status_message.edit(content=initial_text, embed=report_embed)

                connectivity_result = await self._check_network_connectivity(self.api_base_url)
                if connectivity_result:
                    network_status = f"❌ **Failed:** {connectivity_result}"
                    report_embed.set_field_at(-1, name="Network Connectivity", value=network_status, inline=False)  # Update last field
                    report_embed.color = discord.Color.orange()
                    # --- Edit the bot's message ---
                    await status_message.edit(content=initial_text + "\n\nNetwork connectivity failed. Further endpoint tests skipped.", embed=report_embed)
                    return  # Stop diagnostics here
                else:
                    network_status = "✅ **Success:** DNS resolution and TCP connection OK."
                    report_embed.set_field_at(-1, name="Network Connectivity", value=network_status, inline=False)
                    report_embed.color = discord.Color.green()  # Tentatively green
                    # --- Edit the bot's message ---
                    await status_message.edit(content=initial_text, embed=report_embed)

                # 3. API Endpoint Tests (Common Health/Info/Model endpoints)
                endpoint_results = "Testing common endpoints...\n"
                report_embed.add_field(name="API Endpoint Checks", value=endpoint_results, inline=False)
                # --- Edit the bot's message ---
                await status_message.edit(content=initial_text, embed=report_embed)

                test_endpoints = [
                    "/health",
                    "/api/v1/models",
                    "/api/models",
                    "/ollama/api/tags",
                    "/api/version",
                    # Add a basic chat endpoint check with a dummy prompt
                    self.api_endpoint,
                ]
                all_endpoints_ok = True
                endpoints_tested_count = 0

                for endpoint in test_endpoints:
                    endpoints_tested_count += 1
                    logger.info(f"Diagnostic test: Checking endpoint {endpoint}")
                    method = "GET"
                    payload = None
                    # Use appropriate method/payload for chat endpoint test
                    is_chat_endpoint = "chat" in endpoint.lower()
                    if is_chat_endpoint:
method = "POST"
                        # Use default model if set, otherwise a placeholder that *might* fail but tests the endpoint
                        test_model = self.default_model or "test-model-for-diag"
                        payload = {"model": test_model, "messages": [{"role": "user", "content": "ping"}], "stream": False}

                    try:
                        # Perform request using the helper function with diagnostic timeout
                        status_code, response_data = await self._perform_api_request(method, endpoint, payload, timeout_secs=DIAGNOSTIC_TIMEOUT)

                        status_symbol = "❓"
                        status_text = f"Status {status_code}"
                        if status_code == 200:
                            status_symbol = "✅"
                            status_text += " (OK)"
                        elif status_code == 204:  # No Content (also OK for some endpoints like health)
                            status_symbol = "✅"
                            status_text += " (OK - No Content)"
                        elif status_code in [401, 403]:
                            status_symbol = "🔑"  # Key symbol for auth issues
                            status_text += " (Auth Error)"
                            all_endpoints_ok = False  # Consider auth failure significant
                        elif status_code == 404:
                            status_symbol = "ℹ️"  # Info symbol for Not Found
                            status_text += " (Not Found)"
                            # Don't mark as failure if *some* endpoints work
                        elif status_code == 400 and is_chat_endpoint and isinstance(response_data, dict):
                            # Check if it's a 'model not found' error during chat test
                            error_msg = str(response_data.get("error", ""))
                            if "model" in error_msg.lower() and "not found" in error_msg.lower():
                                status_symbol = "ℹ️"
                                status_text += f" (Model '{test_model}' Not Found)"
                            else:
                                status_symbol = "❌"
                                status_text += " (Bad Request)"
                                all_endpoints_ok = False
                        elif status_code == 503 and isinstance(response_data, dict) and "Connection error" in response_data.get("error", ""):
                            status_symbol = "❌"
                            status_text += " (Connection Error)"
                            all_endpoints_ok = False
                        elif status_code == 504 and isinstance(response_data, dict) and "timed out" in response_data.get("error", ""):
                            status_symbol = "❌"
                            status_text += " (Timeout)"
                            all_endpoints_ok = False
                        else:  # Treat other non-2xx codes as potential issues
                            status_symbol = "⚠️" if status_code < 500 else "❌"  # Warning for 4xx, Error for 5xx
                            status_text += " (Unexpected Status)"
                            all_endpoints_ok = False  # Any other failure is significant

                        endpoint_results += f"{status_symbol} `{method} {endpoint}`: {status_text}\n"

                    except Exception as e:
                        # Catch any errors within the diagnostic loop itself
                        logger.error(f"Error during diagnostic check of {endpoint}: {e}", exc_info=True)
                        endpoint_results += f"❌ `{method} {endpoint}`: Internal Check Error ({type(e).__name__})\n"
                        all_endpoints_ok = False

                    # Update embed incrementally
                    if len(endpoint_results) < 1000:  # Keep field value within limits
                        report_embed.set_field_at(-1, name=f"API Endpoint Checks ({endpoints_tested_count}/{len(test_endpoints)})", value=endpoint_results, inline=False)
                        # --- Edit the bot's message ---
                        await status_message.edit(content=initial_text, embed=report_embed)

                # Final update after tests
                if not all_endpoints_ok and report_embed.color != discord.Color.orange():  # Don't override orange from network failure
                    report_embed.color = discord.Color.orange()  # Downgrade color if issues found

                report_embed.set_field_at(-1, name="API Endpoint Checks (Completed)", value=endpoint_results, inline=False)

                # 4. Recommendations
                recommendations = ""
                parsed_url = urlparse(self.api_base_url)
                hostname = parsed_url.hostname

                if connectivity_result: 
                    recommendations += "- Fix the **Network Connectivity** issue reported above.\n"  # Should not happen due to early exit, but keep for safety
                if not all_endpoints_ok: 
                    recommendations += "- Review the **API Endpoint Checks** for specific errors (🔑=Auth, ℹ️=Not Found/Ignorable, ⚠️/❌=Failure).\n"
                if hostname in ('host.docker.internal', 'docker.host.internal'):
                    recommendations += f"- Since using `{hostname}`, ensure bot and OpenWebUI containers are on the **same Docker network** and can resolve each other's names.\n"
                if not self.api_key and not self.jwt_token:
                    recommendations += "- **Authentication** is not configured. If required by OpenWebUI, use `!set_api_key`/`!set_jwt_token` (admin) or set `OPENWEBUI_API_KEY`/`OPENWEBUI_JWT_TOKEN` env vars.\n"
                if not self.default_model:
                    recommendations += "- **Default model** is not set. Set `OPENWEBUI_DEFAULT_MODEL` or specify model in `!ask`.\n"
                if not recommendations:
                    recommendations = "✅ No major issues detected based on these tests. If problems persist, check OpenWebUI server logs."

                report_embed.add_field(name="Recommendations", value=recommendations, inline=False)
                
                # Add timestamp for reference
                report_embed.timestamp = datetime.datetime.now()

                # --- Edit the bot's message with final report ---
                await status_message.edit(content="Diagnostics Complete.", embed=report_embed)

            except discord.HTTPException as e:
                logger.error(f"Failed to edit diagnostic message: {e}")
                # Optionally send a final message if editing failed critically
                await ctx.send("Error updating diagnostic report message. Check logs.")
            except Exception as e:
                logger.exception("Unhandled exception during diagnose_api execution.")
                await status_message.edit(content=f"An unexpected error occurred during diagnostics: `{e}`")

    # --- Admin / Debug Commands ---
    @commands.command(name='debug_env', help='(Admin Only) Show relevant config and environment variables.')
    @commands.has_permissions(administrator=True)
    async def debug_env(self, ctx: Context) -> None:
        """
        Displays configuration and relevant environment variables for debugging. Sends via DM.
        
        Args:
            ctx: The command context
        """
        env_report = f"## OpenWebUI Cog Debug Information for {self.bot.user.name}\n\n"
        env_report += "**Note:** Sensitive values (keys, tokens) are masked.\n\n"

        # 1. Loaded Bot Configuration
        env_report += "### Bot Configuration (`bot.config`)\n"
        if self.config:
            for key, value in sorted(self.config.items()):
                # Mask sensitive values aggressively
                masked_value = str(value)
                if value is not None and ('key' in key.lower() or 'token' in key.lower() or 'secret' in key.lower() or 'password' in key.lower()):
                    masked_value = SecurityUtils.mask_sensitive_value(masked_value)
                elif value is None:
                    masked_value = "`None`"

                # Highlight relevant keys
                if "openwebui" in key.lower() or "api_key" in key.lower() or "token" in key.lower():
                    env_report += f"- **`{key}`**: `{masked_value}`\n"
                else:
                    env_report += f"- `{key}`: `{masked_value}`\n"
        else:
            env_report += "No configuration found in `bot.config`.\n"

        # 2. Cog's Interpreted Values
        env_report += "\n### Cog Internal State\n"
        env_report += f"- `api_base_url`: `{self.api_base_url or 'Not Set'}`\n"
        env_report += f"- `default_model`: `{self.default_model or 'Not Set'}`\n"
        api_key_status = SecurityUtils.mask_sensitive_value(self.api_key) if self.api_key else "`Not Set`"
        jwt_token_status = SecurityUtils.mask_sensitive_value(self.jwt_token) if self.jwt_token else "`Not Set`"
        env_report += f"- `api_key`: {api_key_status}\n"
        env_report += f"- `jwt_token`: {jwt_token_status}\n"
        env_report += f"- `current_chat_endpoint`: `{self.api_endpoint}`\n"

        # 3. Relevant System Environment Variables
        env_report += "\n### System Environment Variables (`os.environ`)\n"
        found_env_var = False
        relevant_prefixes = ["OPENWEBUI_", "OPEN_WEBUI_", "API_KEY", "JWT_TOKEN", "OLLAMA_"]
        for key, value in sorted(os.environ.items()):
            # Check if key *contains* relevant parts, case-insensitive, for wider match
            if any(part in key.upper() for part in relevant_prefixes):
                found_env_var = True
                # Mask sensitive values
                masked_value = value
                if 'key' in key.lower() or 'token' in key.lower() or 'secret' in key.lower() or 'password' in key.lower():
                    masked_value = SecurityUtils.mask_sensitive_value(value)
                env_report += f"- `{key}`: `{masked_value}`\n"

        if not found_env_var:
            env_report += "No potentially relevant system environment variables found.\n"

        # 4. Network Information (If this is helpful for debugging)
        env_report += "\n### Network Information\n"
        try:
            # Get hostname
            hostname = socket.gethostname()
            env_report += f"- Host: `{hostname}`\n"
            
            # Try to get local IP addresses
            ip_addresses = []
            for interface in socket.getaddrinfo(socket.gethostname(), None):
                ip = interface[4][0]
                # Filter out loopback addresses and IPv6
                if not ip.startswith('127.') and ':' not in ip:
                    ip_addresses.append(ip)
            
            if ip_addresses:
                env_report += f"- IP Addresses: `{', '.join(ip_addresses)}`\n"
            else:
                env_report += "- IP Addresses: Unable to determine\n"
                
            # If the OpenWebUI URL is set, try to resolve it
            if self.api_base_url:
                parsed_url = urlparse(self.api_base_url)
                if parsed_url.hostname:
                    try:
                        resolved_ip = socket.gethostbyname(parsed_url.hostname)
                        env_report += f"- API URL Hostname `{parsed_url.hostname}` resolves to: `{resolved_ip}`\n"
                    except socket.gaierror:
                        env_report += f"- API URL Hostname `{parsed_url.hostname}` could not be resolved\n"
        except Exception as e:
            env_report += f"- Error getting network info: {e}\n"

        # Send report via DM
        try:
            if len(env_report) > 1900:  # Discord DM limit
                # Split into multiple messages if too long
                parts = []
                while len(env_report) > 1900:
                    split_point = env_report.rfind('\n', 0, 1900)
                    if split_point == -1: 
                        split_point = 1900  # Force split if no newline found
                    parts.append(env_report[:split_point])
                    env_report = env_report[split_point:].lstrip()
                parts.append(env_report)

                for i, part in enumerate(parts):
                    await ctx.author.send(f"**Debug Info Part {i+1}/{len(parts)}**\n{part}")
            else:
                await ctx.author.send(env_report)

            await ctx.send(f"✅ Debug information sent to your DMs, {ctx.author.mention}.")
        except discord.Forbidden:
            await ctx.send("❌ Could not send DM. Please enable DMs from server members in your Privacy Settings.")
        except Exception as e:
            logger.error(f"Failed to send debug_env DM: {e}")
            await ctx.send("❌ An error occurred while trying to send the debug information via DM.")

    @commands.command(name='set_api_key', help='(Admin Only) Manually set/update the OpenWebUI API key.')
    @commands.has_permissions(administrator=True)
    async def set_api_key(self, ctx: Context, *, api_key: str) -> None:
        """
        Manually sets the API key for OpenWebUI, overriding config. Deletes invocation message.
        
        Args:
            ctx: The command context
            api_key: The API key to set
        """
        if not api_key:
            await ctx.send("❌ Please provide the API key value.")
            return

        original_message = ctx.message
        self.api_key = api_key.strip()
        self.jwt_token = None  # Clear JWT if setting API key explicitly
        logger.info(f"API key manually set/updated by {ctx.author} (ID: {ctx.author.id}). JWT token cleared.")

        masked_key = SecurityUtils.mask_sensitive_value(self.api_key)
        confirm_msg = await ctx.send(f"✅ OpenWebUI API key has been set to {masked_key}. JWT token (if any) was cleared.")

        # Try to delete the user's command message containing the key
        try:
            await original_message.delete()
            logger.debug("Successfully deleted user message containing API key.")
        except discord.Forbidden:
            logger.warning("Missing permissions to delete the user's message containing the API key.")
            await ctx.send("⚠️ Could not delete your message containing the key. Please delete it manually.", delete_after=15)
        except discord.NotFound:
            logger.debug("User message already deleted.")  # Race condition or manual deletion
        except Exception as e:
            logger.error(f"Error deleting user message: {e}")
            await ctx.send("⚠️ An error occurred trying to delete your message containing the key.", delete_after=15)
            
        # If we have a config manager, update the config
        if self.config_manager:
            # Save the API key in the config
            self.config_manager.set("openwebui_api_key", self.api_key, save=True)
            # Remove JWT token in the config
            self.config_manager.set("openwebui_jwt_token", None, save=True)
            logger.info("Updated config file with new API key and removed JWT token.")

    @commands.command(name='set_jwt_token', help='(Admin Only) Manually set/update the OpenWebUI JWT token.')
    @commands.has_permissions(administrator=True)
    async def set_jwt_token(self, ctx: Context, *, jwt_token: str) -> None:
        """
        Manually sets the JWT token for OpenWebUI, overriding config. Deletes invocation message.
        
        Args:
            ctx: The command context
            jwt_token: The JWT token to set
        """
        if not jwt_token:
            await ctx.send("❌ Please provide the JWT token value.")
            return

        original_message = ctx.message
        self.jwt_token = jwt_token.strip()
        self.api_key = None  # Clear API key if setting JWT explicitly
        logger.info(f"JWT token manually set/updated by {ctx.author} (ID: {ctx.author.id}). API key cleared.")

        masked_token = SecurityUtils.mask_sensitive_value(self.jwt_token)
        confirm_msg = await ctx.send(f"✅ OpenWebUI JWT token has been set to {masked_token}. API key (if any) was cleared.")

        # Try to delete the user's command message containing the token
        try:
            await original_message.delete()
            logger.debug("Successfully deleted user message containing JWT token.")
        except discord.Forbidden:
            logger.warning("Missing permissions to delete the user's message containing the JWT token.")
            await ctx.send("⚠️ Could not delete your message containing the token. Please delete it manually.", delete_after=15)
        except discord.NotFound:
            logger.debug("User message already deleted.")
        except Exception as e:
            logger.error(f"Error deleting user message: {e}")
            await ctx.send("⚠️ An error occurred trying to delete your message containing the token.", delete_after=15)
            
        # If we have a config manager, update the config
        if self.config_manager:
            # Save the JWT token in the config
            self.config_manager.set("openwebui_jwt_token", self.jwt_token, save=True)
            # Remove API key in the config
            self.config_manager.set("openwebui_api_key", None, save=True)
            logger.info("Updated config file with new JWT token and removed API key.")

    @commands.command(name='test_auth', help='(Admin Only) Test configured authentication against API.')
    @commands.has_permissions(administrator=True)
    async def test_auth(self, ctx: Context) -> None:
        """
        Tests if the currently configured authentication works against common API endpoints.
        
        Args:
            ctx: The command context
        """
        if not self.api_base_url:
            await ctx.send("❌ **Error:** OpenWebUI API URL is not configured.")
            return

        auth_method = "None"
        auth_header_value = None
        if self.jwt_token:
            auth_method = "JWT Token"
            auth_header_value = f"Bearer {self.jwt_token}"
        elif self.api_key:
            auth_method = "API Key"
            auth_header_value = f"Bearer {self.api_key}"

        initial_msg = await ctx.send(f"⚙️ Testing authentication (`{auth_method}`) against OpenWebUI at `{self.api_base_url}`...")

        # Use endpoints likely requiring auth or providing info
        test_endpoints = ["/api/me", "/api/v1/models", "/api/version"]
        results = []
        success = False
        auth_failure_detected = False

        async with ctx.typing():
            for endpoint in test_endpoints:
                logger.info(f"Auth test: Checking endpoint {endpoint} with method {auth_method}")
                # Use the internal method with a specific timeout
                status_code, response_data = await self._perform_api_request("GET", endpoint, timeout_secs=CONNECTION_TIMEOUT)

                result_str = f"`GET {endpoint}`: Status {status_code}"
                if status_code == 200:
                    result_str += " ✅ (OK)"
                    success = True  # At least one endpoint worked with auth (or didn't require it and was reachable)
                elif status_code in [401, 403]:
                    result_str += " ❌ (Authentication Failed/Forbidden)"
                    auth_failure_detected = True
                elif status_code == 404:
                    result_str += " ℹ️ (Not Found)"
                else:
                    result_str += f" ⚠️ (Unexpected Status: {status_code})"
                    # Include error message if available
                    error_msg = "N/A"
                    if isinstance(response_data, dict) and ('error' in response_data or 'detail' in response_data):
                        error_msg = response_data.get('error') or response_data.get('detail')
                    elif isinstance(response_data, str) and len(response_data) < 100:
                        error_msg = response_data
                    if error_msg != "N/A":
                        result_str += f" - `{error_msg}`"

                results.append(result_str)

            # --- Report Results ---
            report_embed = discord.Embed(title="OpenWebUI Authentication Test Report")
            report_embed.description = f"Tested using **{auth_method}** authentication against `{self.api_base_url}`."
            report_embed.add_field(name="Endpoint Test Results", value="\n".join(results), inline=False)

            if auth_failure_detected:
                report_embed.color = discord.Color.red()
                report_embed.add_field(name="Conclusion", value=f"❌ Configured **{auth_method}** failed for at least one endpoint likely requiring authentication. Check the key/token value and OpenWebUI server settings/logs.", inline=False)
            elif success:
                report_embed.color = discord.Color.green()
                report_embed.add_field(name="Conclusion", value="✅ Authentication seems to be working, or tested endpoints don't require it and are reachable.", inline=False)
            elif auth_method == "None":
                report_embed.color = discord.Color.orange()
                report_embed.add_field(name="Conclusion", value="⚠️ No authentication is configured. Some endpoints might work, but authenticated ones will likely fail if protection is enabled on the server.", inline=False)
            else:  # No success, no specific auth failure (e.g., all 404 or 5xx)
                report_embed.color = discord.Color.orange()
                report_embed.add_field(name="Conclusion", value="⚠️ Could not confirm authentication success. All tested endpoints failed for reasons other than explicit auth errors (e.g., Not Found, Server Error). Use `!diagnose_api` for more details.", inline=False)
                
            # Add timestamp for reference
            report_embed.timestamp = datetime.datetime.now()

            try:
                await initial_msg.edit(content="Authentication Test Complete.", embed=report_embed)
            except discord.HTTPException as e:
                logger.error(f"Failed to edit auth test message: {e}")
                await ctx.send(embed=report_embed)  # Fallback

    # --- Cog Event Listeners ---
    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError) -> None:
        """
        Handles errors specific to commands within this Cog.
        
        Args:
            ctx: The command context
            error: The error that occurred
        """
        # Ensure the error originated from a command in this cog
        if ctx.cog is not self or not ctx.command:
            return  # Pass error to global handler or other cogs

        log_prefix = f"Cog '{self.qualified_name}' - Command '{ctx.command.qualified_name}':"

        # Handle specific error types relevant to this cog
        if isinstance(error, commands.MissingPermissions):
            logger.warning(f"{log_prefix} User {ctx.author} (ID: {ctx.author.id}) missing permissions: {error.missing_permissions}")
            await ctx.send("❌ You do not have the necessary permissions (Administrator) to use this command.", delete_after=10)
            return True
        elif isinstance(error, commands.UserInputError):
            logger.info(f"{log_prefix} User input error: {error}")
            await ctx.send(f"❌ Invalid input: {error}\nPlease use `{ctx.prefix}help {ctx.command.qualified_name}` for usage details.")
            return True
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            logger.error(f"{log_prefix} Error during invocation: {original.__class__.__name__}: {original}", exc_info=True)  # Log full traceback
            await ctx.send(f"An unexpected error occurred while running the command: `{original.__class__.__name__}`. Please check the bot logs or contact an admin.")
            return True
        else:
            # Log other unexpected cog-level errors
            logger.error(f"{log_prefix} Unexpected error: {error}", exc_info=True)
            return False
    
    @commands.Cog.listener()
    async def on_config_update(self, key: str, value: Any) -> None:
        """
        Handle dynamic configuration updates for OpenWebUI config.
        
        Args:
            key: The configuration key that was updated
            value: The new value
        """
        if key == "openwebui_api_url":
            logger.info(f"OpenWebUI API URL updated to: {value}")
            self.api_base_url = value
        elif key == "openwebui_default_model":
            logger.info(f"OpenWebUI default model updated to: {value}")
            self.default_model = value
        elif key == "openwebui_api_key":
            masked_value = SecurityUtils.mask_sensitive_value(value) if value else "None"
            logger.info(f"OpenWebUI API key updated to: {masked_value}")
            self.api_key = value
            if value:  # If setting API key, clear JWT token for clarity
                self.jwt_token = None
        elif key == "openwebui_jwt_token":
            masked_value = SecurityUtils.mask_sensitive_value(value) if value else "None"
            logger.info(f"OpenWebUI JWT token updated to: {masked_value}")
            self.jwt_token = value
            if value:  # If setting JWT token, clear API key for clarity
                self.api_key = None


async def setup(bot: commands.Bot) -> None:
    """
    Load the OpenWebUICog into the bot.
    
    Args:
        bot: The bot instance
    """
    try:
        # Check required libraries are available
        import aiohttp
        import json
        import asyncio
        
        await bot.add_cog(OpenWebUICog(bot))
        logger.info("OpenWebUICog added to bot.")
    except ImportError as e:
        logger.critical(f"Missing required library for OpenWebUICog: {e}. Cog will not load.")
        raise commands.ExtensionFailed("OpenWebUICog", f"Missing required dependency: {e}")
    except Exception as e:
        logger.critical(f"Failed to load OpenWebUICog: {e}", exc_info=True)
        raise commands.ExtensionFailed("OpenWebUICog", f"Initialization error: {e}")