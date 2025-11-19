import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import re
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

import json

# Загружаем переменные окружения
load_dotenv()

# Настройки бота
TOKEN = os.getenv('DISCORD_TOKEN')
SOURCE_CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID', 0))  # ID канала, из которого повторять
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID', 0))  # ID канала, в который повторять (0 = тот же канал)

# Файл для хранения настроек голосовых каналов
VOICE_CHANNELS_FILE = 'voice_channels.json'

# Настройки Spotify (опционально)
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')

# Настройка intents для получения сообщений и работы с голосовыми каналами
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Создаём бота
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree  # Для слэш-команд и autocomplete

# Инициализация Spotify (если указаны ключи)
spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        client_credentials_manager = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        )
        spotify = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
        print("✅ Spotify API подключен")
    except Exception as e:
        print(f"⚠️ Ошибка подключения к Spotify API: {e}")

# Словарь для хранения очередей воспроизведения для каждого сервера
music_queues = {}

def load_voice_channels():
    """Загружает настройки голосовых каналов из файла"""
    if os.path.exists(VOICE_CHANNELS_FILE):
        try:
            with open(VOICE_CHANNELS_FILE, 'r') as f:
                data = json.load(f)
                # Конвертируем ключи (guild_id) обратно в int
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            print(f"Ошибка загрузки настроек каналов: {e}")
    return {}

def save_voice_channels():
    """Сохраняет настройки голосовых каналов в файл"""
    try:
        with open(VOICE_CHANNELS_FILE, 'w') as f:
            json.dump(source_voice_channels, f)
    except Exception as e:
        print(f"Ошибка сохранения настроек каналов: {e}")

# Словарь для хранения исходных голосовых каналов для каждого сервера
# Ключ: guild_id, Значение: voice_channel_id
source_voice_channels = load_voice_channels()

# Множество для хранения созданных ботом голосовых каналов
# Ключ: guild_id, Значение: set(channel_id)
created_voice_channels = {}

# Настройки yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=not stream)
        )

        if 'entries' in data:
            # Берём первый результат, если это плейлист
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


@bot.event
async def on_ready():
    """Вызывается при готовности бота"""
    print(f'{bot.user} подключился к Discord!')
    print(f'Бот работает на {len(bot.guilds)} серверах')
    
    # Выводим список всех загруженных команд
    print(f'📋 Загружено команд: {len(bot.commands)}')
    for cmd in bot.commands:
        print(f'  - {cmd.name} (алиасы: {cmd.aliases})')
    
    # Синхронизируем команды (для autocomplete)
    try:
        synced = await tree.sync()
        print(f'✅ Синхронизировано {len(synced)} команд')
    except Exception as e:
        print(f'❌ Ошибка синхронизации команд: {e}')


@bot.event
async def on_message(message):
    """Обработчик всех сообщений"""
    # Игнорируем сообщения от ботов (включая самого себя)
    if message.author.bot:
        return
    
    # Проверяем, что сообщение из нужного канала
    if SOURCE_CHANNEL_ID and message.channel.id == SOURCE_CHANNEL_ID:
        # Если TARGET_CHANNEL_ID указан, отправляем в другой канал
        if TARGET_CHANNEL_ID:
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            if target_channel:
                # Повторяем сообщение
                content = f"**{message.author.name}**: {message.content}"
                if message.attachments:
                    # Если есть вложения, добавляем их
                    for attachment in message.attachments:
                        content += f"\n{attachment.url}"
                await target_channel.send(content)
        else:
            # Если TARGET_CHANNEL_ID не указан, повторяем в том же канале (после оригинального сообщения)
            if message.content:
                await message.channel.send(f"🔄 {message.content}")
    
    # Позволяем командам работать
    await bot.process_commands(message)


@bot.command(name='ping')
async def ping(ctx):
    """Проверка работоспособности бота"""
    await ctx.send(f'Понг! Задержка: {round(bot.latency * 1000)}ms')


@bot.command(name='setup')
async def setup(ctx, source: discord.TextChannel = None, target: discord.TextChannel = None):
    """Настройка каналов для повтора сообщений (для текущей сессии)"""
    global SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID
    
    if source:
        SOURCE_CHANNEL_ID = source.id
        await ctx.send(f'✅ Исходный канал установлен: {source.mention}')
    
    if target:
        TARGET_CHANNEL_ID = target.id
        await ctx.send(f'✅ Целевой канал установлен: {target.mention}')
    
    if not source and not target:
        await ctx.send('Использование: `!setup #исходный_канал #целевой_канал`\n'
                      'Или: `!setup #канал` (для повтора в тот же канал)')


