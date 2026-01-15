import os
import time
import threading
import requests
import numpy as np
from datetime import datetime
from flask import Flask
import telebot
from sklearn.linear_model import LogisticRegression

# =====================================================
# CONFIGURAÇÕES GERAIS (ENV)
# =====================================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
ROULETTE_API = os.getenv("ROULETTE_API_URL")
BOT_MODE = os.getenv("BOT_MODE", "ALERTA")  # ALERTA ou OPERACAO

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# =====================================================
# ESTADO GLOBAL
# =====================================================
user_data = {}
ml_model = LogisticRegression()
ml_trained = False

dashboard_state = {
    "market_mode": "ANALISANDO",
    "session": "-",
    "entries_today": 0,
    "winrate": 0,
    "ml_prob": 0,
    "last_update": "-"
}

# =====================================================
# DASHBOARD WEB
# =====================================================
@app.route("/")
def home():
    return "BOT AUTO ROULETTE ONLINE", 200

@app.route("/dashboard")
def dashboard():
    return f"""
    <html>
    <head>
        <title>Auto Roulette Dashboard</title>
        <meta http-equiv="refresh" content="15">
        <style>
            body {{
                background:#0f172a;
                color:#e5e7eb;
                font-family:Arial;
                padding:20px;
            }}
            .card {{
                background:#020617;
                padding:15px;
                border-radius:8px;
                margin-bottom:10px;
            }}
            h2 {{ color:#38bdf8; }}
        </style>
    </head>
    <body>
        <h2>🎰 AUTO ROULETTE – DASHBOARD</h2>
        <div class="card">📊 Mercado: <b>{dashboard_state['market_mode']}</b></div>
        <div class="card">⏰ Sessão: <b>{dashboard_state['session']}</b></div>
        <div class="card">🎯 Entradas hoje: <b>{dashboard_state['entries_today']}</b></div>
        <div class="card">📈 Winrate: <b>{dashboard_state['winrate']}%</b></div>
        <div class="card">🤖 ML Prob: <b>{dashboard_state['ml_prob']}%</b></div>
        <div class="card">🕒 Atualizado: <b>{dashboard_state['last_update']}</b></div>
    </body>
    </html>
    """

# =====================================================
# UTILIDADES
# =====================================================
def current_session():
    h = datetime.now().hour
    if 9 <= h < 12:
        return "MANHA"
    if 14 <= h < 17:
        return "TARDE"
    if 19 <= h < 22:
        return "NOITE"
    return None

def fetch_numbers(limit=72):
    try:
        r = requests.get(
            ROULETTE_API,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://casinoscores.com"
            },
            timeout=10
        )
        data = r.json()
        history = data.get("data") or data.get("history") or []
        nums = []
        for item in history[:limit]:
            n = item.get("result") or item.get("number")
            if n is not None:
                nums.append(int(n))
        return nums
    except:
        return []

# =====================================================
# ANÁLISE ESTATÍSTICA AVANÇADA
# =====================================================
def analyze_advanced(numbers):
    if len(numbers) < 24:
        return None

    last_24 = numbers[:24]
    last_6 = numbers[:6]

    valid = [n for n in last_24 if n != 0]
    freq = {
        1: len([n for n in valid if n % 3 == 1]),
        2: len([n for n in valid if n % 3 == 2]),
        3: len([n for n in valid if n % 3 == 0])
    }

    diff = max(freq.values()) - min(freq.values())
    if diff < 4:
        return None

    min_col = min(freq, key=freq.get)
    short_hits = len([n for n in last_6 if n != 0 and (n % 3 or 3) == min_col])
    if short_hits >= 2:
        return None

    if last_24.count(0) >= 2:
        return None

    confidence = diff / len(valid)
    if confidence < 0.62:
        return None

    play_cols = [c for c in [1, 2, 3] if c != min_col]
    return play_cols, confidence

