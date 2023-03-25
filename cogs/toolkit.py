import logging

import random
import discord
from discord import app_commands
from discord.ext import commands

from PIL import Image, ImageDraw, ImageFont, ImageOps

from common.utils import pretty, fuzzy
from common.dataio import get_sqlite_database

logger = logging.getLogger('ctrlshift.Toolkit')

        
class Toolkit(commands.Cog):
    """Outils divers"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    def simulate_dice(self, sides: int, count: int, step: int) -> list[int]:
        """Simule un ou plusieurs dés"""
        faces = tuple(range(step, sides + 1, step))
        return [random.choice(faces) for _ in range(count)]
    
    @app_commands.command(name='dice')
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 1] = 6, count: app_commands.Range[int, 1] = 1, step: app_commands.Range[int, 1] = 1):
        """Simule un ou plusieurs dés
        
        :param sides: Nombre de faces du dé
        :param count: Nombre de dés à lancer
        :param step: Pas entre chaque face"""
        results = self.simulate_dice(sides, count, step)
        die_name = f'd{sides}'
        if step > 1:
            die_name += f'[{step}]'
        if count > 1:
            die_name += f' x{count}'
        
        await interaction.response.send_message(f'🎲 **{die_name}** : `{", ".join(map(str, results))}`{f" = ***{sum(results)}***" if count > 1 else ""}')
    
    
async def setup(bot: commands.Bot):
    cog = Toolkit(bot)
    await bot.add_cog(cog)