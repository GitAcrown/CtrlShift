import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import get as discord_get
from tinydb import TinyDB, Query
import random
import logging
from typing import Optional, Literal, Union

from common.dataio import get_tinydb_database

logger = logging.getLogger('galba.Snowfest')

# TODO
# - Stats & items améliorant les stats (précision, chance, force)

SNOWBALL_TYPES = {
    'normale': {
        'name': "Normale",
        'miss_prob': 0.30,
        'damage_range': (7, 15),
        'critical_x': 2.0,
        'critical_luck': 0.20,
        'description': "Une boule de neige classique, faite de vraie neige.",
        'make_weight': 1,
        'icon_url': "",
        
        'msg': ("{target} s'est pris.e une boule de neige dans le dos !", "{target} s'est fait tiré dessus une boule de neige lancée à pleine allure !"),
        'msg_crit': ["{target} s'est pris.e la boule de neige en plein dans la face !"]
    },
    'boueuse': {
        'name': "Boueuse",
        'miss_prob': 0.10,
        'damage_range': (3, 9),
        'critical_x': 1.5,
        'critical_luck': 0.25,
        'description': "Une boule de neige boueuse provenant d'un bord de route parisien.",
        'make_weight': 0.75,
        'icon_url': "",
        
        'msg': ("{target} s'est pris.e une boule de neige boueuse ! Berk, dégoutant.", "{target} s'est fait tiré dessus une boule de neige boueuse qui s'est écrasée sur son pantalon !"),
        'msg_crit': ["{target} s'est pris.e une boule de neige bien boueuse en pleine face et en a plein la bouche !"]
    },
    'glacee': {
        'name': "Glacée",
        'miss_prob': 0.20,
        'damage_range': (10, 25),
        'critical_x': 2.5,
        'critical_luck': 0.10,
        'description': "Une boule de neige glacée et compacte qui peut faire très mal.",
        'make_weight': 0.33,
        'icon_url': "",
        
        'msg': ("Aïe ! {target} s'est pris.e une boule de neige bien compacte dans la nuque !", "{target} s'est fait tiré dessus une boule de neige glacée lancée à pleine vitesse !"),
        'msg_crit': ["{target} se prend une boule de neige glacée et compacte et trébuche en finissant au sol !"]
    },
    'surprise': {
        'name': "Surprise",
        'miss_prob': 0.30,
        'damage_range': (4, 12),
        'critical_x': 4.0,
        'critical_luck': 0.33,
        'description': "Une boule de neige ramassée dans les décombres, contenant potentiellement des objets dangereux.",
        'make_weight': 0.5,
        'icon_url': "",
        
        'msg': ("{target} s'est pris.e une boule de neige dans le dos !", "{target} s'est fait tiré dessus une boule de neige lancée à pleine allure !"),
        'msg_crit': ["Oh ! {target} s'est pris.e dans la tête une boule de neige surprise qui contenait {junk} !"]
    }
}

SnowballTypes = Literal['normale', 'boueuse', 'glacee', 'surprise']

JUNK_LIST = ('une grosse pierre', 'une serringue usagée', 'un morceau de métal', "la clef de l'Appart")


class Snowfest(commands.Cog):
    """Jeu des fêtes de fin d'année 2022"""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
    def get_snowball_inventory(self, member: discord.Member):
        db = get_tinydb_database('snowfest', member.guild.id)
        table = db.table(member.id)
        Data = Query()
        return table.get(Data.name == 'snowballs') if table.get(Data.name == 'snowballs') else {i: 0 for i in SNOWBALL_TYPES}

    def add_snowball(self, member: discord.Member, type: SnowballTypes, qte: int = 1):
        db = get_tinydb_database('snowfest', member.guild.id)
        table = db.table(member.id)
        Data = Query()
        table.subtract(Data.name == 'snowballs')
     
    # LANCER ------------------------------------------------
    def throw_snowball_cd(interaction: discord.Interaction):
        if interaction.user.id == 172376505354158080:
            return None
        return app_commands.Cooldown(3, 600)

    @app_commands.command(name='throw')
    @app_commands.checks.dynamic_cooldown(throw_snowball_cd)
    async def throw_snowball(self, interaction: discord.Interaction, member: discord.Member, type: str):
        """Lancer une boule de neige au membre visé

        :param member: Membre à viser
        :param type: Type de boule de neige à lancer
        """
        snowball = SNOWBALL_TYPES[type]
        if not self.get_snowball_inventory(interaction.user)[type]:
            return await interaction.response.send_message(f"**Tu n'as plus de boule de neige {snowball['name'].lower()} !**\nPour créer des boules de neige, utilise `/make`.", ephemeral=True)
        
        if random.uniform(0, 1) <= snowball['miss_prob']:
            msg = random.choice((f"Désolé, vous avez loupé **{member.display_name}**...", 
                                 f"Dommage ! C'était bien tenté mais vous avez loupé **{member.display_name}**.",
                                 f"Mince ! **{member.display_name}** a esquivé votre boule de neige."))
            await interaction.response.send_message(msg, ephemeral=True)
            
        dmg = random.randint(*snowball['damage_range'])
        crit = random.uniform(0, 1) <= snowball['critical_luck']
        if crit:
            dmg *= snowball['critical_x']
            dmg = round(dmg)
            msg = random.choice(snowball['msg']) + f' (**{dmg}** dmg)'
        else:
            dmg = round(dmg)
            msg = '**`!! CRIT !!`** ' + random.choice(snowball['msg_crit']) + f' (**{dmg}** dmg)'
        await interaction.response.send_message(msg.format(target=member.display_name, junk=random.choice(JUNK_LIST)))
    
    @throw_snowball.autocomplete('type')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        userinv = self.get_snowball_inventory(interaction.user)
        return [app_commands.Choice(name=f"{SNOWBALL_TYPES[t]['name']} (x{userinv.get(t, 0)})", value=t) for t in SNOWBALL_TYPES] 
    
    
    # RAMASSER---------------------------------------------------
    def make_snowball_cd(interaction: discord.Interaction):
        if interaction.user.id == 172376505354158080:
            return None
        return app_commands.Cooldown(1, 600)

    @app_commands.command(name='make')
    @app_commands.checks.dynamic_cooldown(make_snowball_cd)
    async def make_snowball(self, interaction: discord.Interaction):
        """Créer des boules de neige
        """
        nbsb = random.randint(2, 5)
        snowballs_random = random.choices(list(SNOWBALL_TYPES.keys()), [i['make_weight'] for i in SNOWBALL_TYPES], k=nbsb)
        snowballs = {i: snowballs_random.count(i) for i in set(snowballs_random)}
        
        db = get_tinydb_database('snowfest', interaction.guild.id)
        table = db.table(interaction.user.id)
        Data = Query()
        usersb = table.get(Data.name == 'snowballs')
        if usersb:
            for sb in snowballs:
                usersb.add(sb, snowballs[sb])
        else:
            usersb.update(snowballs)
        
        msg = []
        for sb in snowballs:
            sbdata = SNOWBALL_TYPES[sb]
            msg.append(f"• **{sbdata['name']}** x{snowballs[sb]}\n  *{sbdata['description']}*")

        em = discord.Embed(title="**Vous avez ramassé :**", description=msg.join('\n'), color=0x2F3136)
        await interaction.response.send_message(embed=em, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Snowfest(bot))
