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
logger = logging.getLogger('ctrlshift.Main')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

async def main():
    bot = commands.Bot(
       command_prefix=commands.when_mentioned,
        description="Bot multifonction modulaire français, basé sur NERON",
        help_command=None,
        intents=intents 
    )
    bot.config = dotenv_values('.env')
    
    async with bot:
        print("Chargement des modules :")
        for file in os.listdir(f"./cogs"):
            if file.endswith(".py"):
                extension = file[:-3]
                try:
                    await bot.load_extension(f"cogs.{extension}")
                    print(f"- '{extension}'")
                except Exception as e:
                    exception = f"{type(e).__name__}: {e}"
                    print(f"x Erreur {extension}\n{exception}")
        print('--------------')
        
        @bot.event
        async def on_ready():
            print(f"> Logged in as {bot.user.name}")
            print(f"> discord.py API version: {discord.__version__}")
            print("> Invite : {}".format(discord.utils.oauth_url(int(bot.config["APP_ID"]), permissions=discord.Permissions(int(bot.config['PERMISSIONS_INT'])))))
            print("-------------------")
    
        @bot.tree.error
        async def on_command_error(interaction: discord.Interaction, error):
            if isinstance(error, app_commands.errors.CommandOnCooldown):
                minutes, seconds = divmod(error.retry_after, 60)
                hours, minutes = divmod(minutes, 60)
                hours = hours % 24
                msg = f"**Cooldown ·** Tu pourras réutiliser la commande dans {f'{round(hours)} heures' if round(hours) > 0 else ''} {f'{round(minutes)} minutes' if round(minutes) > 0 else ''} {f'{round(seconds)} secondes' if round(seconds) > 0 else ''}."
                return await interaction.response.send_message(content=msg, ephemeral=True)
            elif isinstance(error, app_commands.errors.MissingPermissions):
                msg = f"**Erreur ·** Tu manques des permissions `" + ", ".join(error.missing_permissions) + "` pour cette commande !"
                return await interaction.response.send_message(content=msg)
            else:
                logger.error(f'Erreur App_commands : {error}', exc_info=True)

        @bot.hybrid_command(name="ping", description="Renvoie un pong")
        async def ping(ctx: commands.Context) -> None:
            """Ping"""
            await ctx.send(f"Pong ! (`{round(bot.latency * 1000)}ms`)")
        
        @bot.command(name='sync')
        @commands.guild_only()
        @commands.is_owner()
        async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
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
            
        await bot.start(bot.config['TOKEN'])
            
if __name__ == "__main__":
    asyncio.run(main())
