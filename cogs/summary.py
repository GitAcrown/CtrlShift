import discord
import logging
from datetime import datetime
import operator
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands, tasks
from typing import Optional
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
        
class Summary(commands.Cog):
    """Commandes pour résumer des textes"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        self.context_menu = app_commands.ContextMenu(
            name='Résumer',
            callback=self.ctx_summarize_message
        )
        self.bot.tree.add_command(self.context_menu)
    
    def summarize_url(self, url: str, language: str, sentences_count: int = 5):
        parser = HtmlParser.from_url(url, Tokenizer(language))
        stemmer = Stemmer(language)
        summarizer = Summarizer(stemmer) # type: ignore
        summarizer.stop_words = get_stop_words(language)
        return summarizer(parser.document, sentences_count)
    
    def summarize_text(self, text: str, language: str, sentences_count: int = 5):
        parser = PlaintextParser.from_string(text, Tokenizer(language))
        stemmer = Stemmer(language)
        summarizer = Summarizer(stemmer) # type: ignore
        summarizer.stop_words = get_stop_words(language)
        return summarizer(parser.document, sentences_count)
    
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
            sentences = self.summarize_url(url, language, sentences_count)
        elif text is not None:
            sentences = self.summarize_text(text, language, sentences_count)
        else:
            return await interaction.response.send_message("Veuillez fournir soit un texte, soit une URL", ephemeral=True)
        resp = ' '.join(map(str, sentences))
        desc = f"**Résumé de <{url}>**" + f"\n> *{resp}*" if url else f"**Résumé du texte :**" + f"\n> *{resp}*"
        em = discord.Embed(description=desc, color=0x2F3136)
        em.set_footer(text=f"{interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=em)
        
    @summarize_command.autocomplete('language')
    async def summarize_command_language_autocomplete(self, interaction: discord.Interaction, current: str):
        search = fuzzy.finder(current, sorted(SUPPORTED_LANGUAGES), key=lambda t: t)
        return [app_commands.Choice(name=value.capitalize(), value=value) for value in search][:10]
        
    async def ctx_summarize_message(self, interaction: discord.Interaction, message: discord.Message):
        """Résume un message depuis un texte ou une URL"""
        view = ChooseLanguageView(self, interaction)
        await interaction.response.send_message("Indiquez la langue du contenu à résumer :", view=view)
        await view.wait()
        lang = view.current_language
        
        url = re.findall(r'(https?://[^\s]+)', message.content)
        if url:
            sentences = self.summarize_url(url[0], lang, 5)
        elif len(message.content) > 100:
            sentences = self.summarize_text(message.content, lang, 5)
        else:
            return await interaction.response.send_message("Le message ne contient pas d'URL ou de texte suffisamment long pour avoir besoin d'être résumé", ephemeral=True)

        resp = ' '.join(map(str, sentences))
        desc = f"**Résumé de <{url[0]}>**" + f"\n> *{resp}*" if url else f"**Résumé du texte :**" + f"\n> *{resp}*"
        em = discord.Embed(description=desc, color=0x2F3136)
        em.set_footer(text=f"{interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.edit_original_response(content='', embed=em)
        
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Summary(bot))