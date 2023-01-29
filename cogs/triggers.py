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

logger = logging.getLogger('nero.Triggers')

DEFAULT_SETTINGS : List[Tuple[str, Any]] = [
    ('fxTwitter', 1),
    ('TikTokPreview', 1)
]

class Triggers(commands.GroupCog, group_name="trig", description="Collection de triggers utiles"):
    """Collection de triggers utiles"""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        self._initialize_database()
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._initialize_database(guild)
        
    def _initialize_database(self, guild: discord.Guild = None):
        initguilds = [guild] if guild else self.bot.guilds
        for g in initguilds:
            conn = get_sqlite_database('triggers', f'g{g.id}')
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT)")
            for name, default_value in DEFAULT_SETTINGS:
                cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
            conn.commit()
            cursor.close()
            conn.close()
            
    def get_guild_settings(self, guild: discord.Guild) -> dict:
        """Obtenir les paramètres Triggers du serveur

        :param guild: Serveur des paramètres à récupérer
        :return: dict
        """
        conn = get_sqlite_database('triggers', f'g{guild.id}')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        settings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        from_json = {s[0] : json.loads(s[1]) for s in settings}
        return from_json
    
    def set_guild_settings(self, guild: discord.Guild, update: dict):
        """Met à jours les paramètres Triggers du serveur

        :param guild: Serveur à mettre à jour
        :param update: Paramètres à mettre à jour (toutes les valeurs seront automatiquement sérialisés en JSON)
        """
        conn = get_sqlite_database('triggers', f'g{guild.id}')
        cursor = conn.cursor()
        for upd in update:
            cursor.execute("UPDATE settings SET value=? WHERE name=?", (json.dumps(update[upd]), upd))
        conn.commit()
        cursor.close()
        conn.close()
        
    # FONCTIONS
        
    async def post_fxtwitter(self, message: discord.Message):
        settings = self.get_guild_settings(message.guild)
        if not int(settings['fxTwitter']):
            return
        result = re.findall(r"(?:https?:\/\/)?(?:www\.)?twitter\.com\/([\w\d\/]*)", message.content)
        chunks = []
        for r in result:
            chunks.append(f"https://fxtwitter.com/{r}")
        if len(result) == 0:
            return
        await message.edit(suppress=True)
        await message.reply('\n'.join(chunks), mention_author=False)
        
    async def preview_tiktok(self, message: discord.Message):
        settings = self.get_guild_settings(message.guild)
        if not int(settings['TikTokPreview']):
            return
        result = re.findall(r"https:\/\/(?:vm|www)?\.tiktok\.com\/[0-z\/]*", message.content)
        chunks = []
        for r in result:
            chunks.append(f"https://tiktok.sauce.sh/?url={r}")
        if len(chunks) == 0:
            return
        await message.edit(suppress=True)
        await message.reply('\n'.join(chunks), mention_author=False)
        
    # COMMANDES
    
    @app_commands.command(name="set")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def edit_settings(self, interaction: discord.Interaction, name: str, value: str):
        """Modifier les paramètres du module Triggers

        :param name: Nom du paramètre à modifier
        :param value: Valeur à attribuer au paramètre
        """
        if name not in [s[0] for s in DEFAULT_SETTINGS]:
            return await interaction.response.send_message("**Erreur ·** Le paramètre `{name}` n'existe pas", ephemeral=True)
        try:
            self.set_guild_settings(interaction.guild, {name : value})
        except Exception as e:
            logger.error(f"Erreur dans edit_settings : {e}", exc_info=True)
            return await interaction.response.send_message(f"**Erreur ·** Il y a eu une erreur lors du réglage du paramètre, remontez cette erreur au propriétaire du bot", ephemeral=True)
        await interaction.response.send_message(f"**Succès ·** Le paramètre `{name}` a été réglé sur `{value}`", ephemeral=True)
    
    @edit_settings.autocomplete('name')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        trig_settings = tuple(self.get_guild_settings(interaction.guild).items())
        tstgs = fuzzy.finder(current, trig_settings, key=lambda bs: bs[0])
        return [app_commands.Choice(name=f'{s[0]} ({s[1]})', value=s[0]) for s in tstgs]
    
    
    # TRIGGERS
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild:
            if not message.author.bot:
                await self.post_fxtwitter(message)
                await self.preview_tiktok(message)
        
async def setup(bot):
    await bot.add_cog(Triggers(bot))