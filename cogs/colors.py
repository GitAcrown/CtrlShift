import logging
from typing import List, Optional, Union

import discord
import requests
import colorgram
import json
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont, ImageOps

from common.dataio import get_sqlite_database, get_package_path

logger = logging.getLogger('ctrlshift.Colors')

DEFAULT_SETTINGS = {
    'beacon_id': 0 # Rôle qui sert de balise pour mettre les rôles de couleur en dessous
}

class ChooseColorMenu(discord.ui.View):
    def __init__(self, cog: 'Colors', initial_interaction: discord.Interaction, colors: List[colorgram.Color], previews: List[Image.Image]):
        super().__init__(timeout=60)
        self._cog = cog
        self.colors = colors
        
        self.previews = previews
        self.index = 0
        
        self.initial_interaction = initial_interaction
        self.result = None
        
    @property
    def color_choice(self) -> colorgram.Color:
        """Renvoie la couleur sélectionnée"""
        return self.colors[self.index]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérifie que l'utilisateur est bien le même que celui qui a lancé la commande"""
        if interaction.user != self.initial_interaction.user:
            await interaction.response.send_message("Vous n'êtes pas l'auteur de cette commande.", ephemeral=True)
            return False
        return True
    
    def get_embed(self) -> discord.Embed:
        """Renvoie l'embed de la couleur sélectionnée"""
        color = self.color_choice.rgb
        hexname = self._cog.rgb_to_hex(color)
        info = self._cog.get_color_info(hexname)
        embed = discord.Embed(title=f'{hexname.upper()}', description="Couleurs extraites de l'avatar (du serveur) demandé", color=discord.Color.from_rgb(*color))
        embed.set_thumbnail(url='attachment://color.png')
        pagenb = f'{self.index + 1}/{len(self.colors)}'
        embed.set_footer(text=f"{pagenb} · {info['name']['value']}")
        return embed
    
    async def start(self):
        """Affiche le menu de sélection de couleur"""
        with BytesIO() as f:
            self.previews[self.index].save(f, format='png')
            f.seek(0)
            await self.initial_interaction.response.send_message(embed=self.get_embed(), file=discord.File(f, 'color.png'), view=self)
            
    async def update(self):
        """Met à jour l'image de la couleur sélectionnée"""
        with BytesIO() as f:
            self.previews[self.index].save(f, format='png')
            f.seek(0)
            await self.initial_interaction.edit_original_response(embed=self.get_embed(), attachments=[discord.File(f, 'color.png')])

    @discord.ui.button(emoji="<:iconLeftArrow:1078124175631339580>", style=discord.ButtonStyle.grey)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Affiche la couleur précédente"""
        await interaction.response.defer()
        self.index -= 1
        if self.index < 0:
            self.index = len(self.colors) - 1
        await self.update()
        
    @discord.ui.button(emoji="<:iconRightArrow:1078124174352076850>", style=discord.ButtonStyle.grey)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Affiche la couleur suivante"""
        await interaction.response.defer()
        self.index += 1
        if self.index >= len(self.colors):
            self.index = 0
        await self.update()
    
    # Valider la couleur
    @discord.ui.button(label='Valider', style=discord.ButtonStyle.green, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Valide la couleur sélectionnée"""
        await interaction.response.defer()
        self.result = self.color_choice
        await self.initial_interaction.delete_original_response()
        self.stop()
        
    # Annuler
    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.red, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Annule la sélection de couleur"""
        await self.initial_interaction.delete_original_response()
        
    async def on_timeout(self) -> None:
        """Annule la sélection de couleur si le menu a expiré"""
        await self.initial_interaction.delete_original_response()
        
        
class Colors(commands.GroupCog, group_name='color', description='Gestion des rôles de couleur'):
    """Gestion des rôles de couleur"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialise la base de données"""
        self.initialize_database()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Initialise la base de données du serveur"""
        self.initialize_database(guild)
        
    def initialize_database(self, guild: Optional[discord.Guild] = None):
        guilds = [guild] if guild else self.bot.guilds
        for g in guilds:
            conn = get_sqlite_database('colors', 'g' + str(g.id))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS settings (name TINYTEXT PRIMARY KEY, value TEXT)")
            for name, value in DEFAULT_SETTINGS.items():
                cursor.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (name, value))
            conn.commit()
            cursor.close()
            conn.close()
            
    def get_guild_settings(self, guild: discord.Guild) -> dict:
        """Renvoie les paramètres du serveur"""
        conn = get_sqlite_database('colors', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM settings")
        settings = {name: json.loads(value) for name, value in cursor.fetchall()}
        cursor.close()
        conn.close()
        return settings
            
    def get_beacon_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Renvoie le rôle balise du serveur
        
        Le rôle balise sert à délimiter les rôles de couleur des autres rôles
        """
        settings = self.get_guild_settings(guild)
        if not settings['beacon_id']:
            return None
        role_id = int(settings['beacon_id'])
        return guild.get_role(role_id)
    
    def set_beacon_role(self, guild: discord.Guild, role: Optional[discord.Role]):
        """Définit le rôle balise du serveur"""
        if role is None:
            role_id = 0
        conn = get_sqlite_database('colors', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ? WHERE name = 'beacon_id'", (str(role.id),))
        conn.commit()
        cursor.close()
        conn.close()
        
        
    def normalize_color(self, color: str) -> Optional[str]:
        """Renvoie la couleur hexadécimale normalisée au format RRGGBB"""
        if color.startswith('0x'):
            color = color[2:]
        if color.startswith('#'):
            color = color[1:]
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        # Vérifier que la couleur est valide
        try:
            int(color, 16)
        except ValueError:
            return None
        return color.upper()
    
    def rgb_to_hex(self, rgb: tuple) -> str:
        """Renvoie la couleur hexadécimale à partir des valeurs RGB"""
        return f'#{"".join(f"{c:02x}" for c in rgb)}'
        
    def is_recyclable(self, role: discord.Role, request_user: Optional[discord.Member] = None) -> bool:
        """Renvoie True si le rôle n'est possédé par personne ou par le membre faisant la demande, sinon False"""
        if not role.members:
            return True
        elif request_user and role.members == [request_user]:
            return True
        return False
    
    def guild_recyclable_color_roles(self, guild: discord.Guild, request_user: Optional[discord.Member] = None) -> List[discord.Role]:
        """Renvoie la liste des rôles de couleur recyclables"""
        return [role for role in self.get_color_roles(guild) if self.is_recyclable(role, request_user)]
    
    def get_user_color_role(self, member: discord.Member) -> Optional[discord.Role]:
        """Renvoie le rôle de couleur possédé par le membre"""
        roles = [role for role in member.roles if role.name.startswith('#') and len(role.name) == 7]
        if roles:
            return roles[0]
        return None
    
    def get_all_user_color_roles(self, guild: discord.Guild) -> List[discord.Role]:
        """Renvoie la liste de tous les rôles de couleur du serveur"""
        return [role for role in self.get_color_roles(guild) if role.members]
    
    async def create_color_role(self, guild: discord.Guild, request_user: discord.Member, color: str) -> discord.Role:
        """Crée un rôle de couleur (ou en recycle un si possible) et l'ajoute au serveur"""
        color = self.normalize_color(color) #type: ignore
        if not color:
            raise commands.BadArgument('La couleur spécifiée est invalide.')
        guild_color_role = self.get_color_role(guild, color)
        if guild_color_role:
            return guild_color_role
        
        self_color = self.get_user_color_role(request_user)
        if self_color and self.is_recyclable(self_color, request_user):
            role = self_color
            await role.edit(name=f'#{color}', color=discord.Color(int(color, 16)))
        elif self.guild_recyclable_color_roles(guild, request_user):
            role = self.guild_recyclable_color_roles(guild, request_user)[0]
            await role.edit(name=f'#{color}', color=discord.Color(int(color, 16)))
        else:
            role = await guild.create_role(name=f'#{color}', color=discord.Color(int(color, 16)))
        return role
    
    async def organize_color_roles(self, guild: discord.Guild) -> bool:
        """Organise les rôles de couleur du serveur en dessous du rôle balise"""
        roles = self.get_color_roles(guild)
        if not roles:
            return False
        roles = sorted(roles, key=lambda r: r.name)
        beacon_role = self.get_beacon_role(guild)
        if not beacon_role:
            return False
        await guild.edit_role_positions({role: beacon_role.position - 1 for role in roles})
        return True
    
    def is_color_displayed(self, member: discord.Member) -> bool:
        """Renvoie True si la couleur du membre est celle de son rôle de couleur, sinon False"""
        role = self.get_user_color_role(member)
        if role and role.color == member.color:
            return True
        return False
    
    async def add_color_role(self, member: discord.Member, role: discord.Role) -> None:
        """Ajoute le rôle de couleur donné au membre"""
        await member.add_roles(role)
    
    async def delete_color_role(self, member: discord.Member) -> None:
        """Supprime le rôle de couleur du membre"""
        role = self.get_user_color_role(member)
        if role:
            await member.remove_roles(role)
        
    async def clean_guild_color_roles(self, guild: discord.Guild) -> None:
        """Supprime les rôles de couleur inutilisés du serveur"""
        for role in self.guild_recyclable_color_roles(guild):
            await role.delete()

    def get_color_role(self, guild: discord.Guild, hex_color: str) -> Optional[discord.Role]:
        """Renvoie le rôle de couleur correspondant à la couleur hexadécimale donnée"""
        name = f"#{self.normalize_color(hex_color)}"
        return discord.utils.get(guild.roles, name=name)

    def get_color_roles(self, guild: discord.Guild) -> List[discord.Role]:
        """Renvoie la liste des rôles de couleur du serveur"""
        return [role for role in guild.roles if role.name.startswith('#') and len(role.name) == 7]
    
    def create_color_block(self, color: Union[str, tuple], with_text: bool = True) -> Image.Image:
        """Renvoie un bloc de couleur"""
        path = get_package_path('colors')
        font_path = f"{path}/gg_sans.ttf"
        if isinstance(color, str):
            color = self.normalize_color(color) #type: ignore
            if not color:
                raise commands.BadArgument('La couleur spécifiée est invalide.')
            color = tuple(int(color[i:i+2], 16) for i in (0, 2, 4)) #type: ignore
        image = Image.new('RGB', (200, 200), color)
        d = ImageDraw.Draw(image)
        if with_text:
            if sum(color) < 382:
                d.text((10, 10), f"#{color}", fill=(255, 255, 255), font=ImageFont.truetype(font_path, 20))
            else:
                d.text((10, 10), f"#{color}", fill=(0, 0, 0), font=ImageFont.truetype(font_path, 20))
        return image
    
    def color_embed(self, color: str, text: str) -> discord.Embed:
        """Renvoie l'embed de la couleur donnée"""
        color = self.normalize_color(color) #type: ignore
        if not color: 
            raise commands.BadArgument('La couleur spécifiée est invalide.')
        info = self.get_color_info(color)
        embed = discord.Embed(description=text, color=discord.Color(int(color, 16)))
        if info:
            embed.set_footer(text=f"{info['name']['value']}")
        embed.set_image(url="attachment://color.png")
        return embed
    
    async def simulate_discord_display(self, user: Union[discord.User, discord.Member], name_color: tuple) -> Image.Image:
        avatar = await user.display_avatar.read()
        avatar = Image.open(BytesIO(avatar))
        avatar = avatar.resize((128, 128)).convert("RGBA")
        
        # Mettre l'avatar en cercle
        mask = Image.new("L", avatar.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + avatar.size, fill=255)
        avatar.putalpha(mask)
        avatar = avatar.resize((50, 50))
        
        images = []
        # Créer une version avec le fond foncé et une version avec le fond clair
        for v in [(54, 57, 63), (255, 255, 255)]:
            bg = Image.new("RGBA", (320, 94), v)
            bg.paste(avatar, (10, 10), avatar)
            d = ImageDraw.Draw(bg)
            avatar_font = ImageFont.truetype("cogs/packages/colors/gg_sans.ttf", 18)
            d.text((74, 14), user.display_name, font=avatar_font, fill=name_color)
        
            content_font = ImageFont.truetype("cogs/packages/colors/gg_sans_light.ttf", 14)
            text_color = (255, 255, 255) if v == (54, 57, 63) else (0, 0, 0)
            d.text((74, 40), "Ceci est une représentation simulée\nde la couleur qu'aurait votre pseudo", font=content_font, fill=text_color)
            images.append(bg)
        
        # On met les deux images une en dessous de l'autre
        full = Image.new("RGBA", (320, 188), (54, 57, 63))
        full.paste(images[0], (0, 0), images[0])
        full.paste(images[1], (0, 94), images[1])
        return full
            
    
    def get_color_info(self, color: str) -> Optional[dict]:
        """Renvoie les informations de la couleur donnée"""
        color = self.normalize_color(color) #type: ignore
        url = f"https://www.thecolorapi.com/id?hex={color}"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    
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
                    return await interaction.response.send_message("**Erreur ·** Aucune image valable n'a été trouvée dans l'historique récent de ce salon.", ephemeral=True)
                
            with requests.get(url) as r:
                if r.status_code != 200:
                    return await interaction.response.send_message("**Erreur ·** L'image n'a pas pu être téléchargée. Vérifiez que l'URL est correcte et que l'image n'est pas trop volumineuse (max. 8 Mo).", ephemeral=True)
                elif not r.headers.get('content-type').startswith('image'):
                    return await interaction.response.send_message("**Erreur ·** L'URL donnée ne pointe pas vers une image.", ephemeral=True)
                elif len(r.content) > 8388608:
                    return await interaction.response.send_message("**Erreur ·** L'image est trop volumineuse (max. 8 Mo).", ephemeral=True)
                img = BytesIO(r.content)
                
            palette = self.draw_image_palette(img, colors)
        
        if not palette:
            return await interaction.response.send_message("**Erreur ·** Une erreur s'est produite lors de la génération de la palette.", ephemeral=True)
        
        with BytesIO() as f:
            palette.save(f, 'PNG')
            f.seek(0)
            palette = discord.File(f, filename='palette.png', description='Palette de couleurs extraite de l\'image')
            await interaction.followup.send(file=palette)
        
    @app_commands.command(name="get")
    @app_commands.guild_only()
    async def get_color(self, interaction: discord.Interaction, color: str):
        """Obtenir un rôle de la couleur donnée
        
        :param color: Code hexadécimal de la couleur (ex. #FF0000)
        """
        member = interaction.user
        guild = interaction.guild
        if not isinstance(member, discord.Member) or not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        # Vérifier si la couleur est valide
        
        await interaction.response.defer()
        color = self.normalize_color(color) #type: ignore
        if not color:
            return await interaction.followup.send("**Erreur ·** Le code hexadécimal de la couleur est invalide.", ephemeral=True)
        
        role = await self.create_color_role(guild, member, color)
        if not role:
            return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors de la création du rôle.", ephemeral=True)

        await self.organize_color_roles(guild)

        if role not in member.roles:
            self_color_role = self.get_user_color_role(member)
            if self_color_role:
                try:
                    await member.remove_roles(self_color_role)
                except discord.Forbidden:
                    return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de vous retirer le rôle **{}**.".format(self_color_role.name), ephemeral=True)
                except discord.HTTPException:
                    return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors du retrait du rôle **{}**.".format(self_color_role.name), ephemeral=True)

            try:
                await member.add_roles(role)
            except discord.Forbidden:
                return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de vous attribuer ce rôle.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors de l'attribution du rôle.", ephemeral=True)
            
        warning = ""
        if not self.is_color_displayed(member):
            warning = "Un autre rôle coloré est plus haut dans la hiérarchie de vos rôles. Vous ne verrez pas la couleur de ce rôle tant que vous ne le retirerez pas."
            
        image = self.create_color_block(color, False)
        embed = self.color_embed(color, "Vous avez désormais le rôle **{}**{}".format(role.name, '\n\n' + warning if warning else ''))
        with BytesIO() as f:
            image.save(f, 'PNG')
            f.seek(0)
            image = discord.File(f, filename='color.png', description=f'Bloc de couleur #{color}')
            await interaction.followup.send(file=image, embed=embed)

    @app_commands.command(name="remove")
    @app_commands.guild_only()
    async def remove_color(self, interaction: discord.Interaction):
        """Retire votre rôle de couleur sur ce serveur"""
        member = interaction.user
        guild = interaction.guild
        if not isinstance(member, discord.Member) or not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        await interaction.response.defer()
        roles = self.get_all_user_color_roles(member)
        if not roles:
            return await interaction.followup.send("**Erreur ·** Vous n'avez pas de rôle de couleur.", ephemeral=True)
        
        for role in roles:
            try:
                await member.remove_roles(role)
            except discord.Forbidden:
                return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de vous retirer ce rôle.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors du retrait du rôle.", ephemeral=True)
        
        if len(role.members) == 0:
            try:
                await role.delete()
            except discord.Forbidden:
                return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de supprimer ce rôle.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors de la suppression du rôle.", ephemeral=True)
        
        await interaction.followup.send("**Succès · ** Vous n'avez plus le rôle **{}**.".format(role.name))

    @app_commands.command(name="list")
    @app_commands.guild_only()
    async def list_colors(self, interaction: discord.Interaction):
        """Liste les rôles de couleurs sur ce serveur"""
        guild = interaction.guild
        if not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        await interaction.response.defer()
        roles = self.get_color_roles(guild)
        if not roles:
            return await interaction.followup.send("**Erreur ·** Aucun rôle de couleur n'a été trouvé sur ce serveur.", ephemeral=True)
        
        rolelist = []
        for role in roles:
            rolelist.append((role.name, len(role.members)))
        rolelist.sort(key=lambda x: x[1], reverse=True)
        
        text = tabulate(rolelist, headers=['Nom', 'Nb. de membres'], tablefmt='plain')
        
        embed = discord.Embed(title="Rôles de couleurs", description=f"```{text}```")
        embed.set_footer(text="Les rôles de couleurs sont automatiquement supprimés lorsqu'ils ne sont plus attribués à aucun membre.")

        await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="avatar")
    @app_commands.guild_only()
    async def avatar_color(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Attribue un rôle de couleur en fonction d'un avatar
        
        :param member: Membre dont vous voulez obtenir la couleur d'avatar (optionnel)
        """
        member = member or interaction.user # type: ignore
        request = interaction.user
        guild = interaction.guild
        if not isinstance(request, discord.Member) or not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        avatar = await member.display_avatar.read()
        avatar = Image.open(BytesIO(avatar))
        colors = colorgram.extract(avatar, 5)
        previews = []
        for color in colors:
            previews.append(await self.simulate_discord_display(member, color.rgb)) # type: ignore
        view = ChooseColorMenu(self, interaction, colors, previews)
        await view.start()
        await view.wait()
        if not view.result:
            return await interaction.response.send_message("**Annulée ·** Aucune couleur n'a été choisie.", ephemeral=True, delete_after=10)

        color = self.rgb_to_hex(view.result.rgb)
        role = await self.create_color_role(guild, request, color)
        if not role:
            return await interaction.response.send_message("**Erreur ·** Une erreur s'est produite lors de la création du rôle.", ephemeral=True)

        await self.organize_color_roles(guild)

        if role not in request.roles:
            self_color_role = self.get_user_color_role(request)
            if self_color_role:
                try:
                    await request.remove_roles(self_color_role)
                except discord.Forbidden:
                    return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de vous retirer le rôle **{}**.".format(self_color_role.name), ephemeral=True)
                except discord.HTTPException:
                    return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors du retrait du rôle **{}**.".format(self_color_role.name), ephemeral=True)

            try:
                await request.add_roles(role)
            except discord.Forbidden:
                return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de vous attribuer ce rôle.", ephemeral=True)
            except discord.HTTPException:
                return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors de l'attribution du rôle.", ephemeral=True)
            
        warning = ""
        if not self.is_color_displayed(request):
            warning = "Un autre rôle coloré est plus haut dans la hiérarchie de vos rôles. Vous ne verrez pas la couleur de ce rôle tant que vous ne le retirerez pas."
            
        image = self.create_color_block(color, False)
        embed = self.color_embed(color, "Vous avez désormais le rôle **{}**{}".format(role.name, '\n\n' + warning if warning else ''))
        with BytesIO() as f:
            image.save(f, 'PNG')
            f.seek(0)
            image = discord.File(f, filename='color.png', description=f'Bloc de couleur #{color}')
            await interaction.followup.send(file=image, embed=embed)

    @app_commands.command(name="clear")
    @app_commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def clear_colors(self, interaction: discord.Interaction):
        """Efface tous les rôles qui ne sont pas attribués à un membre"""
        guild = interaction.guild
        if not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        await interaction.response.defer()
        roles = self.get_color_roles(guild)
        if not roles:
            return await interaction.followup.send("**Erreur ·** Aucun rôle de couleur n'a été trouvé sur ce serveur.", ephemeral=True)
        
        deleted = 0
        for role in roles:
            if len(role.members) == 0:
                try:
                    await role.delete()
                except discord.Forbidden:
                    return await interaction.followup.send("**Erreur ·** Je n'ai pas la permission de supprimer le rôle **{}**.".format(role.name), ephemeral=True)
                except discord.HTTPException:
                    return await interaction.followup.send("**Erreur ·** Une erreur s'est produite lors de la suppression du rôle **{}**.".format(role.name), ephemeral=True)
                deleted += 1
                
        # Faire du rangement
        await self.organize_color_roles(guild)
        
        if deleted == 0:
            return await interaction.followup.send("**Succès ·** Aucun rôle n'a été supprimé.", ephemeral=True)
        
        await interaction.followup.send("**Succès ·** {} rôles ont été supprimés.".format(deleted))
        
    @app_commands.command(name="setbeacon")
    @app_commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def set_beacon(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        """Définir un rôle comme étant un rôle de couleur de balise permettant d'organiser dans la liste des rôles les rôles de couleur
        
        :param role: Rôle à définir comme rôle de couleur de balise, ou aucun pour désactiver
        """
        guild = interaction.guild
        if not isinstance(guild, discord.Guild):
            return await interaction.response.send_message("**Erreur ·** Vous devez être membre d'un serveur pour utiliser cette commande.", ephemeral=True)
        
        if not role:
            self.set_beacon_role(guild, None)
            return await interaction.response.send_message("**Succès ·** Le rôle de balise a été désactivé.", ephemeral=True)
        
        self.set_beacon_role(guild, role)
        await interaction.response.send_message("**Succès ·** Le rôle **{}** sert désormais de balise.".format(role.name), ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(Colors(bot))