"""
Веб-панель для управления Discord ботом
"""
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading
import asyncio
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Глобальная ссылка на бота (будет установлена при запуске)
bot_instance = None
music_queues = {}
source_voice_channels = {}
created_voice_channels = {}


def init_web_panel(bot, queues, source_channels, created_channels):
    """Инициализация веб-панели с ссылками на данные бота"""
    global bot_instance, music_queues, source_voice_channels, created_voice_channels
    bot_instance = bot
    music_queues = queues
    source_voice_channels = source_channels
    created_voice_channels = created_channels


def run_async(coro):
    """Запуск асинхронной функции в синхронном контексте"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.route('/')
def index():
    """Главная страница веб-панели"""
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    """Получение статуса бота"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        guilds_count = len(bot_instance.guilds)
        is_ready = bot_instance.is_ready()
        
        # Подсчитываем активные голосовые подключения
        active_voice = len(bot_instance.voice_clients)
        
        return jsonify({
            'status': 'online' if is_ready else 'offline',
            'guilds': guilds_count,
            'active_voice_connections': active_voice,
            'bot_name': str(bot_instance.user) if bot_instance.user else 'Unknown',
            'uptime': 'N/A'  # Можно добавить отслеживание времени работы
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/guilds')
def get_guilds():
    """Получение списка серверов"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        guilds = []
        for guild in bot_instance.guilds:
            guild_info = {
                'id': guild.id,
                'name': guild.name,
                'member_count': guild.member_count,
                'has_voice': any(vc.guild == guild for vc in bot_instance.voice_clients),
                'source_channel_set': guild.id in source_voice_channels,
                'created_channels_count': len(created_voice_channels.get(guild.id, set()))
            }
            guilds.append(guild_info)
        
        return jsonify({'guilds': guilds})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/guild/<int:guild_id>/music')
def get_music_status(guild_id):
    """Получение статуса музыки для сервера"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        voice_client = None
        for vc in bot_instance.voice_clients:
            if vc.guild.id == guild_id:
                voice_client = vc
                break
        
        queue = music_queues.get(guild_id, [])
        current_track = None
        is_playing = False
        is_paused = False
        volume = 50
        
        if voice_client:
            is_playing = voice_client.is_playing()
            is_paused = voice_client.is_paused()
            if voice_client.source:
                current_track = getattr(voice_client.source, 'title', 'Unknown')
                volume = int(getattr(voice_client.source, 'volume', 0.5) * 100)
        
        return jsonify({
            'connected': voice_client is not None,
            'is_playing': is_playing,
            'is_paused': is_paused,
            'current_track': current_track,
            'volume': volume,
            'queue': queue[:10],  # Первые 10 треков
            'queue_length': len(queue)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/guild/<int:guild_id>/music/control', methods=['POST'])
def control_music(guild_id):
    """Управление воспроизведением музыки"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        action = request.json.get('action')
        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        voice_client = None
        for vc in bot_instance.voice_clients:
            if vc.guild.id == guild_id:
                voice_client = vc
                break
        
        if not voice_client:
            return jsonify({'error': 'Bot not connected to voice channel'}), 400
        
        if action == 'pause':
            if voice_client.is_playing():
                voice_client.pause()
                return jsonify({'success': True, 'message': 'Playback paused'})
            return jsonify({'error': 'Nothing is playing'}), 400
        
        elif action == 'resume':
            if voice_client.is_paused():
                voice_client.resume()
                return jsonify({'success': True, 'message': 'Playback resumed'})
            return jsonify({'error': 'Playback is not paused'}), 400
        
        elif action == 'stop':
            voice_client.stop()
            if guild_id in music_queues:
                music_queues[guild_id].clear()
            return jsonify({'success': True, 'message': 'Playback stopped'})
        
        elif action == 'skip':
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
                return jsonify({'success': True, 'message': 'Track skipped'})
            return jsonify({'error': 'Nothing is playing'}), 400
        
        else:
            return jsonify({'error': 'Invalid action'}), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/guild/<int:guild_id>/music/volume', methods=['POST'])
def set_volume(guild_id):
    """Установка громкости"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        volume = request.json.get('volume')
        if volume is None or not (0 <= volume <= 100):
            return jsonify({'error': 'Volume must be between 0 and 100'}), 400
        
        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        voice_client = None
        for vc in bot_instance.voice_clients:
            if vc.guild.id == guild_id:
                voice_client = vc
                break
        
        if not voice_client or not voice_client.source:
            return jsonify({'error': 'Bot not playing anything'}), 400
        
        voice_client.source.volume = volume / 100
        return jsonify({'success': True, 'volume': volume})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/guild/<int:guild_id>/voice-channels')
def get_voice_channels_info(guild_id):
    """Получение информации о настройках голосовых каналов"""
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 500
    
    try:
        guild = bot_instance.get_guild(guild_id)
        if not guild:
            return jsonify({'error': 'Guild not found'}), 404
        
        source_channel_id = source_voice_channels.get(guild_id)
        source_channel = None
        if source_channel_id:
            source_channel = guild.get_channel(source_channel_id)
        
        created_channels = created_voice_channels.get(guild_id, set())
        created_channels_info = []
        
        for channel_id in created_channels:
            channel = guild.get_channel(channel_id)
            if channel:
                created_channels_info.append({
                    'id': channel.id,
                    'name': channel.name,
                    'members': len([m for m in channel.members if not m.bot])
                })
        
        return jsonify({
            'source_channel': {
                'id': source_channel.id,
                'name': source_channel.name
            } if source_channel else None,
            'created_channels': created_channels_info,
            'created_channels_count': len(created_channels)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_web_panel(host='0.0.0.0', port=5000):
    """Запуск веб-панели"""
    app.run(host=host, port=port, debug=False, threaded=True)

