import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get as discord_get
from tinydb import Query
import random
import logging

from common.dataio import get_database

logger = logging.getLogger('galba.Snowfest')



class Snowfest(commands.Cog):
    """Jeu des fêtes de fin d'année 2022"""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
        self.snowball_ctxmenu = app_commands.ContextMenu(
            name='Boule de neige',
            callback=self.ctx_usercommand_snowball
        )
        self.bot.tree.add_command(self.snowball_ctxmenu)
        
    def snowball_cd(interaction: discord.Interaction):
        # if interaction.user.id == 172376505354158080:
        #     return None
        return app_commands.Cooldown(3, 300)
    
    @app_commands.checks.dynamic_cooldown(snowball_cd)
    async def ctx_usercommand_snowball(self, interaction: discord.Interaction, member: discord.Member):
        """Lancer une boule de neige sur le membre visé
        
        :param member: Membre visé
        """
        if not random.randint(0, 2):
            await interaction.response.send_message(f"Vous avez touché **{member.display_name}** !")
        else:
            await interaction.response.send_message(f"Désolé, vous avez loupé **{member.display_name}**...", ephemeral=True)
     
async def setup(bot):
    await bot.add_cog(Snowfest(bot))