# =====================================================
# BACKTEST CURTO
# =====================================================
def backtest_strategy(history):
    wins = losses = 0
    max_loss_seq = cur_loss = 0

    for i in range(36, len(history) - 2):
        window = history[i-36:i]
        analysis = analyze_advanced(window)
        if not analysis:
            continue

        cols, _ = analysis
        r1 = history[i]
        r2 = history[i+1]

        def hit(r):
            if r == 0:
                return True
            return (r % 3 or 3) in cols

        if hit(r1) or hit(r2):
            wins += 1
            cur_loss = 0
        else:
            losses += 1
            cur_loss += 1
            max_loss_seq = max(max_loss_seq, cur_loss)

    total = wins + losses
    if total == 0:
        return None

    return {
        "winrate": round(wins / total, 3),
        "max_loss": max_loss_seq
    }

# =====================================================
# ML LEVE (CONFIRMAÇÃO)
# =====================================================
def build_features(history):
    last = history[:36]
    valid = [n for n in last if n != 0]

    freq = [
        len([n for n in valid if n % 3 == 1]),
        len([n for n in valid if n % 3 == 2]),
        len([n for n in valid if n % 3 == 0])
    ]

    diff = max(freq) - min(freq)
    zero_rate = last.count(0) / len(last)
    volatility = np.std(freq)

    return [diff, zero_rate, volatility]

def train_ml(samples):
    global ml_trained
    X, y = [], []
    for h, res in samples:
        X.append(build_features(h))
        y.append(res)
    ml_model.fit(X, y)
    ml_trained = True

def ml_predict(history):
    if not ml_trained:
        return 0
    feat = np.array(build_features(history)).reshape(1, -1)
    return ml_model.predict_proba(feat)[0][1]

# =====================================================
# LOOP PRINCIPAL
# =====================================================
def signal_loop(chat_id):
    last_number = None

    while chat_id in user_data:
        session = current_session()
        dashboard_state["session"] = session or "-"

        if not session:
            time.sleep(60)
            continue

        numbers = fetch_numbers()
        if not numbers or numbers[0] == last_number:
            time.sleep(20)
            continue

        last_number = numbers[0]

        bt = backtest_strategy(numbers)
        if not bt or bt["winrate"] < 0.58 or bt["max_loss"] >= 4:
            dashboard_state["market_mode"] = "STOP"
            time.sleep(60)
            continue

        analysis = analyze_advanced(numbers)
        if not analysis:
            time.sleep(30)
            continue

        cols, conf = analysis
        ml_prob = ml_predict(numbers)

        if ml_prob < 0.65:
            time.sleep(30)
            continue

        dashboard_state.update({
            "market_mode": "ATIVO",
            "entries_today": dashboard_state["entries_today"] + 1,
            "winrate": int(bt["winrate"] * 100),
            "ml_prob": int(ml_prob * 100),
            "last_update": datetime.now().strftime("%H:%M:%S")
        })

        if BOT_MODE == "ALERTA":
            bot.send_message(
                chat_id,
                f"🔔 *ALERTA PROFISSIONAL*\n\n"
                f"🎯 Colunas: {cols}\n"
                f"📊 Confiança: {int(conf*100)}%\n"
                f"🤖 ML: {int(ml_prob*100)}%",
                parse_mode="Markdown"
            )

        time.sleep(90)

# =====================================================
# TELEGRAM
# =====================================================
@bot.message_handler(commands=["start"])
def start(message):
    user_data[message.chat.id] = {}
    bot.send_message(
        message.chat.id,
        "🤖 *Bot Auto Roulette*\n\nSistema profissional iniciado.\nModo atual: "
        + BOT_MODE,
        parse_mode="Markdown"
    )
    threading.Thread(
        target=signal_loop,
        args=(message.chat.id,),
        daemon=True
    ).start()

# =====================================================
# START
# =====================================================
if __name__ == "__main__":
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8080),
        daemon=True
    ).start()

    bot.remove_webhook()
    bot.infinity_polling()
