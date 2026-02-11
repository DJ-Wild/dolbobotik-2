# main.py
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
from pymongo import MongoClient # Новая библиотека
from datetime import datetime

# --- 1. ИНИЦИАЛИЗАЦИЯ ---
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BRAWLSTARS_API_KEY = os.getenv('BRAWLSTARS_API_KEY')
ADMIN_CHAT_ID_STR = os.getenv('ADMIN_CHAT_ID')
MONGO_URI = os.getenv('MONGO_URI')

if not all([TELEGRAM_TOKEN, BRAWLSTARS_API_KEY, ADMIN_CHAT_ID_STR, MONGO_URI]):
    raise ValueError("ОШИБКА: Не найдены ключи! Проверьте все 4 переменные в .env файле.")

ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_STR)

bot = telebot.TeleBot(TELEGRAM_TOKEN, skip_pending=True)
bs_client = brawlstats.Client(BRAWLSTARS_API_KEY, load_brawlers_on_init=False)

# Подключение к MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.minecraft_db
stats_collection = db.server_stats
TRACKED_PLAYERS_FILE = 'tracked_players.json'
EMOJI = {'trophy': '🏆', 'star': '⭐', 'level': '📊', 'victory': '✅', 'club': '🏰', 'brawler': '🤖', 'error': '❌',
         'info': 'ℹ️', 'chart': '📈', 'crown': '👑'}


# --- 2. ФУНКЦИИ ДЛЯ РАБОТЫ С JSON ---
def load_tracked_players():
    try:
        with open(TRACKED_PLAYERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_tracked_players(players_data):
    with open(TRACKED_PLAYERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(players_data, f, indent=4, ensure_ascii=False)


# --- 3. ОБРАБОТЧИКИ КОМАНД TELEGRAM ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id,
                     f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот для статистики Brawl Stars.\n\n"
                     f"• <b>/profile</b> или <b>бс профиль</b> - узнать инфо об игроке.\n"
                     f"• <b>/leaderboard</b> или <b>бс лидер</b> - посмотреть топы.", parse_mode='HTML')


# --- Логика Minecraft ---
@bot.message_handler(commands=['world'])
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() in ('маин стата', 'майн стата'))
def send_minecraft_stats(message):
    bot.send_chat_action(message.chat.id, 'typing')
    try:
        data = stats_collection.find_one({"_id": "server_main_stats"})
        if not data:
            bot.send_message(message.chat.id,
                             "❌ Данные с сервера Minecraft еще не поступали. Убедитесь, что плагин работает и на сервере есть игроки.")
            return

        # --- Форматирование красивого ответа ---

        # 1. Блоки
        blocks_top_str = "\n".join([f"  • {item['block']}: {item['count']}" for item in data.get('blocks_top', [])])

        # 2. Время игры
        total_playtime_seconds = data.get('total_playtime_ticks', 0) / 20
        days, remainder = divmod(total_playtime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        total_playtime_str = f"{int(days)}д {int(hours)}ч {int(minutes)}м"

        playtime_top_str = ""
        for item in data.get('playtime_top', []):
            pt_seconds = item['time'] / 20
            pt_hours, pt_rem = divmod(pt_seconds, 3600)
            pt_minutes, _ = divmod(pt_rem, 60)
            playtime_top_str += f"  • {item['name']}: {int(pt_hours)}ч {int(pt_minutes)}м\n"

        # 3. Активность и координаты
        last_activity_str = data.get('last_player_activity', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')

        coords_str = "\n".join(
            [f"  • {item['name']}: {item['coords']}" for item in data.get('online_players_coords', [])])
        if not coords_str:
            coords_str = "Никто не разрешил показывать свои координаты."

        # --- Собираем всё вместе ---
        response = (
            f"<b>{EMOJI['pickaxe']} СТАТИСТИКА MINECRAFT СЕРВЕРА</b>\n\n"
            f"<b>Сломано блоков:</b> {data.get('total_blocks_broken', 0)}\n"
            f"<u>Топ-5 сломанных блоков:</u>\n{blocks_top_str}\n\n"
            f"<b>{EMOJI['clock']} Общее время игры:</b> {total_playtime_str}\n"
            f"<u>Топ-5 игроков по времени:</u>\n{playtime_top_str}\n"
            f"<b>Последняя активность:</b> {last_activity_str}\n\n"
            f"<b>{EMOJI['map']} Координаты игроков онлайн:</b>\n{coords_str}"
        )
        bot.send_message(message.chat.id, response, parse_mode='HTML')

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка при получении данных из базы: {e}")


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

        # Полный вывод профиля (как вы и хотели)
        # ... (здесь ваш код для формирования response)
        response = f"<b>{EMOJI['info']} ПРОФИЛЬ: {player.name}</b> (<code>{player.tag}</code>)\n<b>{EMOJI['trophy']} Трофеи:</b> {player.trophies}"
        bot.send_message(message.chat.id, response, parse_mode='HTML')

        # Обновление данных для отслеживания
        tracked_players = load_tracked_players()
        current_time = int(time.time())
        if player.tag not in tracked_players:
            # Игрок новый, создаем для него историю
            tracked_players[player.tag] = {'name': player.name,
                                           'history': [{'timestamp': current_time, 'trophies': player.trophies}]}
            bot.send_message(message.chat.id, f"✅ Игрок <b>{player.name}</b> добавлен в ежечасное отслеживание.",
                             parse_mode='HTML')
        else:
            # Игрок уже есть, просто обновляем имя (вдруг сменил)
            tracked_players[player.tag]['name'] = player.name

        save_tracked_players(tracked_players)

    except Exception as e:
        bot.send_message(message.chat.id, f"{EMOJI['error']} Ошибка: {e}")


# --- 4. ЛОГИКА ЛИДЕРБОРДОВ ---

@bot.message_handler(commands=['leaderboard'])
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith('бс лидер'))
def leaderboard_handler(message):
    text = message.text.lower()

    periods = {
        'день': 86400,
        'неделя': 7 * 86400,
        'месяц': 30 * 86400,
    }

    period_name = text.split(' ')[-1]

    if period_name in periods:
        title = f"за {period_name}"
        period_seconds = periods[period_name]
    else:
        title = "за всё время"
        period_seconds = float('inf')  # Бесконечность для "всего времени"

    send_leaderboard(message.chat.id, period_seconds, title)


def send_leaderboard(chat_id, period_seconds, title):
    bot.send_chat_action(chat_id, 'typing')

    players_data = load_tracked_players()
    now = int(time.time())
    start_boundary = now - period_seconds

    leaderboard = []

    for tag, data in players_data.items():
        history = data.get('history', [])
        if not history:
            continue

        # Находим начальные и конечные кубки
        start_trophies = history[0]['trophies']  # по умолчанию - самые первые
        if period_seconds != float('inf'):
            # Ищем последнюю запись до начала периода
            relevant_history_points = [p['trophies'] for p in history if p['timestamp'] < start_boundary]
            if relevant_history_points:
                start_trophies = relevant_history_points[-1]

        end_trophies = history[-1]['trophies']
        gain = end_trophies - start_trophies

        if gain > 0:
            leaderboard.append({
                'name': data.get('name', tag),
                'gain': gain,
                'current': end_trophies
            })

    if not leaderboard:
        bot.send_message(chat_id, f"Никто не набил кубки {title}.")
        return

    # Сортируем и берем топ-10
    sorted_leaderboard = sorted(leaderboard, key=lambda x: x['gain'], reverse=True)[:10]

    # Формируем сообщение
    response_lines = [f"{EMOJI['crown']} <b>Лидерборд {title.upper()}</b> {EMOJI['crown']}\n"]
    for i, player in enumerate(sorted_leaderboard):
        place_emoji = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f' {i + 1}.')
        response_lines.append(
            f"{place_emoji} <b>{player['name']}</b>: +{player['gain']} {EMOJI['trophy']}\n"
            f"     (всего: {player['current']})"
        )

    bot.send_message(chat_id, "\n".join(response_lines), parse_mode='HTML')


