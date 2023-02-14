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
            placeholder='Sélectionnez votre choix',
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
        if interaction.user.id in self.session['voters']:
            return await interaction.response.send_message(f"**Sondage `{self.session['title']}` ·** Vous avez déjà voté !", ephemeral=True)
        self.session['voters'].append(interaction.user.id)
        self.session['votes'][self.values[0]] += 1
        self.session['vote_message'] = await self.session['vote_message'].edit(embed=self._cog.get_embed(self.session))
        return await interaction.response.send_message(f"**Sondage `{self.session['title']}` ·** Vote pris en compte, merci d'avoir participé !", ephemeral=True)

        
class FastPolls(commands.Cog):
    """Outils de sondage"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions = {}
        
    def get_embed(self, data: dict):
        title = f"***{data['title']}***"
        chunks = []
        total_votes = sum(data['votes'].values())
        for choice, votes in data['votes'].items():
            chunks.append((choice.capitalize(), pretty.bar_chart(votes, total_votes, 5 if total_votes < 10 else 10) + f" [{votes}]"))
        embed = discord.Embed(title=title, description=f"```css\n{tabulate(chunks, tablefmt='plain')}```", color=0x2F3136, timestamp=datetime.utcnow().fromtimestamp(time.time() + data['timeout']))
        embed.set_footer(text="Sondage créé par " + data['author'].display_name, icon_url=data['author'].display_avatar.url)
        return embed
    
    @app_commands.command(name="poll")
    @app_commands.guild_only()
    async def create_poll(self, interaction: discord.Interaction, title: str, choices: str, timeout: app_commands.Range[int, 30, 600] = 60):
        """Créer un sondage rapide

        :param title: Titre du sondage
        :param choices: Choix séparés par des virgules (X,Y,Z...)
        :param timeout: Temps après la dernière réponse avant la fin du sondage (en secondes), par défaut 60s
        """
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.id in self.sessions:
            return await interaction.response.send_message("**Sondage déjà en cours** · Attendez que le sondage en cours sur ce salon se termine avant d'en lancer un nouveau !", ephemeral=True)
        self.sessions[channel.id] = {
            'title': title,
            'voters': [],
            'choices': [choice.strip() for choice in choices.split(',')],
            'votes': {choice.strip(): 0 for choice in choices.split(',')},
            'author': interaction.user,
            'vote_message': None,
            'timeout': timeout
        }
        embed = self.get_embed(self.sessions[channel.id])
        view = discord.ui.View()
        view.add_item(PollSelect(self, self.sessions[channel.id]))
        view.timeout = timeout
        print(view.timeout)
        msg : discord.Message = await channel.send(embed=embed, view=view)
        self.sessions[channel.id]['vote_message'] = msg
        await interaction.response.send_message("**Nouveau sondage créé** · Vous pouvez voter en cliquant sur le menu déroulant ci-dessus !", ephemeral=True)
        await view.wait()
        await msg.edit(view=None)
        final_embed = self.get_embed(self.sessions[channel.id])
        await channel.send(embed=final_embed, content="**Sondage terminé** · Merci d'avoir participé !")
        del self.sessions[channel.id]
        
    
async def setup(bot):
    await bot.add_cog(FastPolls(bot))
