import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from copy import copy
from typing import Any, Optional, Callable, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks
from tabulate import tabulate

from common.dataio import get_sqlite_database
from common.utils import fuzzy, pretty

logger = logging.getLogger('nero.Insights')

DEFAULT_SETTINGS : List[Tuple[str, Any]] = [
    ('', ''),
]


class InsightsError(Exception):
    """Erreurs spécifiques à Insights"""
    
    
class UserProfile():
    def __init__(self, cog: 'Insights', user: discord.User) -> None:
        self._cog = cog
        self.user = user
        

class Insights(commands.GroupCog, group_name="in", description="Système central de gestion des données utilisateurs"):
    """Système central de gestion des données utilisateurs"""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        self._initialize_database()
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._initialize_database(guild)
        
    def _initialize_database(self, guild: discord.Guild = None):
        if not guild:
            conn = get_sqlite_database('insights')
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS userdata (user_id INTEGER PRIMARY KEY, )")
            conn.commit()
            cursor.close()
            conn.close()
        
        initguilds = [guild] if guild else self.bot.guilds
        for g in initguilds:
            conn = get_sqlite_database('insights', f'{g.id}')
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS memberdata (member_id INTEGER PRIMARY KEY, )")
            for name, default_value in DEFAULT_SETTINGS:
                cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
            conn.commit()
            cursor.close()
            conn.close()
        
async def setup(bot):
    await bot.add_cog(Insights(bot))