# --- 5. ФОНОВАЯ ЗАДАЧА (ТРЕКЕР) ---
def hourly_tracker():
    print("🚀 Фоновое отслеживание кубков запущено.")
    while True:
        time.sleep(3600)  # Ждем 1 час

        print(f"[{time.ctime()}] Начинаю ежечасную проверку кубков...")
        tracked_players = load_tracked_players()
        if not tracked_players:
            print("Список отслеживания пуст.")
            continue

        now = int(time.time())
        month_ago = now - 31 * 86400  # Для очистки старых данных

        changes_report = []

        for tag, data in tracked_players.items():
            try:
                current_player = bs_client.get_player(tag)
                history = data.get('history', [])

                # Сравниваем с последней записью, если она есть
                if history:
                    trophy_change = current_player.trophies - history[-1]['trophies']
                    if trophy_change > 0:
                        report_line = f" • <b>{current_player.name}</b>: +{trophy_change} {EMOJI['trophy']} (стало {current_player.trophies})"
                        changes_report.append(report_line)

                # ОБНОВЛЕНИЕ ИСТОРИИ
                # 1. Добавляем новую запись
                data.get('history', []).append({'timestamp': now, 'trophies': current_player.trophies})
                # 2. Очищаем записи старше месяца
                data['history'] = [p for p in data['history'] if p['timestamp'] > month_ago]
                # 3. Обновляем имя
                data['name'] = current_player.name

            except Exception as e:
                print(f"Ошибка при проверке тега {tag}: {e}")

        # Отправка отчета администратору, если были изменения
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


# --- 6. ЗАПУСК ---
if __name__ == '__main__':
    tracker_thread = threading.Thread(target=hourly_tracker, daemon=True)
    tracker_thread.start()

    print("✅ Основной бот и фоновый трекер запущены!")
    bot.infinity_polling(timeout=20)