# ==================== МУЗЫКАЛЬНЫЕ КОМАНДЫ ====================

def get_spotify_track_info(url):
    """Получает информацию о треке из Spotify"""
    if not spotify:
        return None
    
    try:
        track_id = url.split('/')[-1].split('?')[0]
        track = spotify.track(track_id)
        
        artists = ', '.join([artist['name'] for artist in track['artists']])
        title = track['name']
        search_query = f"{artists} {title}"
        
        return {
            'title': title,
            'artists': artists,
            'search_query': search_query,
            'url': track['external_urls']['spotify']
        }
    except Exception as e:
        print(f"Ошибка получения информации о треке Spotify: {e}")
        return None


def search_spotify_tracks(query, limit=5):
    """Поиск треков в Spotify для autocomplete"""
    if not spotify or not query or len(query) < 2:
        return []
    
    try:
        results = spotify.search(q=query, type='track', limit=limit)
        tracks = []
        
        for item in results['tracks']['items']:
            artists = ', '.join([artist['name'] for artist in item['artists']])
            title = item['name']
            track_name = f"{artists} - {title}"
            spotify_url = item['external_urls']['spotify']
            
            tracks.append({
                'name': track_name,
                'value': spotify_url if len(track_name) > 100 else track_name,  # Discord ограничение 100 символов
                'url': spotify_url
            })
        
        return tracks
    except Exception as e:
        print(f"Ошибка поиска в Spotify: {e}")
        return []


def extract_spotify_url(text):
    """Извлекает URL Spotify из текста"""
    spotify_url_pattern = r'(https?://(?:open\.)?spotify\.com/(?:track|album|playlist)/[a-zA-Z0-9]+)'
    match = re.search(spotify_url_pattern, text)
    return match.group(1) if match else None


async def play_next(ctx, guild_id):
    """Воспроизводит следующий трек из очереди"""
    if guild_id not in music_queues or not music_queues[guild_id]:
        return
    
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not voice_client:
        return
    
    if voice_client.is_playing():
        return
    
    query = music_queues[guild_id].pop(0)
    
    try:
        # Если это поисковый запрос, добавляем префикс ytsearch
        if not query.startswith('http'):
            query = f"ytsearch1:{query}"
        elif query.startswith('https://open.spotify.com'):
            # Если это Spotify URL, получаем информацию о треке
            track_info = get_spotify_track_info(query)
            if track_info:
                query = f"ytsearch1:{track_info['search_query']}"
        
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        voice_client.play(
            player,
            after=lambda e: asyncio.run_coroutine_threadsafe(
                play_next(ctx, guild_id), bot.loop
            ) if e is None else print(f'Ошибка воспроизведения: {e}')
        )
        await ctx.send(f'🎵 Сейчас играет: **{player.title}**')
    except Exception as e:
        await ctx.send(f'❌ Ошибка воспроизведения: {str(e)}')
        # Пробуем следующий трек
        if music_queues[guild_id]:
            await play_next(ctx, guild_id)


@bot.command(name='join')
async def join(ctx):
    """Подключение бота к голосовому каналу"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f'✅ Подключился к каналу {channel.name}')
    else:
        await ctx.send('❌ Вы должны находиться в голосовом канале!')


@bot.command(name='leave')
async def leave(ctx):
    """Отключение бота от голосового канала"""
    if ctx.voice_client:
        if ctx.guild.id in music_queues:
            music_queues[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send('👋 Отключился от голосового канала')
    else:
        await ctx.send('❌ Бот не подключен к голосовому каналу')


async def play_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete для команды play - поиск треков в Spotify"""
    if not current or len(current) < 2:
        return []
    
    # Если это уже URL Spotify, не показываем предложения
    if current.startswith('http') and 'spotify.com' in current:
        return []
    
    # Ищем в Spotify
    if not spotify:
        # Если Spotify API не настроен, возвращаем пустой список
        return []
    
    try:
        results = search_spotify_tracks(current, limit=25)
        
        # Формируем список для Discord (максимум 25 вариантов)
        choices = []
        for track in results[:25]:
            # Используем имя трека как отображаемое имя, а Spotify URL как значение
            display_name = track['name'][:100]  # Discord ограничение на длину имени
            # Используем Spotify URL как значение для точного воспроизведения
            spotify_url = track['url']
            choices.append(app_commands.Choice(name=display_name, value=spotify_url))
        
        return choices
    except Exception as e:
        print(f"Ошибка autocomplete: {e}")
        return []


