import logging
import time
import iso3166
from copy import copy
from datetime import datetime, timezone
from typing import Any, List, Optional

import discord
import requests
import json
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate

from common.utils import pretty, fuzzy
from common.dataio import get_sqlite_database

logger = logging.getLogger('ctrlshift.Colors')

        
class Colors(commands.GroupCog, group_name='color', description='Gestion des rôles de couleur'):
    """Gestion des rôles de couleur"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    def normalize_color(self, color: str) -> str:
        """Renvoie la couleur hexadécimale normalisée au format RRGGBB"""
        if color.startswith('#'):
            color = color[1:]
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        return color
        
    def is_recyclable(self, role: discord.Role, request_user: Optional[discord.Member] = None) -> bool:
        """Renvoie True si le rôle n'est possédé par personne ou par le membre faisant la demande, sinon False"""
        if not role.members:
            return True
        elif request_user and role.members == [request_user]:
            return True
        return False

    def get_color_role(self, guild: discord.Guild, hex_color: str) -> Optional[discord.Role]:
        """Renvoie le rôle de couleur correspondant à la couleur hexadécimale donnée"""
        name = f"#{self.normalize_color(hex_color)}"
        return discord.utils.get(guild.roles, name=name)

    def get_color_roles(self, guild: discord.Guild) -> List[discord.Role]:
        """Renvoie la liste des rôles de couleur du serveur"""
        return [role for role in guild.roles if role.name.startswith('#') and len(role.name) == 7]
    
    async def get_color_info(self, color: str) -> Optional[dict]:
        """Renvoie les informations de la couleur donnée"""
        color = self.normalize_color(color)
        url = f"https://www.thecolorapi.com/id?hex={color}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    
    async def get_color_scheme(self, color: str) -> Optional[dict]:
        """Renvoie la palette de couleurs correspondant à la couleur donnée"""
        color = self.normalize_color(color)
        url = f"https://www.thecolorapi.com/scheme?hex={color}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    
    
        
async def setup(bot):
    await bot.add_cog(Colors(bot))