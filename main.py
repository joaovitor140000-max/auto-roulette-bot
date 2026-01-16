import telebot
import time
import threading
from datetime import datetime
from collections import defaultdict

from config import (
    TELEGRAM_TOKEN,
    CHECK_INTERVAL,
    WINDOW_SIZE,
    CONFIDENCE_THRESHOLD,
    MAX_SIGNALS_PER_HOUR
)

from roulette_api import fetch_numbers
from strategy import classify_columns, confidence_level, roulette_stability

bot = telebot.TeleBot(TELEGRAM_TOKEN)
users = {}
signal_control = defaultdict(lambda: {"hour": None, "count": 0})

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "🤖 Digite o valor da sua banca inicial:")
    bot.register_next_step_handler(message, set_bank)

def set_bank(message):
    try:
        bank = float(message.text.replace(",", "."))
        users[message.chat.id] = {
            "bank": bank,
            "start_bank": bank,
            "active": True
        }
        bot.send_message(
            message.chat.id,
            "🚀 Bot iniciado.\n"
            "Operando somente com sinais ≥ 75% de confiança.\n"
            "Máx. 2 sinais por hora."
        )
        threading.Thread(target=main_loop, args=(message.chat.id,), daemon=True).start()
    except:
        bot.send_message(message.chat.id, "❌ Digite apenas números. Ex: 50")

def main_loop(chat_id):
    while users.get(chat_id, {}).get("active"):
        numbers = fetch_numbers()

        if len(numbers) < WINDOW_SIZE:
            time.sleep(CHECK_INTERVAL)
            continue

        window = numbers[:WINDOW_SIZE]
        cols = classify_columns(window)
        conf = confidence_level(cols)

        stability = roulette_stability(window)
        target = users[chat_id]["start_bank"] * (4 if stability == "quente" else 2)

        now = datetime.now()
        hour_key = now.strftime("%Y-%m-%d %H")

        if signal_control[chat_id]["hour"] != hour_key:
            signal_control[chat_id] = {"hour": hour_key, "count": 0}

        if signal_control[chat_id]["count"] >= MAX_SIGNALS_PER_HOUR:
            time.sleep(CHECK_INTERVAL)
            continue

        if conf < CONFIDENCE_THRESHOLD:
            time.sleep(CHECK_INTERVAL)
            continue

        exclude = min(cols, key=cols.get)
        play = [c for c in [1, 2, 3] if c != exclude]

        bot.send_message(
            chat_id,
            f"🚨 **SINAL DE ALTA PROBABILIDADE**\n\n"
            f"🎯 Colunas: {play}\n"
            f"📊 Confiança: {int(conf * 100)}%\n"
            f"🔥 Status da Roleta: {stability.upper()}\n"
            f"💰 Meta do dia: R${target:.2f}\n"
            f"⏱️ Sinais nesta hora: {signal_control[chat_id]['count'] + 1}/{MAX_SIGNALS_PER_HOUR}"
        )

        signal_control[chat_id]["count"] += 1
        time.sleep(60)

print("🤖 BOT ONLINE")
bot.infinity_polling()
