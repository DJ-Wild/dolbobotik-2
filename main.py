# === ИМПОРТЫ ===
import telebot
import brawlstats
import time
import os
import json
import re
import threading
from dotenv import load_dotenv
from telebot import types

# --- 1. НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ ---
# Эта строка позволяет тестировать бота на компьютере с .env файлом.
# На Render она не помешает, т.к. переменные будут браться из настроек сервиса.
load_dotenv() 

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BRAWLSTARS_API_KEY = os.getenv('BRAWLSTARS_API_KEY')
ADMIN_CHAT_ID_STR = os.getenv('ADMIN_CHAT_ID')

# Проверка, что все переменные окружения загружены
if not all([TELEGRAM_TOKEN, BRAWLSTARS_API_KEY, ADMIN_CHAT_ID_STR]):
    print("!!! КРИТИЧЕСКАЯ ОШИБКА: Не все переменные окружения найдены!")
    print("!!! Убедитесь, что вы добавили TELEGRAM_TOKEN, BRAWLSTARS_API_KEY и ADMIN_CHAT_ID в 'Environment Variables' на Render.")
    exit() # Завершаем работу, если нет ключей

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_STR)

bot = telebot.TeleBot(TELEGRAM_TOKEN, skip_pending=True)
bs_client = brawlstats.Client(BRAWLSTARS_API_KEY, load_brawlers_on_init=False)
TRACKED_PLAYERS_FILE = 'tracked_players.json'
EMOJI = {'trophy': '🏆', 'star': '⭐', 'level': '📊', 'victory': '✅', 'club': '🏰', 'brawler': '🤖', 'error': '❌', 'info': 'ℹ️', 'chart': '📈', 'crown': '👑'}

# --- 2. ФУНКЦИИ ДЛЯ РАБОТЫ С JSON-ФАЙЛОМ ---
def load_tracked_players():
    """Загружает данные из JSON. Если файла нет - создает его."""
    try:
        with open(TRACKED_PLAYERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_tracked_players({})
        return {}

def save_tracked_players(players_data):
    """Сохраняет данные в JSON."""
    with open(TRACKED_PLAYERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(players_data, f, indent=4, ensure_ascii=False)

# --- 3. ОБРАБОТЧИКИ TELEGRAM КОМАНД ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот для статистики Brawl Stars.\n\n"
                                      f"• <b>/profile</b> или <b>бс профиль</b> - узнать инфо об игроке.\n"
                                      f"• <b>/leaderboard</b> или <b>бс лидер</b> - посмотреть топы.", parse_mode='HTML')

@bot.message_handler(commands=['profile'])
@bot.message_handler(func=lambda message: message.text and message.text.lower() in ('бс профиль', 'профиль'))
def request_player_tag(message):
    markup = types.ForceReply(selective=False, input_field_placeholder='Введите тег, например: #2G98QY98')
    bot.send_message(message.chat.id, f"{EMOJI['info']} Введите тег игрока Brawl Stars:", reply_markup=markup)
    bot.register_next_step_handler(message, process_player_tag)

def process_player_tag(message):
    try:
        tag = message.text.strip().upper().replace('O', '0')
        if not tag.startswith('#'): tag = '#' + tag
        if not re.match(r'^#[0289PYLQGRJCUV]{3,}$', tag): raise ValueError("Неверный формат тега")
    except (AttributeError, ValueError):
        bot.send_message(message.chat.id, f"{EMOJI['error']} Неверный формат тега!\nПример: #2G98QY98")
        return

    bot.send_chat_action(message.chat.id, 'typing')
    try:
        player = bs_client.get_player(tag)
        
        club_info = f"{player.club.name} ({player.club.tag})" if player.club else "Не состоит"
        top_brawlers = sorted(player.brawlers, key=lambda b: b.trophies, reverse=True)[:5]
        brawlers_list = [f"{i+1}. {b.name.ljust(12)} {EMOJI['trophy']} {str(b.trophies).rjust(4)} | Rank: {b.rank}" for i, b in enumerate(top_brawlers)]
        brawlers_text = "<pre>" + "\n".join(brawlers_list) + "</pre>"
        
        response = (
            f"<b>{EMOJI['info']} ПРОФИЛЬ BRAWL STARS</b>\n\n<b>Имя:</b> {player.name}\n<b>Тег:</b> <code>{player.tag}</code>\n\n"
            f"<b>{EMOJI['trophy']} Трофеи:</b> {player.trophies}\n<b>{EMOJI['star']} Рекорд:</b> {player.highest_trophies}\n<b>{EMOJI['level']} Уровень:</b> {player.exp_level}\n\n"
            f"<b>{EMOJI['victory']} Победы 3v3:</b> {player.x3v3_victories}\n<b>{EMOJI['victory']} Solo/Duo:</b> {player.solo_victories} / {player.duo_victories}\n\n"
            f"<b>{EMOJI['club']} Клуб:</b> {club_info}\n\n<b>{EMOJI['brawler']} Топ-5 бравлеров:</b>\n{brawlers_text}"
        )
        bot.send_message(message.chat.id, response, parse_mode='HTML')

        tracked_players = load_tracked_players()
        current_time = int(time.time())
        if player.tag not in tracked_players:
            tracked_players[player.tag] = {'name': player.name, 'history': [{'timestamp': current_time, 'trophies': player.trophies}]}
            bot.send_message(message.chat.id, f"✅ Игрок <b>{player.name}</b> добавлен в ежечасное отслеживание.", parse_mode='HTML')
        else:
            tracked_players[player.tag]['name'] = player.name
        save_tracked_players(tracked_players)
    
    except Exception as e:
        bot.send_message(message.chat.id, f"{EMOJI['error']} Ошибка: {e}")

@bot.message_handler(commands=['leaderboard'])
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith('бс лидер'))
def leaderboard_handler(message):
    text = message.text.lower()
    periods = {'день': 86400, 'неделя': 7 * 86400, 'месяц': 30 * 86400}
    period_name = text.split(' ')[-1]
    
    if period_name in periods:
        title, period_seconds = f"за {period_name}", periods[period_name]
    else:
        title, period_seconds = "за всё время", float('inf')
    send_leaderboard(message.chat.id, period_seconds, title)

