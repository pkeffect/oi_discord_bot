# ./tests/test_documentation_cog.py

import pytest
import discord.ext.commands as commands
import asyncio
import aiosqlite
import os
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Import the cog from the correct path
from cogs.documentation_cog import DocumentationCog, extract_title_from_markdown, generate_doc_url

@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    return tmp_path

@pytest.fixture
async def bot():
    """Create a mock bot for testing."""
    mock_bot = AsyncMock(spec=commands.Bot)
    mock_bot.config = {
        "DOCS_ZIP_URL": "https://example.com/docs.zip",
        "DOCS_BASE_URL": "https://docs.example.com/",
        "DOCS_PATH_IN_ZIP": "docs/",
    }
    mock_bot.loop = asyncio.get_event_loop()
    return mock_bot


@pytest.fixture
async def db_path(temp_dir):
    """Create a temporary database path."""
    return temp_dir / "test_docs_index.db"


@pytest.fixture
async def cog(bot, temp_dir, db_path):
    """Create an instance of the cog with patched paths for testing."""
    with patch.object(DocumentationCog, 'initialize_database', AsyncMock(return_value=None)):
        with patch.object(DocumentationCog, 'sync_docs_task'):
            cog = DocumentationCog(bot)
            # Override paths to use temp directory
            cog.app_dir = temp_dir
            cog.data_dir = temp_dir / "data"
            cog.docs_dir = temp_dir / "extracted_docs"
            cog.zip_path = temp_dir / "docs.zip"
            cog.db_path = db_path
            
            # Create necessary directories
            cog.data_dir.mkdir(exist_ok=True)
            cog.docs_dir.mkdir(exist_ok=True)
            
            yield cog
            
            # Cleanup
            if os.path.exists(db_path):
                os.remove(db_path)


class TestDocumentationCog:
    @pytest.mark.asyncio
    async def test_initialization(self, cog, bot):
        """Test proper initialization of the cog."""
        assert cog.docs_zip_url == "https://example.com/docs.zip"
        assert cog.docs_base_url == "https://docs.example.com/"
        assert cog.docs_path_in_zip == "docs/"

    @pytest.mark.asyncio
    async def test_initialize_database(self, cog, db_path):
        """Test database initialization."""
        # Call the method directly (skipping the mocked version)
        await DocumentationCog.initialize_database(cog)
        
        # Verify the database was created with correct tables
        async with aiosqlite.connect(db_path) as db:
            # Check if docs_meta table exists
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_meta';")
            result = await cursor.fetchone()
            assert result is not None
            
            # Check if FTS table exists
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_content';")
            result = await cursor.fetchone()
            assert result is not None

    @pytest.mark.parametrize("content,fallback,expected", [
        ("# Test Title\nContent", "fallback", "Test Title"),
        ("---\ntitle: 'Custom Title'\n---\nContent", "fallback", "Custom Title"),
        ("No title here", "fallback_name", "Fallback Name"),  # Fallback with formatting
    ])
    def test_extract_title_from_markdown(self, content, fallback, expected):
        """Test title extraction from markdown."""
        if fallback == "fallback_name":
            # Test the formatting of the fallback
            result = extract_title_from_markdown(content, "fallback-name")
            assert result == "Fallback Name"
        else:
            result = extract_title_from_markdown(content, fallback)
            assert result == expected

    @pytest.mark.parametrize("path,base_url,expected", [
        ("docs/page.md", "https://docs.example.com/", "https://docs.example.com/docs/page"),
        ("docs/index.md", "https://docs.example.com/", "https://docs.example.com/docs/"),
        ("index.md", "https://docs.example.com/", "https://docs.example.com/"),
    ])
    def test_generate_doc_url(self, path, base_url, expected):
        """Test URL generation from paths."""
        result = generate_doc_url(path, base_url)
        assert result == expected

    @pytest.mark.asyncio
    async def test_search_documentation(self, cog, db_path):
        """Test the search functionality."""
        # First initialize and set up a test database
        await DocumentationCog.initialize_database(cog)
        
        # Insert test data
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                INSERT INTO docs_meta (filepath, title, url, h1_content, h2_content, 
                                      other_headings, bold_content, body_content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("test/path.md", "Test Document", "https://example.com/test", 
                  "Main Heading", "Secondary Heading", "Other Heading", 
                  "Important Text", "This is a test document with searchable content."))
            await db.commit()
        
        # Test search with a matching query
        results = await cog.search_documentation("test document")
        assert len(results) > 0
        assert results[0]["title"] == "Test Document"
        
        # Test search with no matches
        results = await cog.search_documentation("nonexistent content")
        assert len(results) == 0