@bot.hybrid_command(name='play', aliases=['p'], description='Воспроизведение музыки из Spotify или поиск на YouTube')
@app_commands.autocomplete(query=play_autocomplete)
@app_commands.describe(query='Название трека или ссылка на Spotify')
async def play(ctx, *, query: str):
    """Воспроизведение музыки из Spotify или поиск на YouTube"""
    if not ctx.author.voice:
        await ctx.send('❌ Вы должны находиться в голосовом канале!')
        return
    
    # Проверяем, является ли запрос URL Spotify
    spotify_url = extract_spotify_url(query)
    search_query = query
    queue_item = query  # Что сохраним в очередь (может быть Spotify URL или поисковый запрос)
    
    if spotify_url:
        await ctx.send(f'🔍 Ищу трек в Spotify...')
        track_info = get_spotify_track_info(spotify_url)
        if track_info:
            search_query = track_info['search_query']
            queue_item = spotify_url  # Сохраняем оригинальный Spotify URL в очередь
            await ctx.send(f'🎵 Найден: **{track_info["artists"]} - {track_info["title"]}**\n'
                         f'🔗 {track_info["url"]}\n'
                         f'📥 Ищу на YouTube...')
        else:
            await ctx.send('⚠️ Не удалось получить информацию о треке Spotify, ищу на YouTube...')
            queue_item = search_query
    
    # Подключаемся к голосовому каналу, если ещё не подключены
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    
    # Инициализируем очередь для сервера, если её нет
    if ctx.guild.id not in music_queues:
        music_queues[ctx.guild.id] = []
    
    # Ищем на YouTube
    try:
        await ctx.send(f'🔍 Ищу: **{search_query}**')
        yt_search = f"ytsearch1:{search_query}"
        player = await YTDLSource.from_url(yt_search, loop=bot.loop, stream=True)
        
        voice_client = ctx.voice_client
        
        if voice_client.is_playing():
            # Если что-то уже играет, добавляем в очередь (сохраняем оригинальный запрос или Spotify URL)
            music_queues[ctx.guild.id].append(queue_item)
            await ctx.send(f'✅ Добавлено в очередь: **{player.title}**\n'
                         f'📍 Позиция в очереди: {len(music_queues[ctx.guild.id])}')
        else:
            # Воспроизводим сразу
            voice_client.play(
                player,
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    play_next(ctx, ctx.guild.id), bot.loop
                ) if e is None else print(f'Ошибка воспроизведения: {e}')
            )
            await ctx.send(f'🎵 Сейчас играет: **{player.title}**')
            
    except Exception as e:
        await ctx.send(f'❌ Ошибка: {str(e)}')


@bot.command(name='pause')
async def pause(ctx):
    """Приостановка воспроизведения"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send('⏸️ Воспроизведение приостановлено')
    else:
        await ctx.send('❌ Ничего не воспроизводится')


@bot.command(name='resume')
async def resume(ctx):
    """Возобновление воспроизведения"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send('▶️ Воспроизведение возобновлено')
    else:
        await ctx.send('❌ Воспроизведение не приостановлено')


