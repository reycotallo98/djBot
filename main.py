import logging
import os
import discord
import yt_dlp
import discord.ext
import yt_dlp as youtube_dl
import asyncio
import google.generativeai as genai
import nacl
from discord.ext import commands
from discord import app_commands

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is running"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

if not os.path.exists('ffmpeg'):
    os.system('curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar xJ && mv ffmpeg-*-static/ffmpeg .')
# Suponiendo que Google Gemini ofrece una API RESTful
API_KEY = os.environ['API_KEY']
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-pro')
# Configurar el bot de Discord
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
# Cola de canciones
song_queue = []


# Función para extraer canciones del texto de respuesta de Google Gemini
def parse_songs_from_gemini_response(response_text):
    songs = response_text.split('*')
    songs = [song.strip() for song in songs if song.strip()]
    return songs


# Función para obtener canciones desde Google Gemini (hipotético)
def get_songs_from_gemini(mood, num_songs=10):
    response_text = model.generate_content(
        "Hazme una lista de {num_songs} canciones para mi estado actual que es {mood}, solo debes devolver la lista sin texto extra, la lista debe tener el siguiente formato donde cancion serán los títulos de las canciones recomendadas *cancion*cancion*cancion*.")

    songs = parse_songs_from_gemini_response(response_text.text)
    return songs


# Función para buscar la primera URL en YouTube
def search_youtube(song_name):
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch1',  # Realiza una búsqueda y toma el primer resultado
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(song_name, download=False)
        if 'entries' in info:

            video = info['entries'][0]
            return f"https://www.youtube.com/watch?v={video['id']}"
        else:
            return None


# Manejar la reproducción de la cola de canciones
async def play_next(interaction: discord.Interaction):
    if song_queue:
        song_url = song_queue.pop(0)
        interaction.guild.voice_client.play(discord.FFmpegPCMAudio(source=song_url), after=lambda e: bot.loop.create_task(play_next(interaction)))
        await interaction.followup.send(f"Reproduciendo ahora: {song_url}")
    else:
        await interaction.followup.send("No hay más canciones en la cola.")



def get_audio_url_with_ytdlp(url):
    ydl_opts = {
        'format': 'bestaudio',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            formats = info_dict.get('formats', [info_dict])

            # Filtrar formatos de solo audio
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and 'audio' in f.get('format', '')]

            if not audio_formats:
                print("No se encontraron formatos de audio compatibles.")
                return None

            # Elegir el primer formato de audio disponible
            audio_url = audio_formats[0]['url']
            print(f"URL de audio seleccionada: {audio_url}")
            return audio_url
    except Exception as e:
        print(f"Error al obtener la URL de audio: {e}")
        return None

def get_audio_url_with_pytube(url):
    try:
        yt = YouTube(url)
        audio_stream = yt.streams.filter(only_audio=True).first()
        print("Conseguido")
        return audio_stream.url
    except Exception as e:
        print(f"Error al obtener la URL de audio con pytube: {e}")
        return None
@bot.event
async def on_ready():
    try:
        # Sincroniza los comandos de barra
        await bot.tree.sync()
        print(f'DJ Jito en la sala')
    except Exception as e:
        print(f"Error al sincronizar los comandos de barra: {e}")


