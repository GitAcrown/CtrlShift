import discord
import logging
import time
from datetime import datetime
import operator
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from tinydb import Query

from common.dataio import get_sqlite_database

logger = logging.getLogger('galba.Birthdays')

bday_group = app_commands.Group(name="bday", description="Gestion des anniversaires")

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

class Birthdays(commands.GroupCog, group_name="bday", description="Gestion des anniversaires"):
    """Gestion et traçage des anniversaires"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    #   self.task_bday.start()
        
        self.context_menu = app_commands.ContextMenu(
            name='Anniversaire',
            callback=self.ctx_usercommand_bday
        )
        self.bot.tree.add_command(self.context_menu)
        self.initialize_database()
        
    # USER LEVEL -----------------------------------
    
    def initialize_database(self):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, day INTEGER, month INTEGER)")
        conn.commit()
        cursor.close()
        conn.close()
        
    # def import_tinydb_to_sqlite(self):
    #     db = get_tinydb_database('birthdays')
    #     tdb = db.all()
        
    #     conn = get_sqlite_database('birthdays')
    #     cursor = conn.cursor()

    #     for u in tdb:
    #         cursor.execute("INSERT OR IGNORE INTO users (user_id, day, month) VALUES (?, ?, ?)", (u['uid'], u['day'], u['month']))
    #     conn.commit()
    #     cursor.close()
    #     conn.close()
        
    def add_birthday(self, user_id: int, day: int, month: int):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, day, month) VALUES (?, ?, ?)", (user_id, day, month))
        conn.commit()
        cursor.close()
        conn.close()
        
    def remove_birthday(self, user_id: int):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id=?", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
    def get_birthday(self, user_id: int):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("SELECT day, month FROM users WHERE user_id=?", (user_id,))
        birthday = cursor.fetchone()
        cursor.close()
        conn.close()
        return birthday
    
    def get_all_birthdays(self):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, day, month FROM users")
        bdays = cursor.fetchall()
        cursor.close()
        conn.close()
        return bdays
        
    @app_commands.command(name="set")
    @app_commands.choices(mois=MONTHS_CHOICES)
    async def bday_set(self, interaction: discord.Interaction, jour: app_commands.Range[int, 1, 31], mois: app_commands.Range[int, 1, 12]):
        """Informer le bot de votre date d'anniversaire (enregistré globalement)

        :param jour: Jour de naissance (1-31)
        :param mois: Mois de naissance
        """
        self.add_birthday(interaction.user.id, jour, mois)
        await interaction.response.send_message(f"**Votre anniversaire ({jour}/{mois}) a été enregistré !**\nPour le retirer, utilisez `/bday remove`.")
        
    @app_commands.command(name='remove')
    async def bday_remove(self, interaction: discord.Interaction):
        """Retirer votre anniversaire de la base de données du bot (global)"""
        self.remove_birthday(interaction.user.id)
        await interaction.response.send_message(f"Votre anniversaire a été supprimé de la base de données avec succès.")
        
    @app_commands.command(name="list")
    async def bday_list(self, interaction: discord.Interaction, affichage: int = 5):
        """Consulter les X prochains anniversaires sur ce serveur
        
        :param affichage: Nombre d'anniversaire à afficher, par défaut 5, max. 10"""
        guild = interaction.guild
        await interaction.response.defer()
        today = datetime.today()
        affichage = min(affichage, 10)
        
        bdays = self.get_all_birthdays()
        all_members = [m.id for m in guild.members]
        if bdays:
            annivs = []
            for bday in bdays:
                if bday[0] in all_members:
                    user_bday = f"{bday[1]}/{bday[2]}"
                    user_date = datetime.strptime(user_bday, '%d/%m').replace(year=today.year)
                    if today < user_date:
                        annivs.append([guild.get_member(bday[0]), user_bday, user_date.timestamp(), user_date])
                    else:
                        annivs.append([guild.get_member(bday[0]), user_bday, user_date.replace(year=today.year + 1).timestamp(), user_date.replace(year=today.year + 1)])
            sorted_r = sorted(annivs, key=operator.itemgetter(2))[:affichage]
            if sorted_r:
                msg = ''
                for l in sorted_r:
                    try:
                        msg += f"• {l[0].mention} : `{l[3].strftime('%d/%m/%Y')}`\n"
                    except:
                        logger.info(f"Impossible d'accéder à USER_ID:{l[0]}", exc_info=True)
                
                em = discord.Embed(title=f"Prochains anniversaires sur **{guild.name}**", description=msg, color=0x2F3136)
                em.set_footer(text=f"Anniversaires enregistrés sur ce serveur · {len(annivs)}")
                await interaction.followup.send(embed=em)
            else:
                await interaction.followup.send("**Aucun anniversaire n'est à venir ·** Aucun prochain anniversaire n'a été trouvé dans la base de données")
        else:
            await interaction.followup.send("**Aucun anniversaire n'est à venir ·** Aucun membre du serveur n'a configuré son anniversaire")
        
        
    async def ctx_usercommand_bday(self, interaction: discord.Interaction, member: discord.Member):
        """Menu contextuel permettant l'affichage de l'anniversaire du membre visé

        :param user: Utilisateur visé par la commande
        """
        today = datetime.today()
        bday = self.get_birthday(interaction.user.id)
        if bday:
            user_bday = f"{bday[0]}/{bday[1]}"
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
