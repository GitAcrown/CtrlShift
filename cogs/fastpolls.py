import logging
import time
from copy import copy
from datetime import datetime
from typing import Any, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate

from common.utils import pretty

logger = logging.getLogger('nero.FastPolls')

class PollSelect(discord.ui.Select):
    def __init__(self, cog: 'FastPolls', poll_session: dict, minimum: int = 1, maximum: int = 1):
        pholder = "Sélectionnez une option"
        if maximum > 1:
            pholder = f"Sélectionnez de {minimum} à {maximum} options"
        if minimum == maximum:
            pholder = f"Sélectionnez {minimum} option{'s' if maximum > 1 else ''}"
            
        super().__init__(
            placeholder=pholder,
            min_values=minimum,
            max_values=maximum,
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
                
        for v in self.values:
            if interaction.user.id not in self.session['votes'][v]:
                self.session['votes'][v].append(interaction.user.id)
        
        self.session['vote_message'] = await self.session['vote_message'].edit(embed=self._cog.get_embed(self.session))
        if edited:
            return await interaction.response.send_message(f"**`{self.session['title']}` ·** __Vote modifié__, merci d'avoir participé !", ephemeral=True, delete_after=10)
        return await interaction.response.send_message(f"**`{self.session['title']}` ·** __Vote pris en compte__, merci d'avoir participé !", ephemeral=True, delete_after=10)

        
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
            chunks.append((choice.capitalize(), len(votes), pretty.bar_chart(len(votes), total_votes, 5 if total_votes < 10 else 10)))
        chunks.append(('Total', total_votes, f"{'(Choix multiples autorisés)' if data['maximum'] > 1 else ''}"))
        
        timestamp = datetime.utcnow().fromtimestamp(time.time() + data['timeout']) if ending is False else datetime.utcnow().fromtimestamp(time.time())
        embed = discord.Embed(title=title, description=f"```css\n{tabulate(chunks, tablefmt='plain')}```", color=0x2F3136, timestamp=timestamp)
        embed.set_footer(text="Sondage créé par " + data['author'].display_name, icon_url=data['author'].display_avatar.url)
        return embed
    
    @app_commands.command(name="poll")
    @app_commands.guild_only()
    async def create_poll(self, interaction: discord.Interaction, title: str, choices: str, minimum: app_commands.Range[int, 1] = 1, maximum: app_commands.Range[int, 1] = 1, timeout: app_commands.Range[int, 60, 600] = 90):
        """Créer un sondage rapide

        :param title: Titre du sondage
        :param choices: Choix possibles, séparés par des virgules
        :param minimum: Nombre minimum de choix, par défaut 1
        :param maximum: Nombre maximum de choix, par défaut 1
        :param timeout: Temps d'expiration du sondage en secondes à partir de la dernière réponse, par défaut 90s
        """
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.id in self.sessions:
            return await interaction.response.send_message("**Sondage déjà en cours** · Attendez que le sondage en cours sur ce salon se termine avant d'en lancer un nouveau !", ephemeral=True)
        if len(choices.split(',')) < 2:
            return await interaction.response.send_message("**Sondage invalide** · Vous devez fournir au moins deux choix séparés par des virgules !", ephemeral=True)
        if minimum > maximum:
            maximum = minimum
            await interaction.response.send_message(f"**Sondage corrigé automatiquement** · Le nombre maximum de choix a été réglé sur {minimum}", ephemeral=True, delete_after=10)
            
        self.sessions[channel.id] = {
            'title': title,
            'choices': [choice.strip() for choice in choices.split(',')],
            'votes': {choice.strip(): [] for choice in choices.split(',')},
            'author': interaction.user,
            'vote_message': None,
            'timeout': timeout,
            'minimum': minimum,
            'maximum': maximum
        }
        embed = self.get_embed(self.sessions[channel.id])
        view = discord.ui.View()
        view.add_item(PollSelect(self, self.sessions[channel.id], minimum=minimum, maximum=maximum))
        view.timeout = timeout
        msg : discord.Message = await channel.send(embed=embed, view=view)
        self.sessions[channel.id]['vote_message'] = msg
        await interaction.response.send_message("**Nouveau sondage créé avec succès** · Vous pouvez voter en cliquant sur le menu déroulant ci-dessous !", ephemeral=True, delete_after=20)
        await view.wait()
        await msg.edit(view=None)
        final_embed = self.get_embed(self.sessions[channel.id], ending=True)
        await channel.send(embed=final_embed, content="**Sondage terminé** · Merci d'avoir participé !")
        del self.sessions[channel.id]
        
    
async def setup(bot):
    await bot.add_cog(FastPolls(bot))
