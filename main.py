import telebot
import time
import threading
from datetime import datetime
from collections import defaultdict
from flask import Flask

from config import (
    TELEGRAM_TOKEN,
    CHECK_INTERVAL,
    WINDOW_SIZE,
    CONFIDENCE_THRESHOLD,
    MAX_SIGNALS_PER_HOUR
)

from roulette_api import fetch_numbers
from strategy import classify_columns, confidence_level, roulette_stability

# =====================
# TELEGRAM BOT
# =====================
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")
users = {}
signal_control = defaultdict(lambda: {"hour": None, "count": 0})

# =====================
# FLASK (KEEP ALIVE)
# =====================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 Auto Roulette Bot Online"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# =====================
# TELEGRAM HANDLERS
# =====================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 *Auto Roulette Bot*\n\n"
        "Digite o valor da sua banca inicial:"
    )
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
            "🚀 *Bot iniciado com sucesso*\n\n"
            "✔ Apenas sinais ≥ 75%\n"
            "✔ Máx. 2 sinais por hora\n"
            "✔ Meta dinâmica (2x ou 4x)\n"
        )

        threading.Thread(
            target=main_loop,
            args=(message.chat.id,),
            daemon=True
        ).start()

    except:
        bot.send_message(
            message.chat.id,
            "❌ Valor inválido.\nExemplo correto: 50"
        )

# =====================
# MAIN LOOP
# =====================
def main_loop(chat_id):
    while users.get(chat_id, {}).get("active", False):
        try:
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
                f"🚨 *SINAL DE ALTA PROBABILIDADE*\n\n"
                f"🎯 *Colunas:* {play}\n"
                f"📊 *Confiança:* {int(conf * 100)}%\n"
                f"🔥 *Roleta:* {stability.upper()}\n"
                f"💰 *Meta do dia:* R${target:.2f}\n"
                f"⏱️ *Sinais nesta hora:* "
                f"{signal_control[chat_id]['count'] + 1}/{MAX_SIGNALS_PER_HOUR}"
            )

            signal_control[chat_id]["count"] += 1
            time.sleep(60)

        except Exception as e:
            print("Erro no loop:", e)
            time.sleep(10)

# =====================
# START EVERYTHING
# =====================
if __name__ == "__main__":
    print("🤖 BOT ONLINE 24H")

    threading.Thread(target=run_flask, daemon=True).start()

    bot.infinity_polling(
        timeout=60,
        long_polling_timeout=60
    )
