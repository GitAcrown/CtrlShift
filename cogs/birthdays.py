import discord
import logging
import time
from datetime import datetime
import operator
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from tinydb import Query

from common.dataio import get_database

logger = logging.getLogger('galba.Birthdays')

MONTHS_CHOICES = [
    Choice(name='Janvier', value=1),
    Choice(name='Février', value=2),
    Choice(name='Mars', value=3),
    Choice(name='Avril', value=4),
    Choice(name='Mai', value=5),
    Choice(name='Juin', value=6),
    Choice(name='Juillet', value=7),
    Choice(name='Août', value=8),
    Choice(name='Septembre', value=9),
    Choice(name='Octobre', value=10),
    Choice(name='Novembre', value=11),
    Choice(name='Décembre', value=12)
]

class Birthdays(commands.Cog):
    """Gestion et traçage des anniversaires"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task_bday.start()
        
        self.context_menu = app_commands.ContextMenu(
            name='Anniversaire',
            callback=self.show_user_bday
        )
        self.bot.tree.add_command(self.context_menu)
        
    async def cog_unload(self) -> None:
        self.task_bday.cancel()
            
    @tasks.loop(hours=1.0)
    async def task_bday(self):
        now_day, now_month = int(time.strftime('%d', time.localtime())), int(time.strftime('%m', time.localtime()))
        logger.info(f"Check Bday effectué - {now_day}/{now_month}")
        
    @task_bday.before_loop
    async def before_task_bday(self):
        await self.bot.wait_until_ready()
        logger.info("Start task_bday")
        
        
    # GUILD LEVEL ----------------------------------
        
    @app_commands.command(name='bdayrole')
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def bdayrole(self, interaction: discord.Interaction, role: discord.Role):
        """Rôle à attribuer automatiquement le jour de l'anniversaire

        :param role: Rôle à attribuer
        """
        db = get_database('birthdays', str(interaction.guild_id))
        Setting = Query()
        db.upsert({'name': 'role', 'value': role.id}, Setting.name == 'role')
        await interaction.response.send_message(f"Le rôle a bien été configuré sur **{role}** !")
        
        
    # USER LEVEL -----------------------------------
        
    @app_commands.command(name='bday')
    @app_commands.choices(mois=MONTHS_CHOICES)
    async def bday(self, interaction: discord.Interaction, jour: app_commands.Range[int, 1, 31], mois: app_commands.Range[int, 1, 12]):
        """Informer le bot de votre date d'anniversaire (enregistré globalement)

        :param jour: Jour de naissance (1-31)
        :param mois: Mois de naissance
        """
        db = get_database('birthdays')
        User = Query()
        db.upsert({'uid': interaction.user.id, 'day': jour, 'month': mois}, User.uid == interaction.user.id)
        await interaction.response.send_message(f"**Votre anniversaire ({jour}/{mois}) a été enregistré !**\nPour le retirer, utilisez `/removebday`.")
        
    @app_commands.command(name='removebday')
    async def removebday(self, interaction: discord.Interaction):
        """Retirer votre anniversaire de la base de données du bot (global)"""
        db = get_database('birthdays')
        User = Query()
        db.remove(User.uid == interaction.user.id)
        await interaction.response.send_message(f"Votre anniversaire a été supprimé de la base de données avec succès.")
        
    @app_commands.command(name="nextbday")
    async def nextbday(self, interaction: discord.Interaction):
        """Consulter les prochains anniversaires sur ce serveur"""
        guild = interaction.guild
        await interaction.response.defer()
        today = datetime.today()
        members_id = [m.id for m in guild.members]
        db = get_database('birthdays')
        User = Query()
        all_r = db.search(User.uid.test(lambda x: x in members_id))
        if all_r:
            annivs = []
            for r in all_r:
                user_bday = f"{r['day']}/{r['month']}"
                user_date = datetime.strptime(user_bday, '%d/%m').replace(year=today.year)
                if today < user_date:
                    annivs.append([r['uid'], user_bday, user_date.timestamp(), user_date])
                else:
                    annivs.append([r['uid'], user_bday, user_date.replace(year=today.year + 1).timestamp(), user_date.replace(year=today.year + 1)])
            sorted_r = sorted(annivs, key=operator.itemgetter(2))[:5]
            if sorted_r:
                msg = ''
                for l in sorted_r:
                    msg += f"- {guild.get_member(l[0]).mention} : `{l[3].strftime('%d/%m/%Y')}`\n"
                
                em = discord.Embed(title=f"Prochains anniversaires sur **{guild.name}**", description=msg, color=0x2F3136)
                await interaction.followup.send(embed=em)
            else:
                await interaction.followup.send("**Aucun anniversaire n'est à venir ·** Aucun prochain anniversaire n'a été trouvé dans la base de données")
        else:
            await interaction.followup.send("**Aucun anniversaire n'est à venir ·** Aucun membre du serveur n'a configuré son anniversaire")
        
        
    async def show_user_bday(self, interaction: discord.Interaction, member: discord.Member):
        """Menu contextuel permettant l'affichage de l'anniversaire du membre visé

        :param user: Utilisateur visé par la commande
        """
        today = datetime.today()
        db = get_database('birthdays')
        User = Query()
        r = db.search(User.uid == member.id)
        if r:
            user_bday = f"{r[0]['day']}/{r[0]['month']}"
            userdate = datetime.strptime(user_bday, '%d/%m')
            userdate = userdate.replace(year=today.year)
            msg = f"__Anniversaire :__ **{user_bday}**\n"

            if today >= userdate:
                next_date = userdate.replace(year=today.year + 1)
            else:
                next_date = userdate
            msg += f"__Prochain :__ `{next_date.strftime('%d/%m/%Y')}`"
        
            em = discord.Embed(title=f"Anniversaire de **{member.display_name}**", description=msg, color=0x2F3136)
            em.set_thumbnail(url=member.display_avatar.url)
            await interaction.response.send_message(embed=em, ephemeral=True)
        else:
            await interaction.response.send_message("**Erreur ·** Ce membre n'a pas réglé son anniversaire sur ce bot.", ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Birthdays(bot))
