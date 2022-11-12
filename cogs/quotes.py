from typing import Optional

import discord
import platform
import asyncio
import logging
import aiohttp
from discord import app_commands
from discord.ext import commands
from tinydb import Query

from common.dataio import get_database

logger = logging.getLogger('galba.Quotes')

class QuoteView(discord.ui.View):
    def __init__(self, quote_url: str, interaction: discord.Interaction):
        super().__init__(timeout=120)
        self.quote_url = quote_url
        self.interaction = interaction
        
    @discord.ui.button(label="Sauvegarder", style=discord.ButtonStyle.success)
    async def save_quote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Sauvegarder la citation"""
        db = get_database('quotes')
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
        
        db = get_database('quotes')
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
        db = get_database('quotes')
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
        
    async def cog_unload(self) -> None:
        self.session.close()
        
async def setup(bot):
    await bot.add_cog(Quotes(bot))
