import discord
import logging
from datetime import datetime
import sqlite3
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List
import re
import json

from sumy.parsers.html import HtmlParser
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as Summarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words

import nltk

from common.dataio import get_sqlite_database
from common.utils import fuzzy

logger = logging.getLogger('ctrlshift.Summary')

SUPPORTED_LANGUAGES = [
    'hungarian',
    'swedish',
    'kazakh',
    'norwegian',
    'finnish',
    'arabic',
    'indonesian',
    'portuguese',
    'turkish',
    'azerbaijani',
    'slovene',
    'spanish',
    'danish',
    'nepali',
    'romanian',
    'greek',
    'dutch',
    'tajik',
    'german',
    'english',
    'russian',
    'french',
    'italian'
    ]

SUMMARY_IGNORED_DOMAINS = [
    'tiktok.com',
    'twitter.com'
]

class ChooseLanguageView(discord.ui.View):
    def __init__(self, cog: 'Summary', initial_interaction: discord.Interaction, *, timeout: Optional[float] = 180):
        super().__init__(timeout=timeout)
        self._cog = cog
        self.initial_interaction = initial_interaction
        self.current_language = 'french'
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.initial_interaction.user.id:
            await interaction.response.send_message("Vous n'êtes pas le créateur de cette commande", ephemeral=True)
            return False
        return True
    
    @discord.ui.select(options=[discord.SelectOption(label=lang.capitalize(), value=lang) for lang in sorted(SUPPORTED_LANGUAGES)], placeholder="Choissez une langue")
    async def choose_language(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.current_language = select.values[0]
        await interaction.response.edit_message(view=None)
        self.stop()
        
class URLNavigation(discord.ui.View):
    def __init__(self, data: List[dict], initial_interaction: discord.Interaction, search_term: Optional[str] = None):
        super().__init__(timeout=60)
        self.data = data
        self.initial_interaction = initial_interaction
        self.guild = initial_interaction.guild
        self.search_term = search_term
        self.message : Optional[discord.Message] = None
        
        self.pages = self.generate_pages()
        self.current_index = 0
        self.buttons_logic()
    
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.initial_interaction.user.id:
            await interaction.response.send_message("Vous n'êtes pas le créateur de cette commande", ephemeral=True)
            return False
        return True
    
    def generate_pages(self):
        pages = []
        for i in range(len(self.data)):
            pages.append(self.get_page_embed(i))
        return pages
    
    def get_page_embed(self, index: int) -> discord.Embed:
        url_data = self.data[index]
        summary = f">>> *{url_data['summary']}*"[:2048]
        first_post = json.loads(url_data['post_history'])[0]
        embed = discord.Embed(title=url_data['url'], description=summary, color=0x2F3136, timestamp=datetime.fromtimestamp(first_post['timestamp']))
        if self.search_term:
            embed.set_footer(text=f"Page {index+1}/{len(self.data)} · Contenant «{self.search_term}»")
        else:
            embed.set_footer(text=f"Page {index+1}/{len(self.data)}")
        author = self.guild.get_member(first_post['author_id'])
        if author:
            embed.set_author(name=author.display_name, icon_url=author.avatar.url)
            
        msg_txt = []
        for post in json.loads(url_data['post_history'])[-5:]:
            msg_txt.append(f"• <t:{int(post['timestamp'])}:R> [Message de {self.guild.get_member(post['author_id']).mention if self.guild.get_member(post['author_id']) else '**Inconnu.e**'}]({post['message_link']} 'Aller au message')")
        embed.add_field(name="Derniers messages", value="\n".join(msg_txt), inline=False)
        return embed
    
    async def start(self):
        self.message = await self.initial_interaction.followup.send(embed=self.pages[0], view=self)
    
    async def on_timeout(self):
        await self.message.edit(view=None)
        
    def buttons_logic(self):
        self.previous_page.disabled = self.current_index == 0
        self.next_page.disabled = self.current_index == len(self.pages)-1
        
    @discord.ui.button(label='Lien précédent', style=discord.ButtonStyle.grey)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index == 0:
            return
        self.current_index -= 1
        self.buttons_logic()
        await interaction.response.edit_message(embed=self.pages[self.current_index], view=self)
    
    @discord.ui.button(label='Lien suivant', style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index == len(self.pages)-1:
            return
        self.current_index += 1
        self.buttons_logic()
        await interaction.response.edit_message(embed=self.pages[self.current_index], view=self)
    
    @discord.ui.button(label='Fermer', style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.stop()
    
        
class Summary(commands.Cog):
    """Commandes pour résumer des textes"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        self.context_menu = app_commands.ContextMenu(
            name='Résumer',
            callback=self.ctx_summarize_message
        )
        self.bot.tree.add_command(self.context_menu)
        
    @commands.Cog.listener()
    async def on_ready(self):
        self._initialize_database()
        
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self._initialize_database(guild)
        
    def _initialize_database(self, guild: Optional[discord.Guild] = None):
        initguilds = [guild] if guild else self.bot.guilds
        for g in initguilds:
            conn = get_sqlite_database('summary', f'g{g.id}')
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS links (url TEXT PRIMARY KEY, summary TEXT, post_history MEDIUMTEXT)")
            conn.commit()
            cursor.close()
            conn.close()
    
    # Données
    
    def get_url_data(self, guild: discord.Guild, url: str) -> Optional[dict]:
        conn = get_sqlite_database('summary', f'g{guild.id}')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM links WHERE url = ?", (url,))
        data = cursor.fetchone()
        cursor.close()
        conn.close()
        return {'url': data[0], 'summary': data[1], 'post_history': json.loads(data[2])} if data else None
    
    def set_url_data(self, guild: discord.Guild, url: str, summary: str, message: discord.Message):
        current_data = self.get_url_data(guild, url)
        if current_data:
            post_history = current_data['post_history']
        else:
            post_history = []
        post_history.append({'message_link': message.jump_url, 'author_id': message.author.id, 'timestamp': message.created_at.timestamp()})
        conn = get_sqlite_database('summary', f'g{guild.id}')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO links VALUES (?, ?, ?)", (url, summary, json.dumps(post_history)))
        conn.commit()
        cursor.close()
        conn.close()
        
    def update_url_summary(self, guild: discord.Guild, url: str, summary: str):
        conn = get_sqlite_database('summary', f'g{guild.id}')
        cursor = conn.cursor()
        cursor.execute("UPDATE links SET summary = ? WHERE url = ?", (summary, url))
        conn.commit()
        cursor.close()
        conn.close()
        
    def get_last_urls(self, guild: discord.Guild, count: int = 10) -> list:
        conn = get_sqlite_database('summary', f'g{guild.id}')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM links")
        data = cursor.fetchall()
        conn.commit()
        cursor.close()
        conn.close()
        
        data = [dict(d) for d in data]
        urls = {int(json.loads(d['post_history'])[-1]['timestamp']): d for d in data if d['post_history']}
        return [urls[t] for t in sorted(urls.keys(), reverse=True)[:count]]
    
    def search_text(self, guild: discord.Guild, text: str) -> list:
        conn = get_sqlite_database('summary', f'g{guild.id}')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM links")
        data = cursor.fetchall()
        conn.commit()
        cursor.close()
        conn.close()
        
        data = [dict(d) for d in data]
        results = []
        for d in data:
            token = d['summary'].replace('\n', '').lower() + d['url']
            if text in token:
                results.append(d)
        return results
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if not message.content:
            return
        urls = re.findall(r'(https?://[^\s]+)', message.clean_content)
        if not urls:
            return
        for url in urls:
            print(url)
            try:
                summary = self.summarize_url(url, 'french', 5)
                if summary:
                    summary = '\n'.join(map(str, summary))
                else:
                    summary = 'Résumé indisponible'
            except Exception as e:
                logger.error(f"Error while summarizing {url}: {e}")
                summary = 'Résumé indisponible'
            
            self.set_url_data(message.guild, url, summary, message)
    
    # Fonctions
    
    def summarize_url(self, url: str, language: str, sentences_count: int = 5):
        # Vérifier que l'URL est valide et que le site contient du texte
        for i in SUMMARY_IGNORED_DOMAINS:
            if i in url.lower():
                raise Exception(f"Error while fetching {url}: domain is ignored")
        
        stemmer = Stemmer(language)
        summarizer = Summarizer(stemmer) # type: ignore
        summarizer.stop_words = get_stop_words(language)

        try:
            parser = HtmlParser.from_url(url, Tokenizer(language))
            s = summarizer(parser.document, sentences_count)
        except Exception as e:
            logger.error(f"Error while summarizing {url}: {e}")
            raise e
        return s
    
    def summarize_text(self, text: str, language: str, sentences_count: int = 5):
        parser = PlaintextParser.from_string(text, Tokenizer(language))
        stemmer = Stemmer(language)
        summarizer = Summarizer(stemmer) # type: ignore
        summarizer.stop_words = get_stop_words(language)
        try:
            s = summarizer(parser.document, sentences_count)
        except Exception as e:
            logger.error(f"Error while summarizing text: {e}")
            raise e
        return s
    
    @app_commands.command(name="summarize")
    async def summarize_command(self, interaction: discord.Interaction, url: Optional[str], text: Optional[str], language: str = "french", sentences_count: app_commands.Range[int, 1, 10] = 5):
        """Résume un texte brut ou le texte extrait automatiquement d'un site web
        
        :param url: URL du site web à résumer
        :param text: Texte brut à résumer
        :param language: Langue du texte à résumer (french, english, ...)
        :param sentences_count: Nombre de phrases résumées désirées (par défaut 5)"""
        if not nltk.data.find('tokenizers/punkt'):
            nltk.download('punkt')
        if url is None and text is None:
            return await interaction.response.send_message("Veuillez fournir soit un texte, soit une URL", ephemeral=True)
        if url is not None:
            try:
                sentences = self.summarize_url(url, language, sentences_count)
            except Exception:
                sentences = [f"Résumé indisponible"]
        elif text is not None:
            sentences = self.summarize_text(text, language, sentences_count)
        else:
            return await interaction.response.send_message("Veuillez fournir soit un texte, soit une URL", ephemeral=True)
        resp = '\n'.join(map(str, sentences))
        desc = f"**Résumé de <{url}>**" + f"\n>>> *{resp}*" if url else f"__**Résumé du texte :**__" + f"\n>>> *{resp}*"
        em = discord.Embed(description=desc, color=0x2F3136)
        em.set_footer(text=f"Langue : {language.capitalize()} | Nombre de phrases : {sentences_count}")
        await interaction.response.send_message(embed=em)
        
    @summarize_command.autocomplete('language')
    async def summarize_command_language_autocomplete(self, interaction: discord.Interaction, current: str):
        search = fuzzy.finder(current, sorted(SUPPORTED_LANGUAGES), key=lambda t: t)
        return [app_commands.Choice(name=value.capitalize(), value=value) for value in search][:10]
        
    async def ctx_summarize_message(self, interaction: discord.Interaction, message: discord.Message):
        """Résume un message depuis un texte ou une URL"""
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.DMChannel, discord.GroupChannel, discord.Thread)):
            return await interaction.response.send_message("Vous devez utiliser cette commande dans un salon de discussion", ephemeral=True)
        view = ChooseLanguageView(self, interaction)
        await interaction.response.send_message("Afin d'obtenir un résumé fiable, veuillez indiquer la langue du contenu :", view=view, ephemeral=True)
        await view.wait()
        lang = view.current_language
        
        url = re.findall(r'(https?://[^\s]+)', message.content)
        if url:
            sentences = self.summarize_url(url[0], lang, 5)
        elif len(message.content) > 100:
            sentences = self.summarize_text(message.content, lang, 5)
        else:
            return await interaction.response.send_message("Le message ne contient pas d'URL ou de texte suffisamment long pour avoir besoin d'être résumé", ephemeral=True)

        if not sentences:
            resp = 'Résumé indisponible'
        else:
            resp = '\n'.join(map(str, sentences))
        desc = f"**Résumé de <{url[0]}>**" + f"\n>>> *{resp}*" if url else f"__**Résumé du texte :**__" + f"\n>>> *{resp}*"
        em = discord.Embed(description=desc, color=0x2F3136)
        em.set_footer(text=f"Langue : {lang.capitalize()} | Nombre de phrases : 5")
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Source", style=discord.ButtonStyle.gray, url=message.jump_url))
        await channel.send(embed=em, view=view)
        
    @app_commands.command(name="links")
    @app_commands.guild_only()
    async def guild_links(self, interaction: discord.Interaction, search: Optional[str]):
        """Affiche les derniers liens postés sur le serveur avec leur résumé
        
        :param search: Recherche textuelle optionnelle du contenu du résumé et/ou de l'URL"""
        await interaction.response.defer()
        if search:
            results = self.search_text(interaction.guild, search.lower()) # type: ignore
            if not results:
                return await interaction.followup.send("**Aucun résultat ·** Aucune URL ne correspond à votre recherche", ephemeral=True)
            ordered_results = sorted(results, key=lambda d: int(json.loads(d['post_history'])[-1]['timestamp']), reverse=True)[:20]
        else:
            ordered_results = self.get_last_urls(interaction.guild, 20) # type: ignore
        if not ordered_results:
            return await interaction.followup.send("**Base de données vide ·** Personne n'a encore posté d'URL depuis le début du suivi", ephemeral=True)

        await URLNavigation(ordered_results, interaction, search_term=search).start()
        
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Summary(bot))