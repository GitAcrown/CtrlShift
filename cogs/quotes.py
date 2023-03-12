from datetime import datetime
import logging
import random
import sqlite3
from io import BytesIO
from typing import Optional, Union, Tuple, List
import colorgram
import textwrap

import aiohttp
import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont
from tinydb import Query

from common.dataio import get_package_path, get_tinydb_database, get_sqlite_database
from common.utils import fuzzy

logger = logging.getLogger('ctrlshift.Quotes')

FONTS = [
    'Roboto-Regular.ttf',
    'BebasNeue-Regular.ttf',
    'NotoBebasNeue.ttf'
    'Minecraftia-Regular.ttf',
    'coolvetica rg.otf',
    'OldLondon.ttf',
]
FONT_CHOICES = [
    Choice(name="Roboto", value="Roboto-Regular.ttf"),
    Choice(name="Bebas Neue", value="BebasNeue-Regular.ttf"),
    Choice(name="Bebas Neue (avec Emojis)", value="NotoBebasNeue.ttf"),
    Choice(name="Minecraftia", value="Minecraftia-Regular.ttf"),
    Choice(name="Coolvetica", value="coolvetica rg.otf"),
    Choice(name="Old London", value="OldLondon.ttf"),
]

QUOTIFY_LOGS_STARTDATE = '23/02/2023'

