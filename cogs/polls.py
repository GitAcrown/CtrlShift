import discord
import logging
import time
import re
from discord import app_commands
from discord.ext import commands
from typing import Optional, Any
from common.dataio import get_sqlite_database
from common.utils import fuzzy, pretty

logger = logging.getLogger('nero.Polls')

class NewPoll(discord.ui.Modal, title="Créer un sondage"):
    sesstitle = discord.ui.TextInput(label="Titre", placeholder="Nom de cette session de vote", 
                                 style=discord.TextStyle.short, max_length=100)
    choices = discord.ui.TextInput(label="Choix", placeholder="Indiquez un choix par ligne, ou séparez les réponses avec ';'", 
                                style=discord.TextStyle.paragraph, max_length=200)
    poll_timeout = discord.ui.TextInput(label="Expiration auto. (WIP)", placeholder="Temps en min. avant expiration auto. (par défaut aucune)", 
                                style=discord.TextStyle.short, max_length=3, default='0', required=False)
    
    def __init__(self, cog: "Polls") -> None:
        super().__init__()
        self.cog : Polls = cog
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.cog.create_poll_session(interaction.user, str(self.sesstitle), self.choices.value, int(self.poll_timeout.value))
        await interaction.response.send_message(f"Nouvelle session de vote **{self.sesstitle}** créée avec succès.", ephemeral=True)
        await interaction.channel.send(f"Une session de vote **{self.sesstitle}** [{' '.join([f'`{i}`' for i in self.cog.parse_choices(self.choices.value)])}] a été créée par {interaction.user} !\nParticipez-y avec `/poll vote`", delete_after=60)
        
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message(f"Oups ! Il y a eu une erreur lors de la création de la session.", ephemeral=True)
        logger.error(error)
        
class VoteSelectMenu(discord.ui.Select):
    def __init__(self, original_interaction: discord.Interaction, cog: "Polls", session_id: str, choices: list):
        super().__init__(
            placeholder='Sélectionnez votre choix...',
            min_values=1,
            max_values=1,
            row=0
        )
        self.original_interaction : discord.Interaction = original_interaction
        self.cog : Polls = cog
        self.session_id : str = session_id
        self.__fill_options(choices)

    def __fill_options(self, choices: list) -> None:
        for choice in choices:
            self.add_option(label=choice, value=choice)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        self.cog.set_member_vote(interaction.user, self.session_id, value)
        await self.original_interaction.edit_original_response(content=f"**Merci d'avoir voté !**\nVotre réponse (*{value}*) a bien été prise en compte !", view=None)
        session = self.cog.polls_cache[interaction.guild.id][self.session_id]
        await interaction.channel.send(f"**{interaction.user}** a participé au sondage ***{session['title']}***\nParticipez-y aussi avec `/poll vote` !", delete_after=30.0)

