import json
import logging
import re
import sqlite3
import time
from datetime import datetime
from copy import copy
from typing import Any, Optional, Callable, List, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks
from tabulate import tabulate

from common.dataio import get_sqlite_database
from common.utils import fuzzy, pretty

logger = logging.getLogger('nero.Insights')

DEFAULT_SETTINGS : List[Tuple[str, Any]] = [
    ('', ''),
]

CONDITION_MAP = {
    'on_message': {
        'content': str,
        'author_id': int
    }
}

OPERATOR_MAP = {
    'exact': lambda x, y: x == y,
    'startswith': lambda x, y: x.startswith(y),
    'endswith': lambda x, y: x.endswith(y),
    'in': lambda x, y: x in y,
    'not_in': lambda x, y: x not in y,
    'regex': lambda x, y: re.match(y, x)
}

class MakerError(Exception):
    """Erreurs spécifiques à Maker"""
    
class Trigger():
    def __init__(self, conditions: List['Condition'], program: 'Program') -> None:
        self.conditions = conditions
        self.program = program
        
    def check_all(self, object: Union[discord.Message, discord.Reaction]):
        """Vérifie si l'objet passé en paramètre correspond aux conditions du déclencheur."""
        return all([c.check(object) for c in self.conditions])


class Condition():
    def __init__(self, raw_string: str) -> None:
        self._raw_string = raw_string.rstrip()
        self._data = self.__parse(raw_string)
        
        self.event = self._data[0]
        self.property = self._data[1]
        self.operator = self._data[2]
        self.field = self._data[3]
        
    def __repr__(self) -> str:
        return f"Condition({' '.join(self._raw_string.split('>'))})"
        
    def __parse(self, string: str):
        event, property, operator, field = [c.strip() for c in string.split(">")]
        event, property, operator = event.lower(), property.lower(), operator.lower()
        if event not in CONDITION_MAP:
            raise ValueError("Invalid event")
        if property not in CONDITION_MAP[event]:
            raise ValueError("Invalid property")
        if operator not in OPERATOR_MAP:
            raise ValueError("Invalid operator")
        
        if ',' in field:
            field = [CONDITION_MAP[event][property](f.strip()) for f in field.split(',')]
        else:
            field = CONDITION_MAP[event][property](field)
        return event, property, operator, field
    
    def check(self, object: Union[discord.Message, discord.Reaction]):
        """Vérifie si l'objet passé en paramètre correspond à la condition."""
        # on_message
        if self.event == "on_message" and isinstance(object, discord.Message):
            if self.property == "content":
                return OPERATOR_MAP[self.operator](object.content, self.field)
            elif self.property == "author_id":
                return OPERATOR_MAP[self.operator](object.author.id, self.field)
            
        # on_reaction_add
        elif self.event == "on_reaction_add" and isinstance(object, discord.Reaction):
            if self.property == "emoji":
                return OPERATOR_MAP[self.operator](object.emoji, self.field)
            
        return False


class Program():
    def __init__(self, cog: 'Maker', raw_string: str) -> None:
        self._cog = cog
        self._raw_string = raw_string.rstrip()
        self._lines = self._raw_string.splitlines()
        
    def __list_needed_variables(self):
        return [v[1:-1] for v in re.findall(r"\{(.+?)\}", self._raw_string)]
        
    async def execute(self, external_values: dict, context: dict):
        program = self._lines
        program = [line.strip() for line in program if line.strip()]
        prog_variables = {}
        for line in program:
            if line.startswith("$"):
                var, op, value = line.split(">")
                if op == "get":
                    prog_variables[var] = external_values[value[1:-1]]
                elif op == "set":
                    all_values = {**external_values, **prog_variables}
                    prog_variables[var] = value.format(**all_values)
            else:
                func, *args = line.split(">")
                if func == 'send' and 'channel' in context:
                    content_type, content = args
                    if content_type == 'text':
                        channel = context['channel']
                        await channel.send(content)
        return prog_variables
    
    @property
    def needed_variables(self):
        return self.__list_needed_variables()
    
        
class CreateTriggerModal(discord.ui.Modal, title="Créer un déclencheur"):
    name = discord.ui.TextInput(label="Nom", placeholder="Nom du déclencheur", required=True, max_length=32, style=discord.TextStyle.short)
    description = discord.ui.TextInput(label="Description", placeholder="Courte description du déclencheur", required=True, min_length=10, max_length=100, style=discord.TextStyle.short)
    condition = discord.ui.TextInput(label="Condition", placeholder="Condition de déclenchement du programme", required=True, max_length=200, style=discord.TextStyle.short)
    program = discord.ui.TextInput(label="Programme", placeholder="Programme à exécuter", required=True, max_length=500, style=discord.TextStyle.paragraph)
    
    def __init__(self, cog: "Maker") -> None:
        super().__init__()
        self.cog = cog
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.cog.create_poll_session(interaction.user, interaction.channel, str(self.sesstitle), self.choices.value, int(self.poll_timeout.value) * 60)
        await interaction.response.send_message(f"Nouvelle session de vote **{self.sesstitle}** créée avec succès.", ephemeral=True)
        if self.poll_timeout.value != '0':
            await interaction.channel.send(f"Une session de vote **{self.sesstitle}** [{' '.join([f'`{i}`' for i in self.cog.parse_choices(self.choices.value)])}] expirant dans **{self.poll_timeout.value}m** a été créée par {interaction.user} !\nParticipez-y avec `/poll vote`")
        else:
            await interaction.channel.send(f"Une session de vote **{self.sesstitle}** [{' '.join([f'`{i}`' for i in self.cog.parse_choices(self.choices.value)])}] a été créée par {interaction.user} !\nParticipez-y avec `/poll vote`")
        
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message(f"Oups ! Il y a eu une erreur lors de la création de la session.\nVérifiez que vous avez rempli les champs correctement.", ephemeral=True)
        logger.error(error)

class Maker(commands.GroupCog, group_name="maker", description="Créateur de déclencheurs personnalisés"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        self._initialize_database()
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._initialize_database(guild)
        
    def _initialize_database(self, guild: discord.Guild = None):
        initguilds = [guild] if guild else self.bot.guilds
        for g in initguilds:
            conn = get_sqlite_database('maker', f'g{g.id}')
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS triggers (id TEXT PRIMARY KEY, name TEXT, description TEXT, condition TEXT, program TEXT, enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)))")
            for name, default_value in DEFAULT_SETTINGS:
                cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
            conn.commit()
            cursor.close()
            conn.close()
            
    def get_trigger(self, guild: discord.Guild = None, trigger_id: str = None):
        conn = get_sqlite_database('maker', f'g{guild.id}')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM triggers WHERE id = ?", (trigger_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return dict(result) if result else None
    
    def set_trigger(self, guild: discord.Guild = None, trigger_id: str = None, **kwargs):
        conn = get_sqlite_database('maker', f'g{guild.id}')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO triggers (id, name, description, condition, program) VALUES (?, ?, ?, ?, ?)", (trigger_id, kwargs.get('name'), kwargs.get('description'), kwargs.get('condition'), kwargs.get('program')))
        conn.commit()
        cursor.close()
        conn.close()
    
    
    
    @app_commands.command(name="new")
    @app_commands.guild_only()
    async def create_new_trigger(self, interaction: discord.Interaction):
        """Créer un nouveau déclencheur personnalisé"""
        pass

    
        
async def setup(bot):
    await bot.add_cog(Maker(bot))