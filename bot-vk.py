import telebot
import requests
import urllib.parse
import yt_dlp
import os
import threading
import time

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = '8419344748:AAGj23nEdS4b48rvjJleK8lhDR0Bc5dHTLQ'  # ← ОБЯЗАТЕЛЬНО новый!
SOUNDCLOUD_CLIENT_ID = 'knW1rrkzZq7EKRs3wY0k0hqDxv1AqnTs'
DOWNLOAD_DIR = 'downloads'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Хранилище последних результатов по chat_id
user_search_results = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Привет! Напиши .song название — найду на SoundCloud.\nПосле получения списка напиши цифру (1-10), чтобы скачать трек.")

from html import escape

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('.song '))
def search_soundcloud(message):
    query = message.text[6:].strip()
    if not query:
        return bot.reply_to(message, "Напиши .song название")

    try:
        bot.send_message(message.chat.id, "🔍 Ищу на SoundCloud...")

        encoded_query = urllib.parse.quote(query)
        url = f"https://api-v2.soundcloud.com/search/tracks?q={encoded_query}&limit=10&client_id={SOUNDCLOUD_CLIENT_ID}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        tracks = data.get('collection', [])

        if not tracks:
            return bot.send_message(message.chat.id, "Ничего не найдено 😢")

        # Сохраняем результаты для этого чата
        user_search_results[message.chat.id] = tracks[:10]

        result_text = f"Результаты по запросу: <b>{escape(query)}</b>\n\n"
        for i, track in enumerate(tracks[:10], 1):
            title = track.get('title', '—')
            artist = track.get('user', {}).get('username', '—')
            track_url = track.get('permalink_url', '')
            
            if track_url:
                result_text += f'{i}. <a href="{track_url}">{escape(artist)} – {escape(title)}</a>\n'
            else:
                result_text += f'{i}. {escape(artist)} – {escape(title)}\n'

        result_text += "\nНапиши номер трека (1-10), чтобы скачать его."
        bot.send_message(
            message.chat.id,
            result_text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        print(f"❌ Поиск: {e}")
        bot.send_message(message.chat.id, "Ошибка поиска. Попробуй позже.")
# Обработчик цифр 1-10
@bot.message_handler(func=lambda msg: msg.text and msg.text.isdigit())
def handle_track_number(message):
    chat_id = message.chat.id
    if chat_id not in user_search_results:
        return bot.reply_to(message, "Сначала выполни поиск через .song")

    number = int(message.text)
    if number < 1 or number > 10:
        return bot.reply_to(message, "Напиши число от 1 до 10")

    tracks = user_search_results[chat_id]
    if number > len(tracks):
        return bot.reply_to(message, f"В списке всего {len(tracks)} треков.")

    track = tracks[number - 1]
    track_url = track.get('permalink_url')
    if not track_url:
        return bot.reply_to(message, "Не удалось получить ссылку на трек.")

    bot.send_message(chat_id, "⬇️ Скачиваю трек... Это может занять 10–30 секунд.")

    # Запускаем скачивание в отдельном потоке, чтобы не блокировать бота
    thread = threading.Thread(target=download_and_send, args=(track_url, chat_id, track))
    thread.start()

def download_and_send(track_url, chat_id, track):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Генерируем уникальное имя файла
            track_id = track.get('id', hash(track_url))
            temp_path = os.path.join(DOWNLOAD_DIR, f"{track_id}")

            ydl_opts = {
                'format': 'bestaudio[ext=mp3]/bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'outtmpl': temp_path + '.%(ext)s',
                'quiet': False,  # ← Временно для отладки
                'nocheckcertificate': True,
                'retries': 5,
                'fragment_retries': 5,
                'skip_unavailable_fragments': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                },
                'extractor_args': {
                    'soundcloud': {
                        'client_id': [SOUNDCLOUD_CLIENT_ID]
                    }
                }
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(track_url, download=True)
                mp3_file = temp_path + '.mp3'

            if not os.path.exists(mp3_file):
                raise FileNotFoundError("MP3 файл не создан")

            title = track.get('title', 'Трек')
            artist = track.get('user', {}).get('username', 'Неизвестен')

            with open(mp3_file, 'rb') as audio:
                bot.send_audio(
                    chat_id,
                    audio,
                    title=title[:30],        # Telegram ограничивает длину
                    performer=artist[:30],
                    timeout=120
                )

            os.remove(mp3_file)
            return  # Успех — выходим

        except Exception as e:
            print(f"❌ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
            if attempt == max_retries - 1:
                bot.send_message(chat_id, "Не удалось скачать трек. SoundCloud может блокировать запросы из вашего региона.")
            else:
                time.sleep(3)  # Пауза перед повтором

    # Удаляем временные файлы, если остались
    for ext in ['.webm', '.m4a', '.mp3', '.opus']:
        f = temp_path + ext
        if os.path.exists(f):
            os.remove(f)

if __name__ == '__main__':
    print("✅ Бот запущен...")
    bot.polling(none_stop=True)