class Confirmbutton(discord.ui.View):
    def __init__(self, initial_interaction: discord.Interaction):
        super().__init__()
        self.initial_interaction = initial_interaction
        self.value : bool = None

    @discord.ui.button(label='Confirmer', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()

    @discord.ui.button(label='Annuler', style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        
    async def interaction_check(self, interaction: discord.Interaction):
        is_author = interaction.user.id == self.initial_interaction.user.id
        if not is_author:
            await interaction.response.send_message(
                "Vous n'êtes pas l'auteur de la commande.",
                ephemeral=True,
            )
        return is_author

class Polls(commands.GroupCog, group_name="poll", description="Gestion des anniversaires"):
    """Outils de sondage"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        self.polls_cache = self.update_storage()
        
    def update_storage(self):
        cache = {}
        for guild in self.bot.guilds:
            # Création des tables SQLite
            conn = get_sqlite_database('polls', 'g' + str(guild.id))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS polls (session_id TEXT PRIMARY KEY, title TEXT, choices TEXT, start_time REAL, timeout INTEGER, author_id INT)")
            cursor.execute("CREATE TABLE IF NOT EXISTS votes (vote_id TEXT PRIMARY KEY, session_id INTEGER, user_id INTEGER, choice TEXT, FOREIGN KEY (session_id) REFERENCES polls(session_id))")
            conn.commit()
            
            # Mettre les polls en cache
            cursor.execute("SELECT * FROM polls")
            polls = cursor.fetchall()
            cache[guild.id] = {p[0]: {'title': p[1], 'choices': p[2], 'start_time': p[3], 'timeout': p[4], 'author_id': p[5]} for p in polls}
            
            cursor.close()
            conn.close()
        return cache
        
    # POLLS ----------------------------------------------
        
    def parse_choices(self, choices: str) -> list:
        choices = re.split(r'[;|\n]', choices)
        choices = [c.strip() for c in choices if c]
        return choices
        
    def create_poll_session(self, author: discord.Member, title: str, choices: str, timeout: int = 0):
        guild = author.guild
        start_time = time.time()
        sessionid = hex(int(start_time))[2:]
        choices = '|'.join(self.parse_choices(choices))
        
        conn = get_sqlite_database('polls', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO polls (session_id, title, choices, start_time, timeout, author_id) VALUES (?, ?, ?, ?, ?, ?)", (sessionid, title, choices, start_time, timeout, author.id))
        conn.commit()
        cursor.close()
        conn.close()
        
        self.polls_cache = self.update_storage()
    
    def get_poll_sessions(self, guild: discord.Guild):
        conn = get_sqlite_database('polls', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM polls")
        sessions = cursor.fetchall()
        cursor.close()
        conn.close()
        
        sessionsdict = {s[0]: {'title': s[1], 'choices': self.parse_choices(s[2]), 'start_time': s[3], 'timeout': s[4], 'author_id':s[5]} for s in sessions}
        return sessionsdict
    
    def delete_poll_session(self, guild: discord.Guild, session_id: str):
        conn = get_sqlite_database('polls', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM polls WHERE session_id=?", (session_id,))
        cursor.execute("DELETE FROM votes WHERE session_id=?", (session_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        self.polls_cache = self.update_storage()
        
    def embed_poll_results(self, guild: discord.Guild, session_id: str):
        poll = self.polls_cache[guild.id][session_id]
        votes = self.get_all_votes_from_session(guild, session_id)
        
        chunks = []
        for c in self.parse_choices(poll['choices']):
            nb = len([m for m in votes if m[1] == c])
            chunks.append(f"**`{c}` ·** {pretty.bar_chart(nb, len(votes), 2)} {nb}")
        em = discord.Embed(title=f"***{poll['title']}***", description='\n'.join(chunks), color=0x2F3136)
        em.set_footer(text=f"Total votants : {len(votes)}")
        return em
        
    @app_commands.command(name="create")
    async def create_session(self, interaction: discord.Interaction):
        """Créer une nouvelle session de vote"""
        try:
            await interaction.response.send_modal(NewPoll(self))
        except Exception as e:
            logger.warning("Erreur dans 'pollset_group > new_session'", exc_info=True)
            return await interaction.response.send_message(f"**Erreur ·** `{e}`", ephemeral=True)
        
    @app_commands.command(name="stop")
    async def stop_session(self, interaction: discord.Interaction, session: Optional[str] = None):
        """Arrêter une session de vote et afficher les résultats

        :param session: Optionnel, session à arrêter
        """
        sessions = self.get_poll_sessions(interaction.guild)
        if not sessions:
            return await interaction.response.send_message("**Erreur ·** Aucune session de vote n'est actuellement ouverte", ephemeral=True)
        
        if not session:
            msg = ""
            chunks = []
            for s in sessions:
                chunks.append(f"***{sessions[s]['title']}*** : " + ' '.join([f'`{i}`' for i in sessions[s]['choices']]))
            msg = '\n'.join(chunks)
            em = discord.Embed(title=f"Sessions de vote en cours sur ***{interaction.guild.name}***", description=msg, color=0x2F3136)
            return await interaction.response.send_message(embed=em, ephemeral=True)
        
        if session not in sessions:
            return await interaction.response.send_message("**Erreur ·** Cet identifiant de session de vote est invalide", ephemeral=True)
        
        if sessions[session]['author_id'] != interaction.user.id or not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("**Erreur ·** Vous n'avez pas l'autorisation de terminer ce sondage\nVous devez être le créateur du sondage ou un modérateur possédant la permission `ban_members`", ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        votes = self.get_all_votes_from_session(interaction.guild, session)
        
        em = discord.Embed(title=f"***{sessions[session]['title']}***", description='\n'.join([f'• `{i}`' for i in sessions[session]['choices']]), color=discord.Color.red())
        em.add_field(name="Nombre de votants", value=f"**{len(votes)}** vote(s)")
        em.set_footer(text="Êtes-vous sûr de vouloir terminer ce sondage ?")
        
        view = Confirmbutton(interaction)
        await interaction.followup.send(embed=em, view=view)
        await view.wait()
        if not view.value:
            return await interaction.edit_original_response(content="**Annulé ·** Le sondage n'a pas été supprimé", embed=None, view=None)
        
        embed = self.embed_poll_results(interaction.guild, session)
        
        self.delete_poll_session(interaction.guild, session)
        await interaction.edit_original_response(content="**Sondage terminé**", embed=embed, view=None)
        
    @stop_session.autocomplete('session')
    async def stop_autocomplete_callback(self, interaction: discord.Interaction, current: str):
        sessions = self.get_poll_sessions(interaction.guild)
        if sessions:
            sessions = fuzzy.finder(current, [(s, sessions[s]['title']) for s in sessions], key=lambda s: s[1])
            return [app_commands.Choice(name=s[1], value=s[0]) for s in sessions]
        else:
            return []
        
    # VOTES -----------------------------------------------    
    
    def set_member_vote(self, member: discord.Member, session_id: str, vote: str):
        sessions = self.get_poll_sessions(member.guild)
        if session_id not in sessions:
            raise KeyError(f"La session #{session_id} n'existe pas")
        if vote not in sessions[session_id]['choices']:
            raise KeyError(f"Le choix '{vote}' n'existe pas pour la session #{session_id}")
        
        voteid = f'{session_id}{member.id}'
        conn = get_sqlite_database('polls', 'g' + str(member.guild.id))
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO votes (vote_id, session_id, user_id, choice) VALUES (?, ?, ?, ?)", (voteid, session_id, member.id, vote))
        conn.commit()
        cursor.close()
        conn.close()
        
    def remove_member_vote(self, member: discord.Member, session_id: str):
        sessions = self.get_poll_sessions(member.guild)
        if session_id not in sessions:
            raise KeyError(f"La session #{session_id} n'existe pas")
        
        voteid = hash(f'{session_id}{member.id}')
        conn = get_sqlite_database('polls', 'g' + str(member.guild.id))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM votes WHERE vote_id=?", (voteid,))
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_all_votes_from_session(self, guild: discord.Guild, session_id: str):
        sessions = self.get_poll_sessions(guild)
        if session_id not in sessions:
            raise KeyError(f"La session #{session_id} n'existe pas")
        
        conn = get_sqlite_database('polls', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, choice FROM votes WHERE session_id=?", (session_id,))
        votes = cursor.fetchall()
        cursor.close()
        conn.close()
        return votes
        
    @app_commands.command(name='vote')
    async def vote(self, interaction: discord.Interaction, session: Optional[str] = None):
        """Participer à une session de vote ou consulter les sessions en cours

        :param session: Optionnel, session de vote en cours que vous voulez rejoindre 
        """
        sessions = self.get_poll_sessions(interaction.guild)
        if not sessions:
            return await interaction.response.send_message("**Erreur ·** Aucune session de vote n'est actuellement ouverte", ephemeral=True)
        
        if not session:
            msg = ""
            chunks = []
            for s in sessions:
                chunks.append(f"***{sessions[s]['title']}*** : " + ' '.join([f'`{i}`' for i in sessions[s]['choices']]))
            msg = '\n'.join(chunks)
            em = discord.Embed(title=f"Sessions de vote en cours sur ***{interaction.guild.name}***", description=msg, color=0x2F3136)
            return await interaction.response.send_message(embed=em, ephemeral=True)
        
        if session not in sessions:
            return await interaction.response.send_message("**Erreur ·** Cet identifiant de session de vote est invalide", ephemeral=True)
        
        view = discord.ui.View()
        view.add_item(VoteSelectMenu(interaction, self, session, sessions[session]['choices']))
        await interaction.response.send_message(content=f"**Sondage :** *{sessions[session]['title']}*", view=view, ephemeral=True)
        
    @vote.autocomplete('session')
    async def vote_autocomplete_callback(self, interaction: discord.Interaction, current: str):
        sessions = self.get_poll_sessions(interaction.guild)
        if sessions:
            sessions = fuzzy.finder(current, [(s, sessions[s]['title']) for s in sessions], key=lambda s: s[1])
            return [app_commands.Choice(name=s[1], value=s[0]) for s in sessions]
        else:
            return []

async def setup(bot):
    await bot.add_cog(Polls(bot))
