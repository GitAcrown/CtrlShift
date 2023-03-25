import logging

import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

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
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 1] = 6, count: app_commands.Range[int, 1, 50] = 1, step: app_commands.Range[int, 1] = 1):
        """Simule un ou plusieurs dés
        
        :param sides: Nombre de faces du dé
        :param count: Nombre de dés à lancer
        :param step: Pas entre chaque face"""
        results = self.simulate_dice(sides, count, step)
        die_name = f'd{sides}'
        if step > sides:
            return await interaction.response.send_message(f"**Erreur ·** Le pas doit être inférieur ou égal au nombre de faces ({sides})")
        if step > 1:
            die_name += f'[{step}]'
        if count > 1:
            die_name += f' x{count}'
        
        dice_txt = "\n".join(f"{result}" for _, result in enumerate(results))
        if count > 1:
            dice_txt += f"\n------\n= {sum(results)}"
        
        embed = discord.Embed(title=f"🎲 **{die_name}**", description=f"```css\n{dice_txt}```", color=0x2b2d31)
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='choose')
    async def choose(self, interaction: discord.Interaction, items: str, weights: Optional[str] = '', elements: app_commands.Range[int, 1] = 1):
        """Choisi un élément aléatoire dans une liste (avec remise)
        
        :param items: Liste d'éléments séparés par des virgules
        :param weights: Liste de poids séparés par des virgules, dans l'ordre des items
        :param elements: Nombre d'éléments à choisir"""
        i = [item.strip() for item in items.split(',')]
        if weights:
            w = [int(weight.strip()) for weight in weights.split(',')]
        else:
            w = None
        
        if elements > len(i):
            await interaction.response.send_message(f"**Erreur ·** Vous ne pouvez pas choisir plus d'éléments que la liste ne contient ({len(i)})")
            return
        
        choices = random.choices(i, weights=w, k=elements)
        if elements > 1:
            choices = ', '.join(choices)
        else:
            choices = choices[0]
        
        await interaction.response.send_message(f"🎲 **Choix aléatoire ·** `{choices}`")

    
async def setup(bot: commands.Bot):
    cog = Toolkit(bot)
    await bot.add_cog(cog)