import asyncio
import logging
import os
from typing import Optional, Literal

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s (%(name)s %(module)s) %(message)s",
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    description="General purpose bot (FR)",
    help_command=None,
    intents=intents
)
bot.config = dotenv_values('.env')


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user.name}")
    print(f"discord.py API version: {discord.__version__}")
    print("Invite : {}".format(discord.utils.oauth_url(int(bot.config["APP_ID"]), permissions=discord.Permissions(int(bot.config['PERMISSIONS_INT'])))))
    print("-------------------")

@bot.event
async def on_command_error(ctx: commands.Context, error) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        embed = discord.Embed(
            title="Trop rapide !",
            description=f"Tu pourras réutiliser la commande dans {f'{round(hours)} heures' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} secondes' if round(seconds) > 0 else ''}.",
            color=0xE02B2B
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingPermissions):
        embed = discord.Embed(
            title="Erreur !",
            description="Tu manques de ces permissions `" + ", ".join(
                error.missing_permissions) + "` pour cette commande !",
            color=0xE02B2B
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="Erreur !",
            description=str(error).capitalize(),
            color=0xE02B2B
        )
        await ctx.send(embed=embed)
        
@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.CommandOnCooldown):
        minutes, seconds = divmod(error.retry_after, 60)
        hours, minutes = divmod(minutes, 60)
        hours = hours % 24
        msg = f"**Erreur ·** Tu pourras réutiliser la commande dans {f'{round(hours)} heures' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} secondes' if round(seconds) > 0 else ''}."
        return await interaction.response.send_message(content=msg)

async def load_cogs() -> None:
    """
    The code in this function is executed whenever the bot will start.
    """
    for file in os.listdir(f"./cogs"):
        if file.endswith(".py"):
            extension = file[:-3]
            try:
                await bot.load_extension(f"cogs.{extension}")
                print(f"Loaded extension '{extension}'")
            except Exception as e:
                exception = f"{type(e).__name__}: {e}"
                print(f"Failed to load extension {extension}\n{exception}")
         

@bot.hybrid_command(name="ping", description="Renvoie un pong")
async def ping(ctx: commands.Context) -> None:
    """Ping"""
    await ctx.send(f"Pong ! (`{round(bot.latency * 1000)}ms`)")
 
@bot.command(name='appsync')
@commands.guild_only()
@commands.is_owner()
async def appsync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
    """Synchronisation des commandes localement ou globalement
    
    sync -> global sync
    sync ~ -> sync current guild
    sync * -> copies all global app commands to current guild and syncs
    sync ^ -> clears all commands from the current guild target and syncs (removes guild commands)
    sync id_1 id_2 -> syncs guilds with id 1 and 2
    """
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synchronisation de {len(synced)} commandes {'globales' if spec is None else 'au serveur actuel'} effectuée." 
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Arbre synchronisé dans {ret}/{len(guilds)}.")


asyncio.run(load_cogs())
bot.run(bot.config['TOKEN'])