def send_leaderboard(chat_id, period_seconds, title):
    bot.send_chat_action(chat_id, 'typing')
    players_data = load_tracked_players()
    now = int(time.time())
    start_boundary = now - period_seconds
    leaderboard = []
    
    for tag, data in players_data.items():
        history = data.get('history', [])
        if not history: continue
        
        start_trophies = history[0]['trophies']
        if period_seconds != float('inf'):
            relevant_points = [p['trophies'] for p in history if p['timestamp'] < start_boundary]
            if relevant_points: start_trophies = relevant_points[-1]
        
        gain = history[-1]['trophies'] - start_trophies
        if gain > 0:
            leaderboard.append({'name': data.get('name', tag), 'gain': gain, 'current': history[-1]['trophies']})
            
    if not leaderboard:
        bot.send_message(chat_id, f"Никто не набил кубки {title}.")
        return
        
    sorted_leaderboard = sorted(leaderboard, key=lambda x: x['gain'], reverse=True)[:10]
    response_lines = [f"{EMOJI['crown']} <b>Лидерборд {title.upper()}</b> {EMOJI['crown']}\n"]
    for i, player in enumerate(sorted_leaderboard):
        place_emoji = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f' {i+1}.')
        response_lines.append(f"{place_emoji} <b>{player['name']}</b>: +{player['gain']} {EMOJI['trophy']} (всего: {player['current']})")
    
    bot.send_message(chat_id, "\n".join(response_lines), parse_mode='HTML')

# --- 4. ФОНОВЫЙ ПРОЦЕСС (ЕЖЕЧАСНЫЙ ТРЕКЕР) ---
def hourly_tracker():
    print("🚀 Ежечасный трекер запущен в фоновом режиме.")
    while True:
        time.sleep(3600)
        
        print(f"[{time.ctime()}] Начинаю ежечасную проверку кубков...")
        tracked_players = load_tracked_players()
        if not tracked_players:
            print("Список отслеживания пуст. Пропускаю проверку.")
            continue

        now = int(time.time())
        month_ago = now - 31 * 86400
        changes_report = []

        for tag, data in tracked_players.items():
            try:
                current_player = bs_client.get_player(tag)
                history = data.get('history', [])
                if history:
                    trophy_change = current_player.trophies - history[-1]['trophies']
                    if trophy_change > 0:
                        report_line = f" • <b>{current_player.name}</b>: +{trophy_change} {EMOJI['trophy']} (стало {current_player.trophies})"
                        changes_report.append(report_line)
                
                data.get('history', []).append({'timestamp': now, 'trophies': current_player.trophies})
                data['history'] = [p for p in data['history'] if p['timestamp'] > month_ago]
                data['name'] = current_player.name
            except Exception as e:
                print(f"Ошибка при проверке тега {tag}: {e}")
        
        if changes_report:
            header = f"{EMOJI['chart']} <b>Ежечасный отчет по кубкам:</b>\n\n"
            full_report = header + "\n".join(changes_report)
            try:
                bot.send_message(ADMIN_CHAT_ID, full_report, parse_mode='HTML')
                print("Отчет об изменениях отправлен администратору.")
            except Exception as e:
                print(f"Не удалось отправить отчет администратору: {e}")

        save_tracked_players(tracked_players)
        print("Проверка завершена.")

# --- 5. ГЛАВНЫЙ ЗАПУСК ПРОГРАММЫ ---
if __name__ == '__main__':
    print("Запускаю основного бота...")
    
    # Запускаем ежечасный трекер в отдельном фоновом потоке.
    # daemon=True означает, что поток закроется, если основная программа упадет.
    tracker_thread = threading.Thread(target=hourly_tracker, daemon=True)
    tracker_thread.start()
    
    # Основной поток будет вечно занят ожиданием сообщений от Telegram.
    print("✅ Бот и фоновый трекер запущены! Бот ждет команд...")
    bot.infinity_polling(timeout=30)
