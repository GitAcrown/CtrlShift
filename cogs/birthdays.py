import discord
import logging
from datetime import datetime
import operator
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from typing import Optional
import json

from common.dataio import get_sqlite_database

logger = logging.getLogger('nero.Birthdays')

DEFAULT_SETTINGS = [
    ('BirthdayRoleID', 0),
    ('NotificationChannelID', 0)
]

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
        
        self.context_menu = app_commands.ContextMenu(
            name='Anniversaire',
            callback=self.ctx_usercommand_bday
        )
        self.bot.tree.add_command(self.context_menu)
        
    #     self.task_check_birthdays.start()
        
    # @commands.Cog.listener()
    # async def on_ready(self):
    #     self.initialize_database()
        
    # @commands.Cog.listener()
    # async def on_guild_join(self, guild: discord.Guild):
    #     self.initialize_database()

    # def cog_unload(self):
    #     self.task_check_birthdays.cancel()
        
    # @tasks.loop(minutes=1.0)
    # async def task_check_birthdays(self):
    #     bdays = self.get_all_birthdays()
    #     today = datetime.now().strftime('%d/%m')
    #     for bday in bdays:
    #         if f"{bday[1]}/{bday[2]}" == today:
                
    #             for guild in self.bot.guilds:
    #                 settings = self.get_guild_settings(guild)
    #                 if settings['BirthdayRoleID'] and :
    #                     bdayrole = guild.get_role(int(settings['BirthdayRoleID']))
    #                     try:
    #                         member = guild.get_member(bday[0])
    #                     except:
    #                         break
    #                     if bdayrole not in member.roles:
    #                         await member.add_roles([])
                    
    # USER LEVEL -----------------------------------
    
    def initialize_database(self):
        conn = get_sqlite_database('birthdays')
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, day INTEGER, month INTEGER)")
        conn.commit()
        cursor.close()
        conn.close()
        for guild in self.bot.guilds:
            conn = get_sqlite_database('birthdays', 'g' + str(guild.id))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (name TINYTEXT PRIMARY KEY, value TEXT)")
            for name, default_value in DEFAULT_SETTINGS:
                cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
            conn.commit()
            cursor.close()
            conn.close()
        
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
    
    def get_zodiac_sign(self, user_id: int):
        bday = self.get_birthday(user_id)
        user_bday = f"{bday[0]}/{bday[1]}"
        userdate = datetime.strptime(user_bday, '%d/%m').replace(year=datetime.today().year)
        
        zodiacs = [(120, 'Capricorne', '♑'), (218, 'Verseau', '♒'), (320, 'Poisson', '♓'), (420, 'Bélier', '♈'), (521, 'Taureau', '♉'),
           (621, 'Gémeaux', '♊'), (722, 'Cancer', '♋'), (823, 'Lion', '♌'), (923, 'Vierge', '♍'), (1023, 'Balance', '♎'),
           (1122, 'Scorpion', '♏'), (1222, 'Sagittaire', '♐'), (1231, 'Capricorne', '♑')]
        date_number = int("".join((str(userdate.month), '%02d' % userdate.day)))
        for z in zodiacs:
            if date_number <= z[0]:
                return z[1], z[2]
    
    def get_guild_settings(self, guild: discord.Guild) -> dict:
        """Obtenir les paramètres du serveur

        :param guild: Serveur des paramètres à récupérer
        :return: dict
        """
        conn = get_sqlite_database('birthdays', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings")
        settings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        from_json = {s[0] : json.loads(s[1]) for s in settings}
        return from_json
    
    def set_guild_settings(self, guild: discord.Guild, update: dict):
        """Met à jours les paramètres du serveur

        :param guild: Serveur à mettre à jour
        :param update: Paramètres à mettre à jour (toutes les valeurs seront automatiquement sérialisés en JSON)
        """
        conn = get_sqlite_database('birthdays', 'g' + str(guild.id))
        cursor = conn.cursor()
        for upd in update:
            cursor.execute("UPDATE settings SET value=? WHERE name=?", (json.dumps(update[upd]), upd))
        conn.commit()
        cursor.close()
        conn.close()
    
        
    @app_commands.command(name="set")
    @app_commands.choices(month=MONTHS_CHOICES)
    async def bday_set(self, interaction: discord.Interaction, day: app_commands.Range[int, 1, 31], month: app_commands.Range[int, 1, 12]):
        """Informer le bot de votre date d'anniversaire (enregistré globalement)

        :param day: Jour de naissance (1-31)
        :param month: Mois de naissance
        """
        try:
            datetime.strptime(f'{day}/{month}', '%d/%m')
        except:
            return await interaction.response.send_message(f"**Erreur ·** La date fournie est invalide, veuillez vérifier les valeurs données.", ephemeral=True)
        self.add_birthday(interaction.user.id, day, month)
        await interaction.response.send_message(f"**Votre anniversaire ({day}/{month}) a été enregistré !**\nPour le retirer, utilisez </bday remove:1041046244765749359>.")
        
    @app_commands.command(name='remove')
    async def bday_remove(self, interaction: discord.Interaction):
        """Retirer votre anniversaire de la base de données du bot (global)"""
        if self.get_birthday(interaction.user.id):
            self.remove_birthday(interaction.user.id)
            await interaction.response.send_message(f"Votre anniversaire a été supprimé de la base de données avec succès.")
        else:
            await interaction.response.send_message("**Erreur ·** Vous n'avez pas réglé votre anniversaire sur ce bot.", ephemeral=True)
            
    @app_commands.command(name="list")
    async def bday_list(self, interaction: discord.Interaction, display: Optional[int] = 5):
        """Consulter les X prochains anniversaires sur ce serveur
        
        :param affichage: Nombre d'anniversaire à afficher, par défaut 5, max. 10"""
        guild = interaction.guild
        await interaction.response.defer()
        today = datetime.today()
        display = min(display, 10)
        
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
            sorted_r = sorted(annivs, key=operator.itemgetter(2))[:display]
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

        :param member: Utilisateur visé par la commande
        """
        today = datetime.today()
        bday = self.get_birthday(member.id)
        if bday:
            user_bday = f"{bday[0]}/{bday[1]}"
            userdate = datetime.strptime(user_bday, '%d/%m')
            userdate = userdate.replace(year=today.year)
            msg = f"**Anniversaire ·** {user_bday}\n"

            if today >= userdate:
                next_date = userdate.replace(year=today.year + 1)
            else:
                next_date = userdate
            msg += f"**Prochain ·** <t:{int(next_date.timestamp())}:D>\n"
            msg += f"**Signe Astrologique ·** {' '.join(self.get_zodiac_sign(member.id))}"
        
            em = discord.Embed(title=f"Anniversaire de **{member.display_name}**", description=msg, color=0x2F3136)
            em.set_thumbnail(url=member.display_avatar.url)
            await interaction.response.send_message(embed=em, ephemeral=True)
        else:
            await interaction.response.send_message("**Erreur ·** Ce membre n'a pas réglé son anniversaire sur ce bot.", ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Birthdays(bot))
