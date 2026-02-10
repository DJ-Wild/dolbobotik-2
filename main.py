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
from flask import Flask  # Для веб-сервера 24/7

# --- 1. НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ ---
# В Replit эти переменные будут браться из Secrets
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BRAWLSTARS_API_KEY = os.getenv('BRAWLSTARS_API_KEY')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID'))

if not all([TELEGRAM_TOKEN, BRAWLSTARS_API_KEY, ADMIN_CHAT_ID]):
    raise ValueError(
        "ОШИБКА: Не найдены ключи! Убедитесь, что вы добавили TELEGRAM_TOKEN, BRAWLSTARS_API_KEY и ADMIN_CHAT_ID в 'Secrets' слева."
    )

bot = telebot.TeleBot(TELEGRAM_TOKEN, skip_pending=True)
bs_client = brawlstats.Client(BRAWLSTARS_API_KEY, load_brawlers_on_init=False)
TRACKED_PLAYERS_FILE = 'tracked_players.json'
EMOJI = {
    'trophy': '🏆',
    'star': '⭐',
    'level': '📊',
    'victory': '✅',
    'club': '🏰',
    'brawler': '🤖',
    'error': '❌',
    'info': 'ℹ️',
    'chart': '📈',
    'crown': '👑'
}


# --- 2. ФУНКЦИИ ДЛЯ РАБОТЫ С JSON ---
def load_tracked_players():
    try:
        with open(TRACKED_PLAYERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Если файла нет, создаем его с пустой структурой
        save_tracked_players({})
        return {}


def save_tracked_players(players_data):
    with open(TRACKED_PLAYERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(players_data, f, indent=4, ensure_ascii=False)


# --- 3. ОБРАБОТЧИКИ КОМАНД TELEGRAM ---


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот для статистики Brawl Stars.\n\n"
        f"• <b>/profile</b> или <b>бс профиль</b> - узнать инфо об игроке.\n"
        f"• <b>/leaderboard</b> или <b>бс лидер</b> - посмотреть топы.",
        parse_mode='HTML')


@bot.message_handler(commands=['profile'])
@bot.message_handler(func=lambda message: message.text and message.text.lower(
) in ('бс профиль', 'профиль'))
def request_player_tag(message):
    markup = types.ForceReply(
        selective=False,
        input_field_placeholder='Введите тег, например: #2G98QY98')
    bot.send_message(message.chat.id,
                     f"{EMOJI['info']} Введите тег игрока Brawl Stars:",
                     reply_markup=markup)
    bot.register_next_step_handler(message, process_player_tag)


def process_player_tag(message):
    try:
        tag = message.text.strip().upper().replace('O', '0')
        if not tag.startswith('#'): tag = '#' + tag
        if not re.match(r'^#[0289PYLQGRJCUV]{3,}$', tag):
            raise ValueError("Неверный формат тега")
    except (AttributeError, ValueError):
        bot.send_message(
            message.chat.id,
            f"{EMOJI['error']} Неверный формат тега!\nПример: #2G98QY98")
        return

    bot.send_chat_action(message.chat.id, 'typing')
    try:
        player = bs_client.get_player(tag)

        # === ПОЛНЫЙ ВЫВОД ПРОФИЛЯ (КАК ВЫ ПРОСИЛИ) ===
        club_info = f"{player.club.name} ({player.club.tag})" if player.club else "Не состоит"
        top_brawlers = sorted(player.brawlers,
                              key=lambda b: b.trophies,
                              reverse=True)[:5]
        brawlers_list = [
            f"{i+1}. {b.name.ljust(12)} {EMOJI['trophy']} {str(b.trophies).rjust(4)} | Rank: {b.rank}"
            for i, b in enumerate(top_brawlers)
        ]
        brawlers_text = "<pre>" + "\n".join(brawlers_list) + "</pre>"

        response = (
            f"<b>{EMOJI['info']} ПРОФИЛЬ BRAWL STARS</b>\n\n"
            f"<b>Имя:</b> {player.name}\n"
            f"<b>Тег:</b> <code>{player.tag}</code>\n\n"
            f"<b>{EMOJI['trophy']} Трофеи:</b> {player.trophies}\n"
            f"<b>{EMOJI['star']} Рекорд:</b> {player.highest_trophies}\n"
            f"<b>{EMOJI['level']} Уровень:</b> {player.exp_level}\n\n"
            f"<b>{EMOJI['victory']} Победы 3v3:</b> {player.x3v3_victories}\n"
            f"<b>{EMOJI['victory']} Solo/Duo:</b> {player.solo_victories} / {player.duo_victories}\n\n"
            f"<b>{EMOJI['club']} Клуб:</b> {club_info}\n\n"
            f"<b>{EMOJI['brawler']} Топ-5 бравлеров:</b>\n{brawlers_text}")
        bot.send_message(message.chat.id, response, parse_mode='HTML')

        # Обновление данных для отслеживания
        tracked_players = load_tracked_players()
        current_time = int(time.time())
        if player.tag not in tracked_players:
            tracked_players[player.tag] = {
                'name':
                player.name,
                'history': [{
                    'timestamp': current_time,
                    'trophies': player.trophies
                }]
            }
            bot.send_message(
                message.chat.id,
                f"✅ Игрок <b>{player.name}</b> добавлен в ежечасное отслеживание.",
                parse_mode='HTML')
        else:
            tracked_players[player.tag]['name'] = player.name
        save_tracked_players(tracked_players)

    except Exception as e:
        bot.send_message(message.chat.id, f"{EMOJI['error']} Ошибка: {e}")


# ... (Весь код лидербордов остается здесь без изменений) ...
# ... (функция leaderboard_handler и send_leaderboard)


# --- 5. ФОНОВАЯ ЗАДАЧА (ТРЕКЕР) ---
# === ЕЖЕЧАСОВЫЙ ОТЧЕТ (КАК ВЫ ПРОСИЛИ) ===
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
        month_ago = now - 31 * 86400
        changes_report = []

        for tag, data in tracked_players.items():
            try:
                current_player = bs_client.get_player(tag)
                history = data.get('history', [])

                if history:
                    trophy_change = current_player.trophies - history[-1][
                        'trophies']
                    if trophy_change > 0:
                        report_line = f" • <b>{current_player.name}</b>: +{trophy_change} {EMOJI['trophy']} (стало {current_player.trophies})"
                        changes_report.append(report_line)

                data.get('history', []).append({
                    'timestamp':
                    now,
                    'trophies':
                    current_player.trophies
                })
                data['history'] = [
                    p for p in data['history'] if p['timestamp'] > month_ago
                ]
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

# --- БЛОК ДЛЯ 24/7 РАБОТЫ ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is alive and running!" # Ответ для UptimeRobot

def run_bot_polling():
    """Запускает и бота, и ежечасный трекер в одном потоке."""
    print("Запускаю фоновый поток для бота...")

    # Сначала запускаем ежечасный трекер как дочерний поток
    tracker_thread = threading.Thread(target=hourly_tracker, daemon=True)
    tracker_thread.start()

    # Затем в этом же потоке запускаем бесконечный цикл бота
    print("✅ Основной бот запущен и ждет команд!")
    bot.infinity_polling()

# --- ГЛАВНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    # 1. Запускаем ВСЮ логику бота (поллинг + трекер) в отдельном фоновом потоке
    bot_thread = threading.Thread(target=run_bot_polling)
    bot_thread.start()

    # 2. А основной поток теперь целиком отдан под веб-сервер, который "видит" Replit
    print("Веб-сервер для UptimeRobot запущен.")
    app.run(host='0.0.0.0', port=8080)