async def play_song(ctx, voice_client, url):
    print("AAAaAAAA")
    try:
        audio_url = get_audio_url_with_pytube(url)

        if not audio_url:
            await ctx.send(f"No se pudo obtener una URL válida para el audio.")
            return

        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        voice_client.play(discord.FFmpegPCMAudio(audio_url, **ffmpeg_options),
                          after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
        await ctx.send(f"Reproduciendo: {url}")
    except Exception as e:
        await ctx.send(f"Error al intentar reproducir el audio: {e}")
        print(f"Error al intentar reproducir el audio: {e}")



@bot.tree.command(name="mood", description="Añade 5 canciones a la lista de reproducción acordes a tu mood!")
async def mood(interaction: discord.Interaction, mood: str, num_songs: int = 5):
    global song_queue
    await interaction.response.defer()  # Defer to allow time for processing
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        if not interaction.guild.voice_client:
            await channel.connect()

        # Obtener canciones desde Google Gemini (asume que esta función está definida)
        song_titles = get_songs_from_gemini(mood, num_songs)
        await interaction.followup.send(
            f"Se reproducirán las siguientes canciones para el estado de ánimo '{mood}':\n" + "\n".join(song_titles)
        )

        # Buscar las URL de YouTube para las canciones sugeridas (asume que esta función está definida)
        for song in song_titles:
            song_url = search_youtube(song)
            if song_url:
                song_queue.append(song_url)
            else:
                await interaction.followup.send(f"No se encontró la canción: {song}")

        if not interaction.guild.voice_client.is_playing():
            await play_next(interaction)
    else:
        await interaction.followup.send("¡Necesitas estar en un canal de voz para usar este comando!")


@bot.tree.command(name="play", description="Añade una canción a la playlist")
async def play(interaction: discord.Interaction, search: str):
    await interaction.response.defer()  # Defer to allow time for processing
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="DJing"))

    # Verifica si el usuario está en un canal de voz
    if not interaction.user.voice:
        await interaction.followup.send("¡Necesitas estar en un canal de voz para reproducir música!")
        return

    # Conectar al canal de voz
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        voice_client = await interaction.user.voice.channel.connect()
    elif voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)

    # Buscar la canción en YouTube
    song_url = search_youtube(search)
    if not song_url:
        await interaction.followup.send("No se encontró la canción en YouTube.")
        return

    # Añadir la canción a la cola
    song_queue.append(song_url)
    await interaction.followup.send(f"Se ha añadido la canción a la cola: {song_url}")

    # Si no hay nada reproduciéndose, empieza a reproducir
    if not voice_client.is_playing():
        await play_next(interaction)


async def play_next(interaction):
    if len(song_queue) > 0:
        song_url = song_queue.pop(0)
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await interaction.followup.send("¡No hay ningún cliente de voz conectado!")
            return

        try:
            # Aquí asumimos que `get_audio_url_with_ytdlp` funciona correctamente
            audio_url = get_audio_url_with_ytdlp(song_url)
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }

            voice_client.play(discord.FFmpegPCMAudio(audio_url, **ffmpeg_options),
                              after=lambda e: bot.loop.create_task(play_next(interaction)))
            await interaction.followup.send(f"Reproduciendo: {song_url}")
        except Exception as e:
            await interaction.followup.send(f"Error al intentar reproducir el audio: {e}")
            print(f"Error al intentar reproducir el audio: {e}")
    else:
        await interaction.followup.send("La cola de canciones está vacía.")

@bot.tree.command(name="skip", description="Salta la canción")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Canción saltada.")
    else:
        await interaction.response.send_message("No hay una canción reproduciéndose actualmente.")


@bot.tree.command(name="pause", description="Pausa la reproducción en curso")
async def pause(interaction: discord.Interaction):
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Sleep"))

    if interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("Canción pausada.")
    else:
        await interaction.response.send_message("No hay una canción reproduciéndose actualmente.")


@bot.tree.command(name="resume", description="Reanuda la reproducción en curso")
async def resume(interaction: discord.Interaction):
    if interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("Canción reanudada.")
    else:
        await interaction.response.send_message("No hay una canción pausada actualmente.")


@bot.tree.command(name="stop", description="Para la reproducción y desconecta el bot del canal")
async def stop(interaction: discord.Interaction):
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Sleep"))

    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Reproducción detenida y bot desconectado.")
    else:
        await interaction.response.send_message("No hay nada que detener.")


@bot.tree.command(name="join", description="Une al bot en el canal")
async def join(interaction: discord.Interaction):
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Djing"))

    if interaction.user.voice:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client is None:
            await channel.connect()
        else:
            await interaction.guild.voice_client.move_to(channel)
        await interaction.response.send_message("Me he unido al canal de voz.")
    else:
        await interaction.response.send_message("¡Necesitas estar en un canal de voz para invitarme!")


@bot.tree.command(name="leave", description="Desconecta al bot del canal")
async def leave(interaction: discord.Interaction):
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="Sleep"))

    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Me he desconectado del canal de voz.")
    else:
        await interaction.response.send_message("No estoy conectado a ningún canal de voz.")


logging.basicConfig(level=logging.DEBUG)
keep_alive()  # Mantener vivo el bot
bot.run(os.environ['DISCOR_KEY'])
