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

from flask import Flask

# ==============================
# FLASK KEEP ALIVE (REPLIT)
# ==============================
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 BOT ONLINE 24H", 200

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ==============================
# TELEGRAM BOT
# ==============================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

users = {}
signal_control = defaultdict(lambda: {"hour": None, "count": 0})
last_analysis = {}

# ==============================
# START
# ==============================
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 **Bot de Roleta Automática**\n\n"
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
            "🚀 Bot iniciado com sucesso.\n\n"
            "✔️ Apenas sinais ≥ 75%\n"
            "✔️ Máx. 2 sinais por hora\n"
            "✔️ Proteção de banca ativa\n\n"
            "Use /status para acompanhar o funcionamento."
        )

        threading.Thread(
            target=main_loop,
            args=(message.chat.id,),
            daemon=True
        ).start()

    except:
        bot.send_message(message.chat.id, "❌ Digite apenas números. Ex: 50")

# ==============================
# STATUS
# ==============================
@bot.message_handler(commands=["status"])
def status(message):
    chat_id = message.chat.id

    if chat_id not in users:
        bot.send_message(chat_id, "❌ Bot não iniciado. Use /start")
        return

    data = last_analysis.get(chat_id)

    if not data:
        bot.send_message(
            chat_id,
            "⏳ Ainda não há análise registrada.\n"
            "Aguardando dados da roleta..."
        )
        return

    bot.send_message(
        chat_id,
        "📊 **STATUS DO BOT**\n\n"
        f"🕒 Última análise: {data['time']}\n"
        f"🎲 Últimos números: {data['numbers']}\n"
        f"📊 Colunas: {data['cols']}\n"
        f"📈 Confiança: {data['conf']}%\n"
        f"🔥 Roleta: {data['stability'].upper()}\n"
    )

# ==============================
# LOOP PRINCIPAL
# ==============================
def main_loop(chat_id):
    print(f"[INFO] Loop iniciado para usuário {chat_id}")

    while users.get(chat_id, {}).get("active"):

        try:
            numbers = fetch_numbers()

            if not numbers or len(numbers) < WINDOW_SIZE:
                time.sleep(CHECK_INTERVAL)
                continue

            window = numbers[:WINDOW_SIZE]
            cols = classify_columns(window)
            conf = confidence_level(cols)
            stability = roulette_stability(window)

            # LOG VISUAL (PROVA DE FUNCIONAMENTO)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Números: {window} | "
                f"Colunas: {cols} | "
                f"Confiança: {int(conf*100)}% | "
                f"Status: {stability.upper()}"
            )

            # salva última análise
            last_analysis[chat_id] = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "numbers": ", ".join(map(str, window[:10])),
                "cols": cols,
                "conf": int(conf * 100),
                "stability": stability
            }

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

            exclude = min(cols, key=lambda x: cols[x])
            play = [c for c in [1, 2, 3] if c != exclude]

            target = users[chat_id]["start_bank"] * (4 if stability == "quente" else 2)

            bot.send_message(
                chat_id,
                "🚨 **SINAL CONFIRMADO (≥75%)**\n\n"
                f"🎯 Colunas: {play}\n"
                f"📈 Confiança: {int(conf*100)}%\n"
                f"🔥 Roleta: {stability.upper()}\n"
                f"💰 Meta do dia: R${target:.2f}\n"
                f"⏱️ Hora atual: {signal_control[chat_id]['count']+1}/{MAX_SIGNALS_PER_HOUR}"
            )

            signal_control[chat_id]["count"] += 1
            time.sleep(60)

        except Exception as e:
            print(f"[ERRO] Loop principal: {e}")
            time.sleep(10)

# ==============================
# START SYSTEM
# ==============================
if __name__ == "__main__":
    print("🤖 BOT ONLINE 24H")

    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
