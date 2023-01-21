from datetime import datetime
import logging
import random
from io import BytesIO
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from tinydb import Query

from common.dataio import get_package_path, get_tinydb_database

logger = logging.getLogger('nero.Quotes')

FONTS = [
    'Roboto-Regular.ttf',
    'BebasNeue-Regular.ttf',
    'Minecraftia-Regular.ttf',
    'coolvetica rg.otf',
    'OldLondon.ttf',
]
FONT_CHOICES = [
    Choice(name="Roboto", value="Roboto-Regular.ttf"),
    Choice(name="Bebas Neue", value="BebasNeue-Regular.ttf"),
    Choice(name="Minecraftia", value="Minecraftia-Regular.ttf"),
    Choice(name="Coolvetica", value="coolvetica rg.otf"),
    Choice(name="Old London", value="OldLondon.ttf"),
]


class QuoteView(discord.ui.View):
    def __init__(self, quote_url: str, interaction: discord.Interaction):
        super().__init__(timeout=600)
        self.quote_url = quote_url
        self.interaction = interaction
        
    @discord.ui.button(label="Sauvegarder", style=discord.ButtonStyle.success)
    async def save_quote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sauvegarder la citation"""
        db = get_tinydb_database('quotes')
        user = interaction.user
        User = Query()
        current_quotes = db.search(User.uid == user.id)
        msg = "**Citation enregistrée dans vos favoris !**\nConsultez-les avec `/myquotes`."
        if current_quotes:
            quotes = current_quotes[0]['quotes']
            if self.quote_url not in quotes:
                quotes.append(self.quote_url)
                db.update({'quotes': quotes}, User.uid == user.id)
            else:
                msg = "**Impossible d'enregistrer cette citation**\nElle se trouve déjà dans tes favoris !"
        else:
            db.insert({'uid': user.id, 'quotes': [self.quote_url]})
        
        await interaction.response.send_message(msg, ephemeral=True)
        
    async def on_timeout(self) -> None:
        await self.interaction.edit_original_response(view=None)


class MyQuotesView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, initial_position: int = 0):
        super().__init__(timeout=300)
        self.initial_interaction = interaction
        self.user = interaction.user
        
        db = get_tinydb_database('quotes')
        User = Query()
        inv = db.search(User.uid == self.user.id)
        self.inventory = inv[0]['quotes'] if inv else []
        self.inv_position = initial_position if 0 <= initial_position < len(self.inventory) else 0
        
        if initial_position <= 0:
            self.previous.disabled = True
        elif initial_position >= len(self.inventory) - 1:
            self.next.disabled = True
        
        self.message : discord.InteractionMessage = None
        
        
    async def interaction_check(self, interaction: discord.Interaction):
        is_author = interaction.user.id == self.initial_interaction.user.id
        if not is_author:
            await interaction.response.send_message(
                "L'auteur de la commande est le seul à pouvoir consulter son inventaire.",
                ephemeral=True,
            )
        return is_author
    
    async def on_timeout(self) -> None:
        await self.message.edit(view=self.clear_items())
        
    def embed_quote(self, position: int):
        em = discord.Embed(color=0x2F3136)
        em.set_footer(text=f"{position + 1}/{len(self.inventory)}", icon_url=self.user.display_avatar.url)
        em.set_image(url=self.inventory[position])
        return em
    
    async def start(self):
        if self.inventory:
            await self.initial_interaction.response.send_message(embed=self.embed_quote(self.inv_position), view=self)
        else:
            await self.initial_interaction.response.send_message("Votre inventaire est vide ! Pour y ajouter des citations, cliquez sur `Sauvegarder` lorsqu'une citation est générée.")
            self.stop()
            return self.clear_items()
        self.message = await self.initial_interaction.original_response()
        
    async def buttons_logic(self, interaction: discord.Interaction):
        self.previous.disabled = self.inv_position == 0
        self.next.disabled = self.inv_position + 1 >= len(self.inventory)
        await interaction.message.edit(view=self)
        
    @discord.ui.button(label="Précédent", style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Previous button"""
        self.inv_position = max(0, self.inv_position - 1)
        await self.buttons_logic(interaction)
        await interaction.response.edit_message(embed=self.embed_quote(self.inv_position))

    @discord.ui.button(label="Suivant", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Next button"""
        self.inv_position = min(len(self.inventory) - 1, self.inv_position + 1)
        await self.buttons_logic(interaction)
        await interaction.response.edit_message(embed=self.embed_quote(self.inv_position))
        
    @discord.ui.button(label="Retirer", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete button"""
        db = get_tinydb_database('quotes')
        user = interaction.user
        User = Query()
        current_quotes = db.search(User.uid == user.id)
        displayed = self.inventory[self.inv_position]
        if current_quotes:
            quotes = current_quotes[0]['quotes']
            quotes.remove(displayed)
            db.update({'quotes': quotes}, User.uid == user.id)
        else:
            db.insert({'uid': user.id, 'quotes': [self.quote_url]})
        
        await interaction.response.send_message(f"La citation **n°{self.inv_position + 1}** a été retirée avec succès de vos favoris.", ephemeral=True)
        self.inv_position = self.inv_position - 1 if self.inv_position > 0 else 0
        self.inventory = quotes
        
        await self.buttons_logic(interaction)
        await self.message.edit(embed=self.embed_quote(self.inv_position))
    
    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.primary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close"""
        self.stop()
        await self.message.delete()


class Quotes(commands.Cog):
    """Citations Inspirobot et bien plus"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.context_menu = app_commands.ContextMenu(
            name='Quotifier',
            callback=self.ctx_quotify_message
        )
        self.bot.tree.add_command(self.context_menu)
    
    def quote_cooldown(interaction: discord.Interaction):
        if interaction.user.id == 172376505354158080:
            return None
        return app_commands.Cooldown(1, 600)
        
    @app_commands.command(name='quote')
    @app_commands.checks.dynamic_cooldown(quote_cooldown)
    async def quote(self, interaction: discord.Interaction):
        """Obtenir une quote générée depuis Inspirobot.me"""
        await interaction.response.defer(thinking=True)
    
        async def fetch_inspirobot_quote():
            async with aiohttp.ClientSession() as session:
                async with session.get("http://inspirobot.me/api?generate=true") as page:
                    return await page.text()
    
        img = await fetch_inspirobot_quote()
        if not img:
            return await interaction.followup.send("Impossible d'obtenir une image depuis Inspirobot.me", ephemeral=True)
        
        em = discord.Embed(color=0x2F3136)
        em.set_image(url=img)
        em.set_footer(text="Généré par Inspirobot.me")
        await interaction.followup.send(embed=em, view=QuoteView(img, interaction))
        
    @app_commands.command(name='myquotes')
    async def myquotes(self, interaction: discord.Interaction, position: Optional[int] = 0):
        """Voir votre inventaire de citations favorites

        :param position: Commencer le défilement par la citation n°<position> dans votre inventaire
        """
        await MyQuotesView(interaction, position).start()
        
    @app_commands.command(name='quotify')
    @app_commands.choices(font=FONT_CHOICES)
    async def custom_quote(self, interaction: discord.Interaction, message_id: str, font: Optional[str] = None):
        """Permet de créer une citation imagée personnalisée depuis le message de votre choix

        :param font: Police de caractères à utiliser (si non spécifié, une police aléatoire sera choisie)
        :param message_id: ID du message à quotifier
        """
        message_id = int(message_id) if message_id.isdigit() else message_id
        try:
            message : discord.Message = await interaction.channel.fetch_message(message_id)
        except discord.NotFound:
            return await interaction.response.send_message("Impossible de trouver le message demandé.", ephemeral=True)
        except discord.HTTPException:
            return await interaction.response.send_message("Une erreur est survenue.", ephemeral=True)
        try:
            await interaction.response.send_message(file=await self.alternate_quotify_message(message, font))
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        
    async def alternate_quotify_message(self, message: discord.Message, fontname: str = None) -> discord.File:
        x1 = 512
        y1 = 512
        if not fontname:
            fontname = random.choice(FONTS)
        font = get_package_path('quotes') + f"/{fontname}"
        sentence = f"“{message.clean_content}”" if fontname in ["BebasNeue-Regular.ttf", "coolvetica rg.otf"] else f"\"{message.clean_content}\""
        if len(sentence) > 200:
            raise commands.BadArgument("Le message est trop long.")
        author_sentence = f"{message.author.name}, {datetime.now().year}"

        basebg = Image.new('RGBA', (x1, y1), (0, 0, 0, 0))
        userpfp = await message.author.display_avatar.read()
        userbg = Image.open(BytesIO(userpfp))
        userbg = userbg.resize((x1, y1)).convert('RGBA')
        background = Image.alpha_composite(basebg, userbg)
        gradient = Image.new('RGBA', background.size, (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        gradient_draw.polygon([(0, 0), (0, background.height), (background.width, background.height), (background.width, 0)], fill=(0, 0, 0, 125))
        img = Image.alpha_composite(background, gradient)
        d = ImageDraw.Draw(img)
        
        fontfile = ImageFont.truetype(font, 36)
        author_fontfile = ImageFont.truetype(font, 26)

        sum = 0
        for letter in sentence:
            sum += d.textsize(letter, font=fontfile)[0]

        average_length_of_letter = sum/len(sentence)

        number_of_letters_for_each_line = (x1/1.618)/average_length_of_letter
        incrementer = 0
        fresh_sentence = ''

        for letter in sentence:
            if (letter == '-'):
                fresh_sentence += '\n\n' + letter
            elif (incrementer < number_of_letters_for_each_line):
                fresh_sentence += letter
            else:
                if (letter == ' '):
                    fresh_sentence += '\n'
                    incrementer = 0
                else:
                    fresh_sentence += letter
            incrementer += 1

        dim = d.textsize(fresh_sentence, font=fontfile)
        authdim = d.textsize(author_sentence, font=author_fontfile)
        x2 = dim[0]
        y2 = dim[1]
        x3 = authdim[0]

        qx = (x1/2 - x2/2)
        qy = (y1/2-y2/2)

        d.text((qx, qy), fresh_sentence, align="center", font=fontfile, fill=(255, 255, 255, 255))
        d.text((x1 / 2 - (x3 / 2), qy + y2 + 4), author_sentence, align="center", font=author_fontfile, fill=(255, 255, 255, 255))
        out = img.convert('RGB')
        out = out.resize((512, 512))
        with BytesIO() as buffer:
            out.save(buffer, format='PNG')
            buffer.seek(0)
            return discord.File(buffer, filename=f'quote_{message.id}.png')
        
    async def ctx_quotify_message(self, interaction: discord.Interaction, message: discord.Message):
        """Menu contextuel permettant de transformer un message en citation imagée"""
        try:
            await interaction.response.send_message(file=await self.alternate_quotify_message(message, fontname='BebasNeue-Regular.ttf'))
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    # async def quotify_message(self, message: discord.Message, font: str = None) -> discord.File:
    #     """Crée une citation imagée à partir d'un message
    #     """
    #     backgroundraw = await message.author.display_avatar.with_size(512).read()
    #     background = Image.open(BytesIO(backgroundraw))
    #     background = background.convert('RGBA')
    #     txtfront = Image.new('RGBA', background.size, (255, 255, 255, 0))
    #     if not font:
    #         font = random.choice(FONTS)
    #     text = f"“{message.clean_content}”"
    #     authortxt = f"— {message.author.display_name}"
        
    #     # Ajouter un gradient transparent sur l'image de façon à ce que le texte soit plus lisible
    #     gradient = Image.new('RGBA', background.size, (0, 0, 0, 0))
    #     gradient_draw = ImageDraw.Draw(gradient)
    #     gradient_draw.polygon([(0, 0), (0, background.height), (background.width, background.height), (background.width, 0)], fill=(0, 0, 0, 150))
    #     background = Image.alpha_composite(background, gradient)
        
        
    #     font_size = 70
    #     while True:
    #         fontfile = ImageFont.truetype(get_package_path('quotes') + f"/{font}", font_size)
    #         textwidth, textheight = fontfile.getsize(text)
    #         if textwidth < background.width and textheight < background.height:
    #             break
    #         font_size -= 2
            
    #     author_font_size = font_size // 2
    #     while True:
    #         fontfile = ImageFont.truetype(get_package_path('quotes') + f"/{font}", author_font_size)
    #         textwidth, textheight = fontfile.getsize(authortxt)
    #         if textwidth < background.width and textheight < background.height:
    #             break
    #         author_font_size -= 1
            
    #     # Ajouter authortxt en dessous de text aligné à droite par rapport à text
        
    #     fontfile = ImageFont.truetype(get_package_path('quotes') + f"/{font}", font_size)
    #     authorfontfile = ImageFont.truetype(get_package_path('quotes') + f"/{font}", author_font_size)
    #     text = textwrap.fill(text, width=40)
    #     textwidth, textheight = fontfile.getsize(text)
    #     textwidth_author, textheight_author = authorfontfile.getsize(authortxt)
        
    #     d = ImageDraw.Draw(txtfront)
    #     d.text(((background.width - textwidth) / 2, (background.height - textheight) / 2), text, font=fontfile, fill=(255, 255, 255), align='center')
    #     d.text(((background.width - textwidth_author) / 2, (background.height - textheight_author) / 2 + textheight), authortxt, font=authorfontfile, fill=(255, 255, 255), align='right')
        
    #     out = Image.alpha_composite(background, txtfront)
    #     out = out.convert('RGB')
    #     out = out.resize((512, 512))
    #     with BytesIO() as buffer:
    #         out.save(buffer, format='PNG')
    #         buffer.seek(0)
    #         return discord.File(buffer, filename=f'quote_{message.id}.png')
        
    async def cog_unload(self) -> None:
        self.session.close()
        
async def setup(bot):
    await bot.add_cog(Quotes(bot))