class QuoteView(discord.ui.View):
    
    def __init__(self, cog: 'Quotes', quote_url: str, interaction: discord.Interaction):
        super().__init__(timeout=600)
        self._cog = cog
        self.quote_url = quote_url
        self.interaction = interaction
    
        
    @discord.ui.button(emoji='<:iconBookmark:1077963344918609980>', label="Sauvegarder", style=discord.ButtonStyle.success)
    async def save_quote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sauvegarder la citation"""
        db = get_tinydb_database('quotes')
        user = interaction.user
        User = Query()
        current_quotes = db.search(User.uid == user.id)
        msg = f"**Citation enregistrée dans vos favoris !**\nConsultez-les avec </myquotes:1040778741330231426>."
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
        
    @discord.ui.button(emoji='<:iconLeftArrow:1078124175631339580>', style=discord.ButtonStyle.secondary)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Previous button"""
        self.inv_position = max(0, self.inv_position - 1)
        await self.buttons_logic(interaction)
        await interaction.response.edit_message(embed=self.embed_quote(self.inv_position))
    
    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.primary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close"""
        self.stop()
        await self.message.delete()

    @discord.ui.button(emoji='<:iconRightArrow:1078124174352076850>', style=discord.ButtonStyle.secondary)
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
        
class SelectMsgs(discord.ui.Select):
    def __init__(self, editor: 'QuotifyEditor', placeholder: str, options: List[discord.SelectOption]):
        super().__init__(placeholder=placeholder, 
                         min_values=1, 
                         max_values=len(options), 
                         options=options)
        self.editor = editor

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.editor.selected = sorted([self.editor.original_message] + [m for m in self.editor.potential_messages if str(m.id) in self.values], key=lambda m: m.created_at)
        self.options = [discord.SelectOption(label=f"{m.created_at.strftime('%d/%m/%Y %H:%M:%S')}", value=str(m.id), description=textwrap.shorten(m.clean_content, 100, placeholder='...'), default=str(m.id) in self.values) for m in self.editor.all_messages]
        await self.editor._send_update()
        
class QuotifyEditor(discord.ui.View):
    def __init__(self, cog: 'Quotes', selected_message: discord.Message, potential_messages: List[discord.Message], *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self._cog = cog
        
        self.original_message = selected_message
        self.selected = [selected_message]
        self.potential_messages = potential_messages
        self.all_messages = sorted([selected_message] + potential_messages, key=lambda m: m.created_at)
        
        self.interaction : Optional[discord.Interaction] = None
        
        self.color_index = 1
        
        if potential_messages:
            self.select_msgs = SelectMsgs(self, "Sélectionnez les messages à fusionner", [discord.SelectOption(label=f"{m.created_at.strftime('%d/%m/%Y %H:%M:%S')}", value=str(m.id), description=textwrap.shorten(m.clean_content, 100, placeholder='...'), default=True if m == selected_message else False) for m in self.all_messages])
            self.add_item(self.select_msgs)
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._cog.bot.user.id:
            await interaction.response.send_message("Vous ne pouvez pas utiliser cet éditeur car vous n'en êtes pas l'auteur.", ephemeral=True)
            return False
        return True
        
    async def start(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            image = await self._cog.create_quote_img(self.selected, self.color_index)
        except Exception as e:
            logger.exception("Error while creating quote image", exc_info=True)
            return await interaction.followup.send(f"Une erreur est survenue dans la génération de l'image : `{e}`")
        await interaction.followup.send(view=self, file=image)
        self.interaction = interaction

    async def on_timeout(self) -> None:
        view = discord.ui.View()
        msgurl = self.selected[0].jump_url
        view.add_item(discord.ui.Button(label="Source", url=msgurl, style=discord.ButtonStyle.link))
        await self.interaction.edit_original_response(content='', view=view)
        
    async def _send_update(self):
        try:
            image = await self._cog.create_quote_img(self.selected, self.color_index)
        except Exception as e:
            return await self.interaction.edit_original_response(content=f"Une erreur est survenue dans la génération de l'image : `{e}`")
        await self.interaction.edit_original_response(view=self, attachments=[image])
        
    @discord.ui.button(label="Changer la couleur", style=discord.ButtonStyle.blurple)
    async def change_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.color_index = self.color_index + 1 if self.color_index < 2 else 0
        await self._send_update()
    
    @discord.ui.button(label="Sauvegarder et quitter", style=discord.ButtonStyle.red)
    async def save_quit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        view = discord.ui.View()
        msgurl = self.selected[0].jump_url
        view.add_item(discord.ui.Button(label="Source", url=msgurl, style=discord.ButtonStyle.link))
        await self.interaction.edit_original_response(content='', view=view)
        
class QuotifyHistoryView(discord.ui.View):
    def __init__(self, cog: 'Quotes', interaction: discord.Interaction, only_user: Optional[discord.Member] = None, order_desc: bool = True, *, timeout: Optional[float] = 90):
        super().__init__(timeout=timeout)
        self._cog = cog
        self.original_interaction = interaction
        self.only_user = only_user
        self.order_desc = order_desc
        self.message : discord.InteractionMessage = None
        
        self.current_quote_index : int = 0
        self.quotes : list = self.__get_quotes(only_user, order_desc)
    
        if self.quotes:
            self.previous.disabled = self.current_quote_index < 1
            self.previousten.disabled = self.current_quote_index < 10
            self.next.disabled = self.current_quote_index + 1 >= len(self.quotes)
            self.nextten.disabled = self.current_quote_index + 10 >= len(self.quotes)
        
    async def start(self):
        if not self.quotes:
            return await self.original_interaction.response.send_message("**Historique vide ·** Aucune citation n'a été générée pour le moment.")
        message = await self.__current_message()
        await self.original_interaction.response.send_message(embed=self.embed_quote(message), view=self)
        self.message = await self.original_interaction.original_response()
        
    async def on_timeout(self) -> None:
        await self.message.edit(view=self.clear_items())
    
    async def interaction_check(self, interaction: discord.Interaction):
        is_author = interaction.user.id == self.original_interaction.user.id
        if not is_author:
            await interaction.response.send_message(
                "Seul l'auteur de la commande peut intéragir avec le menu.",
                ephemeral=True,
            )
        return is_author
    
    async def button_logic(self):
        self.previous.disabled = self.current_quote_index < 1
        self.previousten.disabled = self.current_quote_index < 10
        self.next.disabled = self.current_quote_index + 1 >= len(self.quotes)
        self.nextten.disabled = self.current_quote_index + 10 >= len(self.quotes)
    
        
    def __get_quotes(self, user: Optional[discord.Member] = None, order_desc: bool = True) -> list:
        return self._cog.get_quote_history(self.original_interaction.guild, user, order_desc) #type: ignore
    
    async def __current_message(self) -> Optional[discord.Message]:
        message_id, channel_id = self.quotes[self.current_quote_index]
        channel = self._cog.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                msg = await channel.fetch_message(message_id)
                return msg
            except discord.NotFound:
                pass
        return None
        
    def embed_quote(self, message: Optional[discord.Message]):
        title = f"**Quotify ·** Historique"
        if self.only_user is not None:
            title += f" `user:{self.only_user.name}`"
        if self.order_desc:
            title += " `order:Desc`"
        else:
            title += " `order:Asc`"
        em = discord.Embed(title=title, color=0x2F3136)
        if not isinstance(message, discord.Message):
            em.description = "Cette citation a été supprimée et n'est plus disponible."
        elif message.attachments:
            em.description = f"<t:{int(message.created_at.timestamp())}:R> · [Source]({message.jump_url})"
            quote = message.attachments[0].url
            em.set_image(url=quote)
        else:
            em.description = "L'image de cette citation a été supprimée et n'est plus disponible."
        em.set_footer(text=f"{self.current_quote_index + 1}/{len(self.quotes)} • Historique depuis le {QUOTIFY_LOGS_STARTDATE}", icon_url=self.original_interaction.user.display_avatar.url)
        return em
    
    @discord.ui.button(emoji='<:iconLeftDoubleA:1078124171088896071>', style=discord.ButtonStyle.secondary, row=1)
    async def previousten(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Previous button x10"""
        self.current_quote_index = max(0, self.current_quote_index - 10)
        new_message = await self.__current_message()
        await self.button_logic()
        await interaction.response.edit_message(embed=self.embed_quote(new_message), view=self)

    @discord.ui.button(emoji='<:iconLeftArrow:1078124175631339580>', style=discord.ButtonStyle.blurple, row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Previous button"""
        self.current_quote_index = max(0, self.current_quote_index - 1)
        new_message = await self.__current_message()
        await self.button_logic()
        await interaction.response.edit_message(embed=self.embed_quote(new_message), view=self)
        
    @discord.ui.button(emoji='<:iconClose:1078144818703765554>', style=discord.ButtonStyle.red, row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close button"""
        await interaction.response.edit_message(embed=self.embed_quote(await self.__current_message()), view=None)
        self.stop()
    
    @discord.ui.button(emoji='<:iconRightArrow:1078124174352076850>', style=discord.ButtonStyle.blurple, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Next button"""
        self.current_quote_index = min(len(self.quotes), self.current_quote_index + 1)
        new_message = await self.__current_message()
        await self.button_logic()
        await interaction.response.edit_message(embed=self.embed_quote(new_message), view=self)
        
    @discord.ui.button(emoji='<:iconRightDoubleA:1078124173076992100>', style=discord.ButtonStyle.secondary, row=1)
    async def nextten(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Next button x10"""
        self.current_quote_index = min(len(self.quotes), self.current_quote_index + 10)
        new_message = await self.__current_message()
        await self.button_logic()
        await interaction.response.edit_message(embed=self.embed_quote(new_message), view=self)


class Quotes(commands.Cog):
    """Citations Inspirobot et bien plus"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.context_menu = app_commands.ContextMenu(
            name='Quotifier',
            callback=self.ctx_quotify_message
        )
        self.bot.tree.add_command(self.context_menu)
        
        self.quotify2 = app_commands.ContextMenu(
            name='QuoteMaker (BETA)',
            callback=self.ctx_quote_maker
        )
        self.bot.tree.add_command(self.quotify2)
        
        self.bookmark_emoji = self.bot.get_emoji(1077959551669776384)
        
    @commands.Cog.listener()
    async def on_ready(self):
        self.__initialize_database()
    
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.__initialize_database(guild)
        
    def __initialize_database(self, guild: discord.Guild = None):
        guilds = [guild] if guild else self.bot.guilds
        for guild in guilds:
            conn = get_sqlite_database('quotes', 'g' + str(guild.id))
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS history (message_id INTEGER PRIMARY KEY, channel_id INTEGER, user_id INTEGER)")
            conn.commit()
            cursor.close()
            conn.close()
    
    def save_quote(self, quote_message: discord.Message, source_user: Union[discord.User, discord.Member]):
        guild = quote_message.guild
        
        conn = get_sqlite_database('quotes', 'g' + str(guild.id))
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO history VALUES (?, ?, ?)", (quote_message.id, quote_message.channel.id, source_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_quote_history(self, guild: discord.Guild, source_user: Optional[discord.User] = None, order_desc: bool = True):
        conn = get_sqlite_database('quotes', 'g' + str(guild.id))
        cursor = conn.cursor()
        if source_user:
            cursor.execute("SELECT message_id, channel_id FROM history WHERE user_id = ?{}".format(' ORDER BY message_id DESC' if order_desc else ''), (source_user.id,))
        else:
            cursor.execute("SELECT message_id, channel_id FROM history{}".format(' ORDER BY message_id DESC' if order_desc else ''))
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result
    
    
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
        await interaction.followup.send(embed=em, view=QuoteView(self, img, interaction))
        
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
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Message original", style=discord.ButtonStyle.secondary, url=message.jump_url))
        try:
            await interaction.response.send_message(file=await self.quotify_message_img(message, font), view=view)
            intermsg = await interaction.original_response()
            if intermsg:
                self.save_quote(intermsg, message.author)
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        
    # Quotify v1 (deprecated) -----------------------------------------
        
    async def quotify_message_img(self, message: discord.Message, fontname: str = None) -> discord.File:
        x1 = 512
        y1 = 512
        if not fontname:
            fontname = random.choice(FONTS)
        font = get_package_path('quotes') + f"/{fontname}"
        sentence = f"“{message.clean_content}”" if fontname in ["BebasNeue-Regular.ttf", "NotoBebasNeue.ttf", "coolvetica rg.otf"] else f"\"{message.clean_content}\""
        if len(sentence) > 200:
            raise commands.BadArgument("Le message est trop long.")
        author_sentence = f"@{message.author.name}, {message.created_at.year}"

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
        
    # Quotify v2 ---------------------------------------------------------------
     
    def _get_quote_img(self, background: Union[str, BytesIO], text: str, author_text: str, *, 
                       gradient_color_index: int = 1, fontname: str = 'NotoBebasNeue.ttf') -> Image.Image:
        if len(text) > 500:
            raise ValueError("text must be less than 500 characters")
        if len(author_text) > 32:
            raise ValueError("author_text must be less than 32 characters")
        if gradient_color_index < 0 or gradient_color_index > 2:
            raise ValueError("gradient_color_index must be between 0 and 2")
        
        img = Image.open(background)
        w, h = (512, 512)
        bw, bh = (w - 20, h - 50)
        img = img.convert("RGBA").resize((w, h)) 
        fontfile = get_package_path('quotes') + f"/{fontname}"

        gradient_magnitude = 0.85 + 0.05 * (len(text) / 100)
        img = self._add_quote_gradient(img, gradient_magnitude, colorgram.extract(img, 3)[gradient_color_index].rgb)
        font = ImageFont.truetype(fontfile, 56, encoding='unic')
        author_font = ImageFont.truetype(fontfile, 26, encoding='unic')
        draw = ImageDraw.Draw(img)
            
        wrapwidth = int(bw / font.getlength(' ') + (0.02 * len(text)))
        wrap = textwrap.fill(text, width=wrapwidth, placeholder='…', replace_whitespace=False, max_lines=8)
        box = draw.multiline_textbbox((0, 0), wrap, font=font, align='center')
        while box[2] > bw or box[3] > bh:
            font = ImageFont.truetype(fontfile, font.size - 1)
            box = draw.multiline_textbbox((0, 0), wrap, font=font, align='center')

        draw.multiline_text((w/2, bh), wrap, font=font, align='center', fill='white', anchor='md')
        draw.text((w/2 - 7, h - 16), author_text, font=author_font, fill='white', anchor='md')
        return img

    def _add_quote_gradient(self, image: Image.Image, gradient_magnitude=1.0, color: Tuple[int, int, int]=(0, 0, 0)):
        im = image
        if im.mode != 'RGBA':
            im = im.convert('RGBA')
        width, height = im.size
        gradient = Image.new('L', (1, height), color=0xFF)
        for x in range(height):
            gradient.putpixel((0, x), int(255 * (gradient_magnitude * float(x)/(width))))
        
        alpha = gradient.resize(im.size)
        black_im = Image.new('RGBA', (width, height), color=color) # i.e. black
        black_im.putalpha(alpha)
        gradient_im = Image.alpha_composite(im, black_im)
        return gradient_im
    
    async def create_quote_img(self, messages: List[discord.Message], color_index: int) -> discord.File:
        """Crée une image de citation à partir d'un ou plusieurs message(s) (v2)"""
        messages = sorted(messages, key=lambda m: m.created_at)
        user_avatar = BytesIO(await messages[0].author.display_avatar.read())
        message_year = messages[0].created_at.strftime('%Y')
        content = ' '.join(m.clean_content for m in messages)
        try:
            image = self._get_quote_img(user_avatar, f"“{content}”", f'— {messages[0].author.name}, {message_year}', gradient_color_index=color_index)
        except ValueError as e:
            logger.error(f"Une erreur est survenue lors de la création de l'image de citation: {e}", exc_info=True)
            raise ValueError(f"Une erreur est survenue lors de la création de l'image de citation: {e}")
        with BytesIO() as buffer:
            image.save(buffer, format='PNG')
            buffer.seek(0)
            desc = f"'{content}'\n— {messages[0].author.name}, {message_year}"
            return discord.File(buffer, filename=f"quote_{'_'.join([str(m.id) for m in messages])}.png", description=desc)
        
    async def get_potential_quote_messages(self, channel: Union[discord.TextChannel, discord.Thread], message: discord.Message) -> List[discord.Message]:
        """Récupère les messages potentiels à partir du message donné"""
        potential_messages = []
        async for m in channel.history(limit=10, before=message.created_at):
            if m.author == message.author and len(potential_messages) < 5:
                potential_messages.append(m)
            else:
                break
        async for m in channel.history(limit=10, after=message.created_at):
            if m.author == message.author and len(potential_messages) < 5:
                potential_messages.append(m)
            else:
                break
        
        return sorted(potential_messages, key=lambda m: m.created_at)

        
    async def ctx_quotify_message(self, interaction: discord.Interaction, message: discord.Message):
        """Menu contextuel permettant de transformer un message en citation imagée"""
        if not message.content or message.content.isspace():
            return await interaction.response.send_message("Le message ne contient pas de texte", ephemeral=True)
        try:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Source", style=discord.ButtonStyle.secondary, url=message.jump_url))
            await interaction.response.send_message(file=await self.quotify_message_img(message, fontname='NotoBebasNeue.ttf'), view=view)
            intermsg = await interaction.original_response()
            if intermsg:
                self.save_quote(intermsg, message.author)
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            
    async def ctx_quote_maker(self, interaction: discord.Interaction, message: discord.Message):
        """Menu contextuel permettant de transformer un message en citation imagée (v2)"""
        if not message.content or message.content.isspace():
            return await interaction.response.send_message("Le message ne contient pas de texte", ephemeral=True)
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("Le message doit être dans un salon de discussion", ephemeral=True)
        try:
            potential = await self.get_potential_quote_messages(message.channel, message)
            await QuotifyEditor(self, message, potential, timeout=30).start(interaction)
            intermsg = await interaction.original_response()
            if intermsg:
                self.save_quote(intermsg, message.author)
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            
    @app_commands.command(name='qhistory')
    async def quotify_history(self, interaction: discord.Interaction, user: Optional[discord.Member] = None, order: Optional[str] = 'desc'):
        """Affiche l'historique des citations quotifiées de la plus récente à la plus ancienne
        
        :param user: Limiter l'historique aux citations quotifiées de l'utilisateur spécifié
        :param order: Choisir l'ordre d'affichage des citations (Ascendant ou Descendant des identifiants messages)"""
        order_desc = order.lower() == 'desc'
        await QuotifyHistoryView(self, interaction, user, order_desc).start()
        
    @quotify_history.autocomplete('order')
    async def autocomplete_callback(self, interaction: discord.Interaction, current: str):
        options = [('Descendant', 'desc'), ('Ascendant', 'asc')]
        stgs = fuzzy.finder(current, options, key=lambda o: o[1])
        return [app_commands.Choice(name=f'{s[0]}', value=s[1]) for s in stgs]

        
async def setup(bot):
    await bot.add_cog(Quotes(bot))
