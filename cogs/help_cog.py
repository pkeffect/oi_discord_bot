# In cogs/help_cog.py - Create a custom help system

class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot):
        self.bot = bot
        # Remove the default help command
        self.bot.remove_command('help')
        
    @commands.group(invoke_without_command=True)
    async def help(self, ctx, *, command_name=None):
        """Improved help command with categories and examples."""
        prefix = ctx.prefix
        
        if command_name is None:
            # Show main help menu with categories
            embed = discord.Embed(
                title="Bot Help",
                description=f"Use `{prefix}help <category>` for more info on a category.\n"
                           f"Use `{prefix}help <command>` for more info on a command.",
                color=discord.Color.blue()
            )
            
            # Define categories
            categories = {
                "🧠 OpenWebUI": ["ask", "openwebui_models", "diagnose_api", "test_auth"],
                "📚 Documentation": ["docs", "syncdocs"],
                "🔍 Model Search": ["osearch"],
                "🎥 Media": ["youtube", "yt"],
                "⚙️ Utility": ["ping"],
                "🛡️ Admin": ["set_api_key", "set_jwt_token", "debug_env", "reload_logger_config"],
            }
            
            # Add fields for each category
            for category, commands_list in categories.items():
                command_text = ", ".join(f"`{prefix}{cmd}`" for cmd in commands_list)
                embed.add_field(name=category, value=command_text, inline=False)
                
            embed.set_footer(text="Tip: Type !help <command> for detailed help on a command")
            await ctx.send(embed=embed)
            
        else:
            # Check if it's a category
            categories = {
                "openwebui": "🧠 OpenWebUI",
                "documentation": "📚 Documentation",
                "modelsearch": "🔍 Model Search",
                "media": "🎥 Media",
                "utility": "⚙️ Utility", 
                "admin": "🛡️ Admin",
            }
            
            lowered = command_name.lower()
            
            if lowered in categories:
                await self.send_category_help(ctx, lowered, categories[lowered])
                return
            
            # It's a command, show specific help
            command = self.bot.get_command(command_name)
            
            if command is None:
                await ctx.send(f"❌ Command or category `{command_name}` not found.")
                return
                
            await self.send_command_help(ctx, command)
    
    async def send_category_help(self, ctx, category_id, category_name):
        """Send help for a specific category."""
        prefix = ctx.prefix
        embed = discord.Embed(
            title=f"{category_name} Commands",
            color=discord.Color.blue()
        )
        
        # Map category IDs to commands and their descriptions
        category_commands = {
            "openwebui": [
                ("ask", "Ask a question to the LLM", f"`{prefix}ask What is OpenWebUI?`\n`{prefix}ask llama3:latest Tell me a joke`"),
                ("openwebui_models", "List available models", f"`{prefix}openwebui_models`"),
                ("diagnose_api", "Test API connectivity", f"`{prefix}diagnose_api`"),
            ],
            "documentation": [
                ("docs", "Search documentation", f"`{prefix}docs installation`\n`{prefix}docs api reference`"),
                ("syncdocs", "Manually sync docs (admin)", f"`{prefix}syncdocs`"),
            ],
            # Add other categories...
        }
        
        # Get commands for this category
        commands_info = category_commands.get(category_id, [])
        
        if not commands_info:
            embed.description = "No commands found for this category."
        else:
            for name, desc, example in commands_info:
                embed.add_field(
                    name=f"`{prefix}{name}`",
                    value=f"**Description:** {desc}\n**Example:**\n{example}",
                    inline=False
                )
                
        await ctx.send(embed=embed)
    
    async def send_command_help(self, ctx, command):
        """Send help for a specific command."""
        prefix = ctx.prefix
        
        embed = discord.Embed(
            title=f"Help: {prefix}{command.name}",
            color=discord.Color.blue()
        )
        
        # Add command description
        if command.help:
            embed.description = command.help
        else:
            embed.description = "No description available."
            
        # Add usage
        usage = f"{prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
        
        # Add aliases if any
        if command.aliases:
            aliases = ", ".join(f"`{prefix}{alias}`" for alias in command.aliases)
            embed.add_field(name="Aliases", value=aliases, inline=False)
            
        # Add examples (manually defined)
        examples = {
            "ask": f"`{prefix}ask What is OpenWebUI?`\n`{prefix}ask llama3:latest Explain quantum computing`",
            "docs": f"`{prefix}docs installation`\n`{prefix}docs api reference`",
            "osearch": f"`{prefix}osearch llama`\n`{prefix}osearch mistral`",
            # Add more examples for each command
        }
        
        if command.name in examples:
            embed.add_field(name="Examples", value=examples[command.name], inline=False)
            
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCog(bot))