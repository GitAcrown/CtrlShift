import logging
import time
import iso3166
from copy import copy
from datetime import datetime, timezone
from typing import Any, List, Optional

import discord
import requests
import json
from discord import app_commands
from discord.ext import commands
from tabulate import tabulate

from common.utils import pretty, fuzzy
from common.dataio import get_sqlite_database

logger = logging.getLogger('ctrlshift.Forecast')

DEFAULT_SETTINGS = [
    ('OWMAPIKey', '')
]

        
class Forecast(commands.GroupCog, group_name='weather', description='Commandes de prévision météo'):
    """Commandes de prévision météo"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
    @commands.Cog.listener()
    async def on_ready(self):
        self.initialize_database()
        
    def initialize_database(self):
        conn = get_sqlite_database('forecast')
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (name TINYTEXT PRIMARY KEY, value TEXT)")
        for name, default_value in DEFAULT_SETTINGS:
            cursor.execute("INSERT OR IGNORE INTO settings (name, value) VALUES (?, ?)", (name, json.dumps(default_value)))
        conn.commit()
        cursor.close()
        conn.close()
        
    def get_setting(self, name: str) -> Any:
        conn = get_sqlite_database('forecast')
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE name = ?", (name,))
        value = json.loads(cursor.fetchone()[0])
        cursor.close()
        conn.close()
        return value
    
    def get_all_settings(self) -> dict:
        conn = get_sqlite_database('forecast')
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM settings")
        values = {name: json.loads(value) for name, value in cursor.fetchall()}
        cursor.close()
        conn.close()
        return values
    
    def set_setting(self, name: str, value: Any):
        conn = get_sqlite_database('forecast')
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = ? WHERE name = ?", (json.dumps(value), name))
        conn.commit()
        cursor.close()
        conn.close()
        
    def get_all_iso_countries(self):
        return [(country.name, country.alpha2) for country in iso3166.countries]
    
    def get_iso_country(self, country_name: str):
        return iso3166.countries.get(country_name)
    
    def get_iso_country_by_alpha2(self, alpha2: str):
        return iso3166.countries.get(alpha2)
        
    def get_geocode(self, city: str, country: str = '') -> Optional[dict]:
        api_key = self.get_setting('OWMAPIKey')
        if country:
            url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},{country}&appid={api_key}"
        else:
            url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={api_key}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                return {'name': data[0]['local_names']['fr'] if 'local_names' in data[0] else data[0]['name'], 'lat': data[0]['lat'], 'lon': data[0]['lon'], 'country': data[0]['country']}
            else:
                return None
        except Exception as e:
            logger.error(e)
            return None
        
    def __weather_icon(self, icon_id: str):
        return f"https://openweathermap.org/img/wn/{icon_id}@2x.png"
        
    def get_current_weather(self, city: dict) -> Optional[dict]:
        api_key = self.get_setting('OWMAPIKey')
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={city['lat']}&lon={city['lon']}&appid={api_key}&units=metric&lang=fr"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return {'name': data['name'], 
                    'country': data['sys']['country'], 
                    'temp': data['main']['temp'], 
                    'feels_like': data['main']['feels_like'], 
                    'temp_min': data['main']['temp_min'], 
                    'temp_max': data['main']['temp_max'], 
                    'humidity': data['main']['humidity'], 
                    'pressure': data['main']['pressure'], 
                    'wind_speed': data['wind']['speed'], 
                    'wind_deg': data['wind']['deg'], 
                    'clouds': data['clouds']['all'], 
                    'weather': data['weather'][0]['description'], 
                    'weather_icon': self.__weather_icon(data['weather'][0]['icon']),
                    'sunrise': datetime.fromtimestamp(data['sys']['sunrise']),
                    'sunset': datetime.fromtimestamp(data['sys']['sunset']),
                    'updated': datetime.fromtimestamp(data['dt'])}
        else:
            return None
        
    def get_week_weather(self, city: dict) -> Optional[dict]:
        """Afficher les prévisions pour la semaine"""
        api_key = self.get_setting('OWMAPIKey')
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={city['lat']}&lon={city['lon']}&appid={api_key}&units=metric&lang=fr"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return {'name': data['city']['name'],
                    'country': data['city']['country'],
                    'list': [{'date': datetime.fromtimestamp(item['dt']),
                              'temp': item['main']['temp'],
                              'temp_min': item['main']['temp_min'],
                              'temp_max': item['main']['temp_max'],
                              'humidity': item['main']['humidity'],
                              'weather': item['weather'][0]['description'],
                              'weather_icon': self.__weather_icon(item['weather'][0]['icon'])} for item in data['list']],
                    'updated': datetime.fromtimestamp(data['list'][0]['dt'])}
        else:
            return None
        
    def determine_embed_color(self, temp: float) -> int:
        if temp < 0:
            return 0x3498DB
        elif temp < 10:
            return 0x1ABC9C
        elif temp < 20:
            return 0x2ECC55
        elif temp < 30:
            return 0xF1C40F
        else:
            return 0xE74C3C
        
    @app_commands.command(name='current')
    async def forecast_current(self, interaction: discord.Interaction, city: str, country: Optional[str] = ''):
        """Afficher les mesures météo actuelles pour une ville donnée

        :param city: Ville concernée
        :param country: Préciser le pays (si nécessaire)
        """
        if country:
            loc = self.get_geocode(city, country)
        else:
            loc = self.get_geocode(city)
        
        if loc:
            forecast = self.get_current_weather(loc)
            if forecast:
                embed = discord.Embed(title=f"**Météo actuelle** · `{forecast['name']}, {self.get_iso_country_by_alpha2(forecast['country']).name}`", 
                                      color=self.determine_embed_color(forecast['temp']),
                                      timestamp=forecast['updated'].astimezone(tz=None),
                                      description=f"**{forecast['weather'].capitalize()}**")
                embed.add_field(name="Température", value=f"__{forecast['temp']}°C__")
                embed.add_field(name="Ressenti", value=f"{forecast['feels_like']}°C")
                embed.add_field(name="Max/Min", value=f"{forecast['temp_max']}°C / {forecast['temp_min']}°C")
                embed.add_field(name="Humidité", value=f"{forecast['humidity']}%")
                embed.add_field(name="Pression", value=f"{forecast['pressure']} hPa")
                embed.add_field(name="Vitesse du vent", value=f"{forecast['wind_speed']} m/s")
                embed.add_field(name="Lever et coucher", value=f"{forecast['sunrise'].strftime('%H:%M')} / {forecast['sunset'].strftime('%H:%M')}")
                embed.add_field(name="Nuages", value=f"{forecast['clouds']}%")
                embed.set_thumbnail(url=forecast['weather_icon'])
                embed.set_footer(text="Données de OpenWeatherMap · Dernière mise à jour", 
                                 icon_url="https://openweathermap.org/themes/openweathermap/assets/img/mobile_app/android-app-top-banner.png")
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("**Erreur ·** Impossible de récupérer la météo actuelle pour cette ville.")
        else:
            await interaction.response.send_message("**Erreur ·** Cette ville n'est pas dans les données d'OpenWeatherMap.\nVérifiez l'orthographe, fournissez le pays ou essayez la grosse ville la plus proche.")
        
    @forecast_current.autocomplete('country')
    async def forecast_today_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice]:
        all_codes = self.get_all_iso_countries()
        search = fuzzy.finder(current, all_codes, key=lambda t: t[0])
        return [app_commands.Choice(name=name, value=value) for name, value in search][:10]
    
    @app_commands.command(name='week')
    async def forecast_week(self, interaction: discord.Interaction, city: str, country: Optional[str] = ''):
        """Afficher les prévisions météo pour une semaine pour une ville donnée

        :param city: Ville concernée
        :param country: Préciser le pays (si nécessaire)
        """
        if country:
            loc = self.get_geocode(city, country)
        else:
            loc = self.get_geocode(city)
        
        if loc:
            forecast = self.get_week_weather(loc)
            if forecast:
                embed = discord.Embed(title=f"**Prévisions météo J-5** · `{forecast['name']}, {self.get_iso_country_by_alpha2(forecast['country']).name}`",
                                      description="Prévisions météo pour les 5 prochains jours, toutes les 3 heures.\nLecture · `Heure Météo · Température (Min / Max) · Humidité`",
                                      color=self.determine_embed_color(forecast['list'][0]['temp']),
                                      timestamp=forecast['updated'].astimezone(tz=None))
                days = {}
                for item in forecast['list']:
                    if item['date'].strftime('%d/%m/%Y') not in days:
                        days[item['date'].strftime('%d/%m/%Y')] = []
                    days[item['date'].strftime('%d/%m/%Y')].append(item)
                
                for day in days:
                    day_txt = [f"__{item['date'].strftime('%H')}h__ **{item['weather'].capitalize()}** · {item['temp']}°C ({item['temp_min']}°C / {item['temp_max']}°C) · {item['humidity']}%" for item in days[day]]
                    embed.add_field(name=f"• {day}",
                                    value="\n".join(day_txt),
                                    inline=False)
                embed.set_footer(text="Données de OpenWeatherMap · Prochaine mise à jour", icon_url="https://openweathermap.org/themes/openweathermap/assets/img/mobile_app/android-app-top-banner.png") 
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message("**Erreur ·** Impossible de récupérer la prévision météo pour cette ville.")
        else:
            await interaction.response.send_message("**Erreur ·** Cette ville n'est pas dans les données d'OpenWeatherMap.\nVérifiez l'orthographe, fournissez le pays ou essayez la grosse ville la plus proche.")
        
    @forecast_week.autocomplete('country')
    async def forecast_today_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice]:
        all_codes = self.get_all_iso_countries()
        search = fuzzy.finder(current, all_codes, key=lambda t: t[0])
        return [app_commands.Choice(name=name, value=value) for name, value in search][:10]
    
    
    @commands.command(name='forecastset')
    @commands.is_owner()
    async def set_forecast(self, ctx, setting: str, value: str):
        """Modifier les paramètres du module Forecast (météo)

        :param setting: Nom du paramètre à modifier
        :param value: Valeur à attribuer au paramètre (sera sérialisé en JSON)
        """
        if setting not in [s[0] for s in DEFAULT_SETTINGS]:
            return await ctx.send(f"**Erreur ·** Le paramètre `{setting}` n'existe pas")
        try:
            self.set_setting(setting, value)
        except Exception as e:
            logger.error(f"Erreur dans set_setting : {e}", exc_info=True)
            return await ctx.send(f"**Erreur ·** Il y a eu une erreur lors du réglage du paramètre, remontez cette erreur au propriétaire du bot")
        await ctx.send(f"**Succès ·** Le paramètre `{setting}` a été réglé sur `{value}`")
        
        
async def setup(bot):
    await bot.add_cog(Forecast(bot))