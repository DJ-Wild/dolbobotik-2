# === ИМПОРТЫ ===
import telebot
import brawlstats
import clashroyale
import os
import json
import re
import threading
import time
from dotenv import load_dotenv

# --- 1. НАСТРОЙКИ ---
load_dotenv()


# Загружаем переменные
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
BRAWLSTARS_API_KEY = os.getenv('BRAWLSTARS_API_KEY')
CLASHROYALE_API_KEY = os.getenv('CLASHROYALE_API_KEY')
ADMIN_CHAT_ID_STR = os.getenv('ADMIN_CHAT_ID')

# ✅ ИСПРАВЛЕНО: Более надежная проверка и выход из программы, если чего-то не хватает
missing_vars = []
if not TELEGRAM_TOKEN: missing_vars.append("TELEGRAM_TOKEN")
if not BRAWLSTARS_API_KEY: missing_vars.append("BRAWLSTARS_API_KEY")
if not CLASHROYALE_API_KEY: missing_vars.append("CLASHROYALE_API_KEY")
if not ADMIN_CHAT_ID_STR: missing_vars.append("ADMIN_CHAT_ID")

if missing_vars:
    print(f"!!! КРИТИЧЕСКАЯ ОШИБКА: Следующие переменные не найдены в вашем .env файле или системных переменных:")
    for var in missing_vars:
        print(f" - {var}")
    exit() # Завершаем работу, если нет ключей

# Теперь мы уверены, что ADMIN_CHAT_ID_STR существует
ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_STR)

bot = telebot.TeleBot(TELEGRAM_TOKEN, skip_pending=True)
# ✅ КЛИЕНТ ДЛЯ BRAWL STARS ОСТАЕТСЯ, ТАК КАК ОН РАБОТАЕТ
cr_client = clashroyale.official_api.Client(token=CLASHROYALE_API_KEY)
bs_client = brawlstats.Client(BRAWLSTARS_API_KEY, load_brawlers_on_init=False)
# --- Хранилище и эмодзи ---
TRACKED_PLAYERS_FILE = 'tracked_players.json'
EMOJI = {'trophy': '🏆', 'star': '⭐', 'level': '📊', 'victory': '✅', 'club': '🏰', 'brawler': '🤖', 'error': '❌',
         'info': 'ℹ️', 'card': '🃏', 'crown': '👑', 'chart': '📈'}


