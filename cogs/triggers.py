import io
import json
import logging
import re
from typing import Any, List, Tuple

import discord
import requests
from discord import app_commands
from discord.ext import commands

from common.dataio import get_sqlite_database
from common.utils import fuzzy

logger = logging.getLogger('nero.Triggers')

DEFAULT_SETTINGS : List[Tuple[str, Any]] = [
    ('fxTwitter', 1),
    ('TikTokPreview', 1)
]

class Triggers(commands.GroupCog, group_name="trig", description="Collection de triggers utiles"):
    """Collection de triggers utiles"""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.session = requests.Session()
        
    def cog_unload(self) -> None:
        self.session.close()
        
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
        attachments = []
        raw_links = []
        for c in chunks:
            try:
                r = self.session.get(c)
            except Exception as e:
                logger.warning(f"Error while fetching {c}: {e}", exc_info=True)
                return await message.reply(f"**Une erreur est survenue lors de la récupération de `{c}`**\nLe site Tiktok.sauce est peut-être hors-ligne.", mention_author=False)
            if r.headers['Content-Type'] != 'video/mp4':
                raw_links.append(c)
                continue
            link_id = c.split('/')[-1]
            attachments.append(discord.File(io.BytesIO(r.content), filename=f'{link_id}.mp4'))
        if attachments:
            if raw_links:
                return await message.reply('\n'.join(raw_links), mention_author=False, files=attachments)
            return await message.reply(files=attachments, mention_author=False)
        elif raw_links:
            return await message.reply('\n'.join(raw_links), mention_author=False)
        
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