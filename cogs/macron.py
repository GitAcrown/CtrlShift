import logging
from pathlib import Path

import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from common.dataio import get_package_path

logger = logging.getLogger('ctrlshift.Macron')

        
class Macron(commands.Cog):
    """Répond par oui, non, ou peut-être en vidéo..."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _load_videos(self):
        """Charge les vidéos de Macron"""
        path : str = get_package_path('macron')
        self.videos = {}
        for file in Path(path).glob('*.mp4'):
            self.videos[file.stem] = file
    
    @app_commands.command(name='macron')
    async def macron(self, interaction: discord.Interaction, question: str):
        """Répond par oui, non, ou peut-être en vidéo...
        
        :param question: Question à poser"""
        if not hasattr(self, 'videos'):
            self._load_videos()
        video = random.choice(list(self.videos.values()))
        await interaction.response.send_message(f"**{question}**", file=discord.File(video))
    
async def setup(bot: commands.Bot):
    cog = Macron(bot)
    await bot.add_cog(cog)