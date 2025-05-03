# In tests/test_openwebui_cog.py
import pytest
import discord.ext.commands as commands
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock

# Import your cog
from cogs.openwebui_cog import OpenWebUICog

class TestOpenWebUICog:
    @pytest.fixture
    async def bot(self):
        # Create a mock bot
        mock_bot = AsyncMock(spec=commands.Bot)
        mock_bot.config = {
            "OPENWEBUI_API_URL": "http://test.server",
            "OPENWEBUI_DEFAULT_MODEL": "test-model"
        }
        mock_bot.loop = asyncio.get_event_loop()
        return mock_bot
    
    @pytest.fixture
    async def cog(self, bot):
        # Create an instance of your cog
        cog = OpenWebUICog(bot)
        return cog
    
    @pytest.mark.asyncio
    async def test_init(self, cog, bot):
        # Test initialization
        assert cog.api_base_url == "http://test.server"
        assert cog.default_model == "test-model"
        
    @pytest.mark.asyncio
    async def test_perform_api_request_success(self, cog, bot):
        # Mock the aiohttp ClientSession
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value=json.dumps({"success": True}))
        
        mock_session = AsyncMock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_session.request.return_value = mock_context_manager
        
        with patch('aiohttp.ClientSession', return_value=mock_session):
            status, data = await cog._perform_api_request("GET", "/test-endpoint")
            
            assert status == 200
            assert data == {"success": True}
            mock_session.request.assert_called_once_with(
                "GET", 
                "http://test.server/test-endpoint", 
                headers={"Accept": "application/json"}, 
                json=None
            )
    
    @pytest.mark.asyncio
    async def test_send_prompt_to_api(self, cog, bot):
        # Mock the _perform_api_request method
        mock_result = (200, {
            "choices": [{"message": {"content": "Test response"}}]
        })
        
        with patch.object(cog, '_perform_api_request', return_value=mock_result):
            result = await cog.send_prompt_to_api("Test prompt", "test-model")
            
            assert result["success"] == True
            assert result["content"] == "Test response"
            assert result["endpoint"] == cog.api_endpoint

# In tests/conftest.py
# Common fixtures and setup

# Create a pytest.ini file
"""
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
"""

# In requirements-dev.txt - Add development dependencies
"""
pytest>=7.0.0
pytest-asyncio>=0.18.0
pytest-cov>=3.0.0
"""