# --- 2. ФУНКЦИИ ДЛЯ РАБОТЫ С JSON ---
def load_tracked_players():
    try:
        with open(TRACKED_PLAYERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        save_tracked_players({})
        return {}


def save_tracked_players(players_data):
    with open(TRACKED_PLAYERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(players_data, f, indent=4, ensure_ascii=False)


# --- 3. ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, f"👋 Привет, {message.from_user.first_name}!\n\n"
                                      f"Я бот для игровой статистики. Чтобы узнать профиль, введите команду и тег, например:\n\n"
                                      f"• <code>/profilebs #TAG</code>\n"
                                      f"• <code>/profilecr #TAG</code>\n\n"
                                      f"<b>Лидерборды:</b>\n"
                                      f"• <code>бс лидер [день/неделя]</code>\n"
                                      f"• <code>клэш лидер [день/неделя]</code>", parse_mode='HTML')


# --- Логика Brawl Stars (без изменений) ---
@bot.message_handler(commands=['profilebs'])
def send_bs_profile(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Пожалуйста, укажите тег после команды.\nПример: `/profilebs #2G98QY98`",
                         parse_mode='Markdown')
            return
        tag = parts[1].strip().upper().replace('O', '0')
        if not tag.startswith('#'): tag = '#' + tag

        bot.send_chat_action(message.chat.id, 'typing')
        player = bs_client.get_player(tag)  # Используем старый, рабочий клиент

        # ... (остальной код для BS без изменений)
        club_info = f"{player.club.name} ({player.club.tag})" if player.club else "Не состоит"
        top_brawlers = sorted(player.brawlers, key=lambda b: b.trophies, reverse=True)[:5]
        brawlers_list = [f"{i + 1}. {b.name.ljust(12)} {EMOJI['trophy']} {str(b.trophies).rjust(4)} | Rank: {b.rank}"
                         for i, b in enumerate(top_brawlers)]
        brawlers_text = "<pre>" + "\n".join(brawlers_list) + "</pre>"

        response = (
            f"<b>{EMOJI['brawler']} ПРОФИЛЬ BRAWL STARS</b>\n\n<b>Имя:</b> {player.name}\n<b>Тег:</b> <code>{player.tag}</code>\n\n"
            f"<b>{EMOJI['trophy']} Трофеи:</b> {player.trophies}\n<b>{EMOJI['star']} Рекорд:</b> {player.highest_trophies}\n<b>{EMOJI['level']} Уровень:</b> {player.exp_level}\n\n"
            f"<b>{EMOJI['victory']} Победы 3v3:</b> {player.x3v3_victories}\n<b>{EMOJI['victory']} Solo/Duo:</b> {player.solo_victories} / {player.duo_victories}\n\n"
            f"<b>{EMOJI['club']} Клуб:</b> {club_info}\n\n<b>Топ-5 бравлеров:</b>\n{brawlers_text}")
        bot.send_message(message.chat.id, response, parse_mode='HTML')

        # Добавляем в отслеживание
        tracked_players = load_tracked_players()
        if tag not in tracked_players:
            tracked_players[tag] = {'name': player.name, 'game': 'brawlstars',
                                    'history': [{'timestamp': int(time.time()), 'trophies': player.trophies}]}
            bot.send_message(message.chat.id, f"✅ Игрок <b>{player.name}</b> (Brawl Stars) добавлен в отслеживание.",
                             parse_mode='HTML')
        else:
            tracked_players[tag].update({'name': player.name, 'game': 'brawlstars'})
        save_tracked_players(tracked_players)

    except brawlstats.errors.NotFoundError:
        bot.reply_to(message, f"{EMOJI['error']} Игрок Brawl Stars с тегом <code>{tag}</code> не найден.",
                     parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"{EMOJI['error']} Ошибка: {e}")

    except brawlstats.errors.NotFoundError:
        bot.reply_to(message, f"{EMOJI['error']} Игрок Brawl Stars с тегом <code>{tag}</code> не найден.",
                     parse_mode='HTML')
    except Exception as e:
        bot.reply_to(message, f"{EMOJI['error']} Произошла непредвиденная ошибка: {e}")


# --- Логика Clash Royale (полностью переписана под правильную библиотеку) ---
@bot.message_handler(commands=['profilecr'])
def send_cr_profile(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Пример: `/profilecr #8L9L9GL`", parse_mode='Markdown')
            return
        tag = parts[1].strip().upper().replace('O', '0')
        if not tag.startswith('#'): tag = '#' + tag        
        bot.send_chat_action(message.chat.id, 'typing')
        
        # ✅✅✅ ПРАВИЛЬНЫЙ ВЫЗОВ СОГЛАСНО ДОКУМЕНТАЦИИ ✅✅✅
        # Мы просто вызываем функцию из модуля, передавая токен каждый раз.
        player = cr_client.get_player(tag)
        club_info = f"{player.clan.name} ({player.clan.tag})" if player.clan else "Не состоит"
        current_deck = ", ".join([card.name for card in player.current_deck])

        response = (f"<b>{EMOJI['crown']} ПРОФИЛЬ CLASH ROYALE</b>\n\n<b>Имя:</b> {player.name}\n<b>Тег:</b> <code>{player.tag}</code>\n\n"
                    f"<b>{EMOJI['trophy']} Трофеи:</b> {player.trophies}\n<b>{EMOJI['star']} Рекорд:</b> {player.best_trophies}\n<b>{EMOJI['level']} Уровень:</b> {player.exp_level}\n\n"
                    f"<b>{EMOJI['victory']} Победы/Поражения:</b> {player.wins} / {player.losses}\n\n"
                    f"<b>{EMOJI['club']} Клан:</b> {club_info}\n\n<b>{EMOJI['card']} Текущая колода:</b>\n<pre>{current_deck}</pre>")
        bot.send_message(message.chat.id, response, parse_mode='HTML')

        # Добавляем в отслеживание
        tracked_players = load_tracked_players()
        if tag not in tracked_players:
            tracked_players[tag] = {'name': player.name, 'game': 'clashroyale', 'history': [{'timestamp': int(time.time()), 'trophies': player.trophies}]}
            bot.send_message(message.chat.id, f"✅ Игрок <b>{player.name}</b> (Clash Royale) добавлен в отслеживание.", parse_mode='HTML')
        else:
            tracked_players[tag].update({'name': player.name, 'game': 'clashroyale'})
        save_tracked_players(tracked_players)

    except clashroyale.NotFoundError:
        bot.reply_to(message, f"{EMOJI['error']} Игрок Clash Royale с тегом <code>{tag}</code> не найден.", parse_mode='HTML')
    except clashroyale.RequestError as e:
        bot.reply_to(message, f"{EMOJI['error']} Ошибка API Clash Royale: {e}")
    except Exception as e:
        bot.reply_to(message, f"{EMOJI['error']} Произошла непредвиденная ошибка: {e}")

# --- ✅ ВОЗВРАЩАЕМ ЛИДЕРБОРДЫ ---
@bot.message_handler(
    func=lambda msg: msg.text and msg.text.lower().startswith(('бс лидер', 'клэш лидер', 'клеш лидер')))
def leaderboard_handler(message):
    text = message.text.lower()

    if text.startswith('бс лидер'):
        game, game_name = 'brawlstars', 'Brawl Stars'
        period_name = text.replace('бс лидер', '').strip()
    else:
        game, game_name = 'clashroyale', 'Clash Royale'
        period_name = text.replace('клэш лидер', '').replace('клеш лидер', '').strip()

    periods = {'день': 86400, 'неделя': 7 * 86400, 'месяц': 30 * 86400}

    if period_name in periods:
        title, period_seconds = f"за {period_name}", periods[period_name]
    else:
        title, period_seconds = "за всё время", float('inf')

    send_leaderboard(message.chat.id, period_seconds, title, game, game_name)


def send_leaderboard(chat_id, period_seconds, title, game, game_name):
    bot.send_chat_action(chat_id, 'typing')
    players_data = load_tracked_players()
    now = int(time.time())
    start_boundary = now - period_seconds
    leaderboard = []

    for tag, data in players_data.items():
        if data.get('game') != game:
            continue
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
        bot.send_message(chat_id, f"Никто не набил кубки в {game_name} {title}.")
        return

    sorted_leaderboard = sorted(leaderboard, key=lambda x: x['gain'], reverse=True)[:10]
    response_lines = [f"{EMOJI['crown']} <b>Лидерборд {game_name.upper()} {title.upper()}</b> {EMOJI['crown']}\n"]
    for i, player in enumerate(sorted_leaderboard):
        place_emoji = {0: '🥇', 1: '🥈', 2: '🥉'}.get(i, f' {i + 1}.')
        response_lines.append(
            f"{place_emoji} <b>{player['name']}</b>: +{player['gain']} {EMOJI['trophy']} (всего: {player['current']})")

    bot.send_message(chat_id, "\n".join(response_lines), parse_mode='HTML')


# --- ✅ ВОЗВРАЩАЕМ ЕЖЕЧАСОВЫЙ ТРЕКЕР ---
def hourly_tracker():
    print("🚀 Мульти-игровой трекер запущен.")
    while True:
        time.sleep(3600)

        print(f"[{time.ctime()}] Начинаю ежечасную проверку кубков...")
        tracked_players = load_tracked_players()
        if not tracked_players:
            print("Список отслеживания пуст.")
            continue

        now = int(time.time())
        month_ago = now - 31 * 86400
        bs_changes_report = []
        cr_changes_report = []

        for tag, data in tracked_players.items():
            try:
                game_type = data.get('game')
                history = data.get('history', [])
                if not history: continue

                trophy_change = 0
                current_trophies = 0
                current_name = data.get('name', tag)

                if game_type == 'brawlstars':
                    player = bs_client.get_player(tag)
                    current_trophies = player.trophies
                    current_name = player.name
                    trophy_change = current_trophies - history[-1]['trophies']
                    if trophy_change > 0:
                        bs_changes_report.append(
                            f" • <b>{current_name}</b>: +{trophy_change} {EMOJI['trophy']} (стало {current_trophies})")
                elif game_type == 'clashroyale':
                    player = cr_client.get_player(tag)
                    current_trophies = player.trophies
                    current_name = player.name
                    trophy_change = current_trophies - history[-1]['trophies']
                    if trophy_change > 0:
                        cr_changes_report.append(
                            f" • <b>{current_name}</b>: +{trophy_change} {EMOJI['trophy']} (стало {current_trophies})")
                else:
                    continue

                data['name'] = current_name
                if not history or history[-1].get('trophies') != current_trophies:
                    data['history'].append({'timestamp': now, 'trophies': current_trophies})
                data['history'] = [p for p in data['history'] if p['timestamp'] > month_ago]

            except Exception as e:
                print(f"Ошибка при проверке тега {tag} ({data.get('game')}): {e}")

        if bs_changes_report:
            header = f"{EMOJI['chart']} <b>Ежечасный отчет BRAWL STARS:</b>\n\n"
            full_report = header + "\n".join(bs_changes_report)
            bot.send_message(ADMIN_CHAT_ID, full_report, parse_mode='HTML')
            print("Отчет об изменениях в BS отправлен.")

        if cr_changes_report:
            header = f"{EMOJI['chart']} <b>Ежечасный отчет CLASH ROYALE:</b>\n\n"
            full_report = header + "\n".join(cr_changes_report)
            bot.send_message(ADMIN_CHAT_ID, full_report, parse_mode='HTML')
            print("Отчет об изменениях в CR отправлен.")

        save_tracked_players(tracked_players)
        print("Проверка завершена.")


# --- 4. ГЛАВНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    # Удаляем старый файл, если он есть, т.к. структура могла измениться
    # if os.path.exists(TRACKED_PLAYERS_FILE):
    #     os.remove(TRACKED_PLAYERS_FILE)

    tracker_thread = threading.Thread(target=hourly_tracker, daemon=True)
    tracker_thread.start()

    print("✅ Бот (ПОЛНАЯ ВЕРСИЯ BS + CR) запущен!")
    bot.infinity_polling(timeout=30)