@bot.command(name='stop')
async def stop(ctx):
    """Остановка воспроизведения и очистка очереди"""
    if ctx.voice_client:
        if ctx.guild.id in music_queues:
            music_queues[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send('⏹️ Воспроизведение остановлено, очередь очищена')
    else:
        await ctx.send('❌ Бот не подключен к голосовому каналу')


@bot.command(name='skip')
async def skip(ctx):
    """Пропуск текущего трека"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send('⏭️ Трек пропущен')
        # Воспроизводим следующий трек
        if ctx.guild.id in music_queues and music_queues[ctx.guild.id]:
            await play_next(ctx, ctx.guild.id)
    else:
        await ctx.send('❌ Ничего не воспроизводится')


@bot.command(name='queue', aliases=['q'])
async def queue(ctx):
    """Показать очередь воспроизведения"""
    if ctx.guild.id in music_queues and music_queues[ctx.guild.id]:
        queue_list = music_queues[ctx.guild.id][:10]  # Показываем первые 10
        queue_text = '\n'.join([f'{i+1}. {query}' for i, query in enumerate(queue_list)])
        await ctx.send(f'📋 Очередь воспроизведения ({len(music_queues[ctx.guild.id])} треков):\n{queue_text}')
    else:
        await ctx.send('📋 Очередь пуста')


@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, volume: int = None):
    """Установка громкости (0-100)"""
    if ctx.voice_client:
        if volume is None:
            current_volume = int(ctx.voice_client.source.volume * 100) if ctx.voice_client.source else 50
            await ctx.send(f'🔊 Текущая громкость: {current_volume}%')
        else:
            if 0 <= volume <= 100:
                if ctx.voice_client.source:
                    ctx.voice_client.source.volume = volume / 100
                    await ctx.send(f'🔊 Громкость установлена: {volume}%')
                else:
                    await ctx.send('❌ Ничего не воспроизводится')
            else:
                await ctx.send('❌ Громкость должна быть от 0 до 100')
    else:
        await ctx.send('❌ Бот не подключен к голосовому каналу')


# ==================== АВТОМАТИЧЕСКОЕ СОЗДАНИЕ ГОЛОСОВЫХ КАНАЛОВ ====================

@bot.command(name='setvoicechannel', aliases=['svc'])
async def set_voice_channel(ctx, *, channel_input: str = None):
    """Установка исходного голосового канала для автоматического создания новых каналов
    
    Использование: !setvoicechannel #канал
    Или: !svc (если вы находитесь в голосовом канале)
    """
    channel = None
    
    if channel_input:
        # Пытаемся конвертировать через конвертер discord.py
        try:
            converter = commands.VoiceChannelConverter()
            channel = await converter.convert(ctx, channel_input)
        except commands.BadArgument:
            # Если конвертер не сработал, пытаемся найти канал вручную
            # Извлекаем ID из упоминания <#ID> или используем как ID
            channel_id = None
            if channel_input.startswith('<#') and channel_input.endswith('>'):
                try:
                    channel_id = int(channel_input[2:-1])
                except ValueError:
                    pass
            else:
                try:
                    channel_id = int(channel_input)
                except ValueError:
                    # Ищем по имени
                    channel = discord.utils.get(ctx.guild.voice_channels, name=channel_input)
            
            if channel_id and not channel:
                found_channel = ctx.guild.get_channel(channel_id)
                if found_channel and isinstance(found_channel, discord.VoiceChannel):
                    channel = found_channel
    
    # Если канал не найден и не указан, пытаемся получить канал автора команды
    if channel is None:
        if ctx.author.voice and ctx.author.voice.channel:
            channel = ctx.author.voice.channel
        else:
            await ctx.send('❌ Укажите голосовой канал! Использование: `!setvoicechannel #канал`\n'
                          'Или зайдите в голосовой канал и используйте команду без параметров.')
            return
    
    if not isinstance(channel, discord.VoiceChannel):
        await ctx.send('❌ Указанный канал не является голосовым каналом!')
        return
    
    source_voice_channels[ctx.guild.id] = channel.id
    save_voice_channels()
    await ctx.send(f'✅ Исходный голосовой канал установлен: {channel.mention}\n'
                   f'Теперь при заходе в этот канал будет создаваться новый канал с максимальным качеством.')


@bot.command(name='removevoicechannel', aliases=['rvc'])
async def remove_voice_channel(ctx):
    """Удаление настройки исходного голосового канала"""
    if ctx.guild.id in source_voice_channels:
        del source_voice_channels[ctx.guild.id]
        save_voice_channels()
        await ctx.send('✅ Настройка исходного голосового канала удалена')
    else:
        await ctx.send('❌ Исходный голосовой канал не установлен')


@bot.event
async def on_voice_state_update(member, before, after):
    """Обработчик изменений состояния голосовых каналов"""
    # Игнорируем ботов
    if member.bot:
        return
    
    guild_id = member.guild.id
    
    # Проверяем, установлен ли исходный канал для этого сервера
    if guild_id not in source_voice_channels:
        # Проверяем удаление пустых созданных каналов даже если исходный канал не установлен
        # (на случай, если настройка была удалена, но каналы остались)
        if before and before.channel:
            await check_and_delete_empty_channel(before.channel, guild_id)
        return
    
    source_channel_id = source_voice_channels[guild_id]
    
    # Проверяем, зашёл ли пользователь в исходный канал
    if after.channel and after.channel.id == source_channel_id:
        try:
            # Получаем максимальный битрейт для сервера
            # Для обычных серверов: 96000, для VIP: 128000, для Boost Level 2: 256000, для Boost Level 3: 384000
            max_bitrate = min(384000, member.guild.bitrate_limit)
            
            # Создаём новый голосовой канал с максимальным качеством
            category = after.channel.category
            new_channel = await member.guild.create_voice_channel(
                name=f'🎵 {member.display_name}',
                category=category,
                bitrate=max_bitrate,
                user_limit=0  # Без ограничения пользователей
            )
            
            # Добавляем канал в список созданных каналов
            if guild_id not in created_voice_channels:
                created_voice_channels[guild_id] = set()
            created_voice_channels[guild_id].add(new_channel.id)
            
            # Перемещаем пользователя в новый канал
            await member.move_to(new_channel)
            
            # Отправляем уведомление (если есть текстовый канал)
            # Можно настроить отправку в определённый канал или в канал, где была команда
            print(f'✅ Создан новый голосовой канал {new_channel.name} для {member.display_name} с битрейтом {max_bitrate} bps')
            
        except discord.Forbidden:
            print(f'❌ Нет прав для создания голосового канала или перемещения пользователя')
        except discord.HTTPException as e:
            print(f'❌ Ошибка при создании канала или перемещении пользователя: {e}')
        except Exception as e:
            print(f'❌ Неожиданная ошибка: {e}')
    
    # Проверяем, покинул ли пользователь канал, который был создан ботом
    if before and before.channel:
        await check_and_delete_empty_channel(before.channel, guild_id)


async def check_and_delete_empty_channel(channel, guild_id):
    """Проверяет, является ли канал пустым созданным каналом, и удаляет его если да"""
    # Проверяем, был ли этот канал создан ботом
    if guild_id not in created_voice_channels:
        return
    
    if channel.id not in created_voice_channels[guild_id]:
        return
    
    # Проверяем, пуст ли канал (только боты или вообще никого)
    members = [m for m in channel.members if not m.bot]
    
    if len(members) == 0:
        try:
            # Удаляем канал из списка созданных
            created_voice_channels[guild_id].discard(channel.id)
            # Если список пуст, можно удалить ключ (опционально)
            if not created_voice_channels[guild_id]:
                del created_voice_channels[guild_id]
            
            # Удаляем канал
            await channel.delete()
            print(f'🗑️ Удалён пустой голосовой канал {channel.name}')
        except discord.Forbidden:
            print(f'❌ Нет прав для удаления голосового канала {channel.name}')
        except discord.HTTPException as e:
            print(f'❌ Ошибка при удалении канала {channel.name}: {e}')
        except Exception as e:
            print(f'❌ Неожиданная ошибка при удалении канала: {e}')


# Инициализация веб-панели (опционально)
WEB_PANEL_ENABLED = os.getenv('WEB_PANEL_ENABLED', 'false').lower() == 'true'
WEB_PANEL_PORT = int(os.getenv('WEB_PANEL_PORT', 5000))

if WEB_PANEL_ENABLED:
    try:
        from web_panel import init_web_panel, run_web_panel
        import threading
        import time
        
        def start_web_panel():
            """Запуск веб-панели в отдельном потоке"""
            # Небольшая задержка, чтобы бот успел инициализироваться
            time.sleep(2)
            try:
                init_web_panel(bot, music_queues, source_voice_channels, created_voice_channels)
                print(f'🚀 Запуск веб-панели на порту {WEB_PANEL_PORT}...')
                run_web_panel(host='0.0.0.0', port=WEB_PANEL_PORT)
            except Exception as e:
                print(f'❌ Ошибка в веб-панели: {e}')
                import traceback
                traceback.print_exc()
        
        # Запускаем веб-панель в отдельном потоке
        web_thread = threading.Thread(target=start_web_panel, daemon=True)
        web_thread.start()
        print(f'✅ Веб-панель инициализирована, будет доступна на http://0.0.0.0:{WEB_PANEL_PORT}')
    except ImportError as e:
        print(f'⚠️ Flask не установлен. Веб-панель недоступна. Установите: pip install flask flask-cors')
        print(f'   Детали ошибки: {e}')
    except Exception as e:
        print(f'⚠️ Ошибка запуска веб-панели: {e}')
        import traceback
        traceback.print_exc()
else:
    print('ℹ️ Веб-панель отключена. Установите WEB_PANEL_ENABLED=true для включения.')


# Запуск бота
if __name__ == '__main__':
    if not TOKEN:
        print('Ошибка: DISCORD_TOKEN не найден в .env файле!')
    else:
        bot.run(TOKEN)

