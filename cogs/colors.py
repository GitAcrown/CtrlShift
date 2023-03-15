import logging
import time
import iso3166
from copy import copy
from datetime import datetime, timezone
from typing import Any, List, Optional, Union

import discord
import requests
import colorgram
import json
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps

from common.utils import pretty, fuzzy
from common.dataio import get_sqlite_database

logger = logging.getLogger('ctrlshift.Colors')

        
class Colors(commands.GroupCog, group_name='color', description='Gestion des rôles de couleur'):
    """Gestion des rôles de couleur"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    def normalize_color(self, color: str) -> str:
        """Renvoie la couleur hexadécimale normalisée au format RRGGBB"""
        if color.startswith('#'):
            color = color[1:]
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        return color
        
    def is_recyclable(self, role: discord.Role, request_user: Optional[discord.Member] = None) -> bool:
        """Renvoie True si le rôle n'est possédé par personne ou par le membre faisant la demande, sinon False"""
        if not role.members:
            return True
        elif request_user and role.members == [request_user]:
            return True
        return False

    def get_color_role(self, guild: discord.Guild, hex_color: str) -> Optional[discord.Role]:
        """Renvoie le rôle de couleur correspondant à la couleur hexadécimale donnée"""
        name = f"#{self.normalize_color(hex_color)}"
        return discord.utils.get(guild.roles, name=name)

    def get_color_roles(self, guild: discord.Guild) -> List[discord.Role]:
        """Renvoie la liste des rôles de couleur du serveur"""
        return [role for role in guild.roles if role.name.startswith('#') and len(role.name) == 7]
    
    async def get_color_info(self, color: str) -> Optional[dict]:
        """Renvoie les informations de la couleur donnée"""
        color = self.normalize_color(color)
        url = f"https://www.thecolorapi.com/id?hex={color}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    
    async def get_color_scheme(self, color: str) -> Optional[dict]:
        """Renvoie la palette de couleurs correspondant à la couleur donnée"""
        color = self.normalize_color(color)
        url = f"https://www.thecolorapi.com/scheme?hex={color}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    
    def extract_palette(self, img: BytesIO, n: int = 5) -> List[colorgram.Color]:
        image = Image.open(img)
        return colorgram.extract(image, n)
    
    def draw_image_palette(self, img: Union[str, BytesIO], n_colors: int = 5) -> Image.Image:
        """Ajoute la palette de 5 couleur extraite de l'image sur le côté de celle-ci avec leurs codes hexadécimaux"""
        colors : List[colorgram.Color] = colorgram.extract(img, n_colors)
        image = Image.open(img).convert("RGBA")
        image = ImageOps.contain(image, (500, 500))
        iw, ih = image.size
        w, h = (iw + 100, ih)
        font = ImageFont.truetype('cogs/packages/colors/RobotoRegular.ttf', 18)   
        palette = Image.new('RGBA', (w, h), color='white')
        maxcolors = h // 30
        if len(colors) > maxcolors:
            colors = colors[:maxcolors]
        blockheight = h // len(colors)
        for i, color in enumerate(colors):
            # On veut que le dernier block occupe tout l'espace restant
            if i == len(colors) - 1:
                palette.paste(color.rgb, (iw, i * blockheight, iw + 100, h))
            else:
                palette.paste(color.rgb, (iw, i * blockheight, iw + 100, i * blockheight + blockheight))
            draw = ImageDraw.Draw(palette)
            hex_color = f'#{color.rgb[0]:02x}{color.rgb[1]:02x}{color.rgb[2]:02x}'.upper()
            if color.rgb[0] + color.rgb[1] + color.rgb[2] < 382:
                draw.text((iw + 10, i * blockheight + 10), f'{hex_color}', fill='white', font=font)
            else:
                draw.text((iw + 10, i * blockheight + 10), f'{hex_color}', fill='black', font=font)
        palette.paste(image, (0, 0))
        return palette
    
    @app_commands.command(name='palette')
    async def show_palette(self, interaction: discord.Interaction, colors: app_commands.Range[int, 3, 10] = 5, file: Optional[discord.Attachment] = None, url: Optional[str] = None, user: Optional[discord.User] = None):
        """Génère une palette de 5 couleurs (les plus dominantes) à partir d'une image. Si aucune image n'est fournie, la palette est générée à partir de la dernière image envoyée dans le salon.
        
        :param colors: Nombre de couleurs à extraire de l'image (entre 3 et 10)
        :param file: Image dont on veut extraire la palette
        :param url: URL directe d'une image dont on veut extraire la palette
        :param user: Utilisateur dont on veut extraire la palette de la photo de profil
        """
        await interaction.response.defer()
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread, discord.DMChannel, discord.GroupChannel)):
            return await interaction.response.send_message("**Erreur · ** Vous ne pouvez pas utiliser cette commande ici.", ephemeral=True)
        if file:
            img = BytesIO(await file.read())
            palette = self.draw_image_palette(img, colors)
        else:
            if user:
                url = user.display_avatar.url
                
            if not url:
                async for message in interaction.channel.history(limit=30):
                    if message.attachments:
                        type = message.attachments[0].content_type
                        if type not in ['image/png', 'image/jpeg', 'image/gif']:
                            continue
                        url = message.attachments[0].url
                        break
                else:
                    return await interaction.response.send_message("**Erreur · ** Aucune image valable n'a été trouvée dans l'historique récent de ce salon.", ephemeral=True)
                
            with requests.get(url) as r:
                if r.status_code != 200:
                    return await interaction.response.send_message("**Erreur · ** L'image n'a pas pu être téléchargée. Vérifiez que l'URL est correcte et que l'image n'est pas trop volumineuse (max. 8 Mo).", ephemeral=True)
                elif not r.headers.get('content-type').startswith('image'):
                    return await interaction.response.send_message("**Erreur · ** L'URL donnée ne pointe pas vers une image.", ephemeral=True)
                elif len(r.content) > 8388608:
                    return await interaction.response.send_message("**Erreur · ** L'image est trop volumineuse (max. 8 Mo).", ephemeral=True)
                img = BytesIO(r.content)
                
            palette = self.draw_image_palette(img, colors)
        
        if not palette:
            return await interaction.response.send_message("**Erreur · ** Une erreur s'est produite lors de la génération de la palette.", ephemeral=True)
        
        with BytesIO() as f:
            palette.save(f, 'PNG')
            f.seek(0)
            palette = discord.File(f, filename='palette.png', description='Palette de couleurs extraite de l\'image')
            await interaction.followup.send(file=palette)
        
        
async def setup(bot):
    await bot.add_cog(Colors(bot))