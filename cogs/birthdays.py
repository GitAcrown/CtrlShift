from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from tinydb import Query

from common.dataio import get_database


class Birthdays(commands.Cog):
    """Gestion et traçage des anniversaires"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @app_commands.command(name='bdayrole')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def bdayrole(self, interaction: discord.Interaction, role: discord.Role):
        """Rôle à attribuer automatiquement le jour de l'anniversaire

        :param role: Rôle à attribuer
        """
        db = get_database('birthdays', str(interaction.guild_id))
        Role = Query()
        db.table('settings').upsert({'name': 'role', 'value': role.id}, Role.name == 'role')
        
        await interaction.response.send_message(f"Le rôle a bien été configuré sur **{role}** !")
        
    
        
async def setup(bot):
    await bot.add_cog(Birthdays(bot))
