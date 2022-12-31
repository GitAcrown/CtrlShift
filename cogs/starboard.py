# pyright: reportGeneralTypeIssues=false

import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from copy import copy
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from tabulate import tabulate

from common.dataio import get_sqlite_database
from common.utils import fuzzy, pretty

logger = logging.getLogger('nero.Starboard')

DEFAULT_SETTINGS = [
    ('PostChannelID', 0),
    ('PostTarget', 5),
    ('AdaptiveTargetRange', 2),
    ('DetectPotentialPost', True)
]


class StarboardError(Exception):
    """Erreurs spécifiques à Starboard"""
    

class Starboard(commands.GroupCog, group_name="star", description="Gestion et maintenance d'un salon de messages favoris"):
    """Gestion et maintenance d'un salon de messages favoris"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task_message_expire.start()

    def cog_unload(self):
        self.task_message_expire.cancel()
        
    @tasks.loop(hours=12)
    async def task_message_expire(self):
        expiration = datetime.utcnow().timestamp() - 86400
        for guild in self.bot.guilds:
            conn = get_sqlite_database('starboard', 'g' + str(guild.id))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE created_at < ?", (expiration,))
            conn.commit()
            cursor.close()
            conn.close()
        logger.info("Suppression des messages expirés Starboard effectuée")
        
    @commands.Cog.listener()
    async def on_ready(self):
        self._initialize_database()
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._initialize_database(guild)
        
    def _initialize_database(self, guild: discord.Guild = None):
        initguilds = [guild] if guild else self.bot.guilds
        for g in initguilds:
            conn = get_sqlite_database('starboard', 'g' + str(g.id))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS messages (message_id BIGINT PRIMARY KEY, votes TEXT, embed_message BIGINT, created_at REAL)")
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (name TINYTEXT PRIMARY KEY, value TEXT)")
            for name, default_value in DEFAULT_SETTINGS:
                cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
            conn.commit()
            cursor.close()
            conn.close()
            
            
    def get_guild_settings(self, guild: discord.Guild) -> dict:
        """Obtenir les paramètres Starboard du serveur

        :param guild: Serveur des paramètres à récupérer
        :return: dict
        """
        conn = get_sqlite_database('starboard', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        settings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        from_json = {s[0] : json.loads(s[1]) for s in settings}
        return from_json
    
    def set_guild_settings(self, guild: discord.Guild, update: dict):
        """Met à jours les paramètres Starboard du serveur

        :param guild: Serveur à mettre à jour
        :param update: Paramètres à mettre à jour (toutes les valeurs seront automatiquement sérialisés en JSON)
        """
        conn = get_sqlite_database('starboard', 'g' + str(guild.id))
        cursor = conn.cursor()
        for upd in update:
            cursor.execute("UPDATE settings SET value=? WHERE name=?", (json.dumps(update[upd]), upd))
        conn.commit()
        cursor.close()
        conn.close()
        
        
    def get_message_metadata(self, guild: discord.Guild, message: discord.Message) -> dict:
        conn = get_sqlite_database('starboard', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM messages WHERE message_id=?", (message.id,))
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        if data:
            return dict(message_id=data[0], votes=json.loads(data[1]), embed_message=data[2], created_at=data[3])
        return None
    
    def delete_message_metadata(self, guild: discord.Guild, message: discord.Message) -> dict:
        conn = get_sqlite_database('starboard', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE message_id=?", (message.id,))
        conn.commit()
        cursor.close()
        conn.close()
        
    
    async def get_embed(self, message: discord.Message) -> discord.Embed:
        guild = message.guild
        metadata = self.get_message_metadata(guild, message)
        if not metadata:
            raise KeyError(f"Le message '{message.id}' n'a pas de données liées")
        
        reply_text = ''
        reply_thumb = None
        if message.reference:
            try:
                reference_msg : discord.Message = await message.channel.fetch_message(message.reference.message_id)
                reply_text = f"> **{reference_msg.author.name}** · <t:{int(reference_msg.created_at.timestamp())}>\n> {reference_msg.clean_content if reference_msg.clean_content else 'Contenu multimédia'}\n\n"
                _reply_img = [a for a in reference_msg.attachments if a.content_type in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']]
                if _reply_img:
                    reply_thumb = reply_img[0]
            except Exception as e:
                logger.info(e, exc_info=True)
        
        message_content = message.clean_content
        # message_content += f"\n[→ Aller au message]({message.jump_url})"
        
        content = reply_text + message_content
        votes = len(metadata['votes'])
        footxt = f"⭐ {votes}"
        
        em = discord.Embed(description=content, timestamp=message.created_at, color=0x2F3136)
        em.set_author(name=message.author.name, icon_url=message.author.display_avatar.url)
        em.set_footer(text=footxt)
        
        image_preview = None
        media_links = []
        for a in message.attachments:
            if a.content_type in ['image/jpeg', 'image/png', 'image/gif', 'image/webp'] and not image_preview:
                image_preview = a.url
            else:
                media_links.append(a.url)
        for msge in message.embeds:
            if msge.image and not image_preview:
                image_preview = msge.image.url
            elif msge.thumbnail and not image_preview:
                image_preview = msge.thumbnail.url
        
        if image_preview:
            em.set_image(url=image_preview)
        if reply_thumb:
            em.set_thumbnail(url=reply_thumb)
        if media_links:
            linkstxt = [f"[[{l.split('/')[-1]}]]({l})" for l in media_links]
            em.add_field(name="Média(s)", value='\n'.join(linkstxt))
            
        return em
            
    async def post_starboard_message(self, message: discord.Message):
        guild = message.guild
        settings = self.get_guild_settings(guild)
        post_channel = self.bot.get_channel(int(settings['PostChannelID'])) if settings['PostChannelID'] else None
        if not post_channel:
            raise ValueError("Channel Starboard non configuré")

        try:
            embed = await self.get_embed(message)
        except KeyError as e:
            logger.error(e, exc_info=True)
            raise
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Aller au message", url=message.jump_url))
        
        try:
            embed_msg = await post_channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(e, exc_info=True)
            return
        
        conn = get_sqlite_database('starboard', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET embed_message=? WHERE message_id=?", (embed_msg.id, message.id))
        conn.commit()
        cursor.close()
        conn.close()
    
    async def edit_starboard_message(self, original_message: discord.Message):
        guild = original_message.guild
        settings = self.get_guild_settings(guild)
        post_channel = self.bot.get_channel(int(settings['PostChannelID'])) if settings['PostChannelID'] else None
        if not post_channel:
            raise ValueError("Channel Starboard non configuré")
    
        metadata = self.get_message_metadata(guild, original_message)
        try:
            embed_msg = await post_channel.fetch_message(metadata['embed_message'])
        except:
            logger.info(f"Impossible d'accéder à {metadata['embed_message']} : données supprimées")
            self.delete_message_metadata(guild, original_message)
            
        embed = await self.get_embed(original_message)
        await embed_msg.edit(embed=embed)
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        emoji = payload.emoji
        if hasattr(channel, 'guild'):
            guild = channel.guild
            if emoji.name == '⭐':
                settings = self.get_guild_settings(guild)
                if settings['PostChannelID']:
                    message = await channel.fetch_message(payload.message_id)
                    if message.created_at.timestamp() + 86400 >= datetime.utcnow().timestamp():
                        user = guild.get_member(payload.user_id)
                        post_channel = guild.get_channel(int(settings['PostChannelID']))
                        metadata = self.get_message_metadata(guild, message)
                        if not metadata:
                            created_at = datetime.utcnow().timestamp()
                            metadata = {'message_id': message.id, 'votes': [], 'embed_message': 0, 'created_at': created_at}
                            conn = get_sqlite_database('starboard', 'g' + str(guild.id))
                            cursor = conn.cursor()
                            cursor.execute("INSERT OR IGNORE INTO messages (message_id, votes, embed_message, created_at) VALUES (?, ?, ?, ?)", (message.id, '[]', 0, created_at))
                            conn.commit()
                            cursor.close()
                            conn.close()
                        
                        if user.id not in metadata['votes']:
                            metadata['votes'].append(user.id)
                            conn = get_sqlite_database('starboard', 'g' + str(guild.id))
                            cursor = conn.cursor()
                            cursor.execute("UPDATE messages SET votes=? WHERE message_id=?", (json.dumps(metadata['votes']), message.id))
                            conn.commit()
                            cursor.close()
                            conn.close()
                            
                            if len(metadata['votes']) >= int(settings['PostTarget']):
                                if not metadata['embed_message']:
                                    await self.post_starboard_message(message)
                                    try:
                                        notif = await message.reply(f"Ce message a été enregistré sur {post_channel.mention} !", mention_author=False)
                                        await notif.delete(delay=120)
                                    except:
                                        raise
                                else:
                                    await self.edit_starboard_message(message)
                        
        
    @app_commands.command(name="set")
    @app_commands.guild_only
    @app_commands.checks.has_permissions(manage_messages=True)
    async def set_starboard_settings(self, interaction: discord.Interaction, setting: str, value: str):
        """Modifier les paramètres de Starboard (salon des messages favoris)

        :param setting: Nom du paramètre à modifier
        :param value: Valeur à attribuer au paramètre (sera sérialisé en JSON)
        """
        if setting not in [s[0] for s in DEFAULT_SETTINGS]:
            return await interaction.response.send_message(f"**Erreur ·** Le paramètre `{setting}` n'existe pas", ephemeral=True)
        try:
            self.set_guild_settings(interaction.guild, {setting: value})
        except Exception as e:
            logger.error(f"Erreur dans set_bank_settings : {e}", exc_info=True)
            return await interaction.response.send_message(f"**Erreur ·** Il y a eu une erreur lors du réglage du paramètre, remontez cette erreur au propriétaire du bot", ephemeral=True)
        await interaction.response.send_message(f"**Succès ·** Le paramètre `{setting}` a été réglé sur `{value}`", ephemeral=True)
        
    @set_starboard_settings.autocomplete('setting')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        starsettings = tuple(self.get_guild_settings(interaction.guild).items())
        stgs = fuzzy.finder(current, starsettings, key=lambda bs: bs[0])
        return [app_commands.Choice(name=f'{s[0]} ({s[1]})', value=s[0]) for s in stgs]
    
async def setup(bot):
    await bot.add_cog(Starboard(bot))
