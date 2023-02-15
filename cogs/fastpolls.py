import logging
import time
from copy import copy
from datetime import datetime
from typing import Any, List

import discord
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate

from common.utils import pretty

logger = logging.getLogger('nero.FastPolls')

class PollSelect(discord.ui.Select):
    def __init__(self, cog: 'FastPolls', poll_session: dict):
        super().__init__(
            placeholder='Sélectionnez une option',
            min_values=1,
            max_values=1,
            row=0
        )
        self._cog = cog
        self.session = poll_session
        self.__fill_options(poll_session['choices'])

    def __fill_options(self, choices: List[str]) -> None:
        for choice in choices:
            self.add_option(label=choice.capitalize(), value=choice)
    
    async def callback(self, interaction: discord.Interaction) -> Any:
        edited = False
        for v in self.session['votes']:
            if interaction.user.id in self.session['votes'][v]:
                self.session['votes'][v].remove(interaction.user.id)
                edited = True
        self.session['votes'][self.values[0]].append(interaction.user.id)
        self.session['vote_message'] = await self.session['vote_message'].edit(embed=self._cog.get_embed(self.session))
        if edited:
            return await interaction.response.send_message(f"**`{self.session['title']}` ·** __Vote modifié__, merci d'avoir participé !", ephemeral=True)
        return await interaction.response.send_message(f"**`{self.session['title']}` ·** __Vote pris en compte__, merci d'avoir participé !", ephemeral=True)

        
class FastPolls(commands.Cog):
    """Outils de sondage"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions = {}
        
    def get_embed(self, data: dict, ending: bool = False):
        title = f"***{data['title']}***"
        chunks = []  
        total_votes = sum([len(data['votes'][v]) for v in data['votes']])
        for choice, votes in data['votes'].items():
            chunks.append((choice.capitalize(), pretty.bar_chart(len(votes), total_votes, 5 if total_votes < 10 else 10), len(votes)))
        timestamp = datetime.utcnow().fromtimestamp(time.time() + data['timeout']) if ending is False else datetime.utcnow().fromtimestamp(time.time())
        embed = discord.Embed(title=title, description=f"```css\n{tabulate(chunks, tablefmt='plain')}```", color=0x2F3136, timestamp=timestamp)
        embed.set_footer(text="Sondage créé par " + data['author'].display_name, icon_url=data['author'].display_avatar.url)
        return embed
    
    @app_commands.command(name="poll")
    @app_commands.guild_only()
    async def create_poll(self, interaction: discord.Interaction, title: str, choices: str, timeout: app_commands.Range[int, 60, 600] = 90):
        """Créer un sondage rapide

        :param title: Titre du sondage
        :param choices: Choix séparés par des virgules (X,Y,Z...)
        :param timeout: Temps en secondes d'expiration après la dernière réponse reçue, par défaut 90s
        """
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.id in self.sessions:
            return await interaction.response.send_message("**Sondage déjà en cours** · Attendez que le sondage en cours sur ce salon se termine avant d'en lancer un nouveau !", ephemeral=True)
        if len(choices.split(',')) < 2:
            return await interaction.response.send_message("**Sondage invalide** · Vous devez fournir au moins deux choix séparés par des virgules !", ephemeral=True)
        self.sessions[channel.id] = {
            'title': title,
            'choices': [choice.strip() for choice in choices.split(',')],
            'votes': {choice.strip(): [] for choice in choices.split(',')},
            'author': interaction.user,
            'vote_message': None,
            'timeout': timeout
        }
        embed = self.get_embed(self.sessions[channel.id])
        view = discord.ui.View()
        view.add_item(PollSelect(self, self.sessions[channel.id]))
        view.timeout = timeout
        msg : discord.Message = await channel.send(embed=embed, view=view)
        self.sessions[channel.id]['vote_message'] = msg
        await interaction.response.send_message("**Nouveau sondage créé avec succès** · Vous pouvez voter en cliquant sur le menu déroulant ci-dessous !", ephemeral=True)
        await view.wait()
        await msg.edit(view=None)
        final_embed = self.get_embed(self.sessions[channel.id], ending=True)
        await channel.send(embed=final_embed, content="**Sondage terminé** · Merci d'avoir participé !")
        del self.sessions[channel.id]
        
    
async def setup(bot):
    await bot.add_cog(FastPolls(bot))
