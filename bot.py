import os
import time
import requests
import threading
from collections import deque
import telebot
import math

# ================== CONFIG ==================
TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL = os.getenv(
    "ROULETTE_API_URL",
    "https://api.casinoscores.com/svc-evolution-stats/stats/auto-roulette"
)
BOT_MODE = os.getenv("BOT_MODE", "ALERTA")  # ALERTA ou OPERACAO (apenas alerta aqui)

API_INTERVAL = 15  # segundos (seguro)
WINDOW = 24        # janela de análise
MIN_CONF = 0.60    # confiança mínima
HOT_CONF = 0.72    # confiança para considerar "quente"
COLD_ERRORS = 2    # reds seguidos para standby
STANDBY_TIME = 120 # segundos

# ================== BOT ==================
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ================== ESTADO ==================
state = {
    "chat_id": None,
    "banca_inicial": 0.0,
    "banca_atual": 0.0,
    "meta_dia": 0.0,
    "wins": 0,
    "reds": 0,
    "errors_row": 0,
    "last_spin": None,
    "history": deque(maxlen=WINDOW),
    "session_profit": 0.0,
    "standby_until": 0
}

# ================== API ==================
def fetch_numbers():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    try:
        r = requests.get(API_URL, headers=headers, timeout=15)
        if r.status_code == 200:
            js = r.json()
            data = js.get("data") or js.get("history") or []
            nums = []
            for it in data:
                n = it.get("result")
                if isinstance(n, int):
                    nums.append(n)
            return nums[:WINDOW]
    except Exception as e:
        print("API error:", e)
    return []

# ================== LÓGICA ==================
def col(num):
    if num == 0:
        return 0
    m = num % 3
    return 3 if m == 0 else m

def confidence_from_counts(counts, total):
    if total == 0:
        return 0.0
    return max(counts.values()) / total

def analyze(history):
    # ignora zeros para padrão de coluna
    valid = [n for n in history if n != 0]
    if len(valid) < 8:
        return None

    counts = {
        1: sum(1 for n in valid if col(n) == 1),
        2: sum(1 for n in valid if col(n) == 2),
        3: sum(1 for n in valid if col(n) == 3),
    }
    conf = confidence_from_counts(counts, len(valid))

    # exclui a menos frequente
    exclude = min(counts, key=counts.get)
    play = [c for c in (1, 2, 3) if c != exclude]

    return {
        "play": play,
        "exclude": exclude,
        "conf": conf,
        "counts": counts
    }

def session_targets():
    # regra: se muito instável → 2x, senão 4x no dia (em sessões)
    if state["errors_row"] >= 2:
        return 2.0
    return 4.0

def should_standby():
    return time.time() < state["standby_until"]

# ================== LOOP ==================
def loop_signals():
    bot.send_message(
        state["chat_id"],
        "🤖 *Bot iniciado*\n"
        "_Alertas estatísticos. Não garante ganhos._"
    )

    while True:
        try:
            if should_standby():
                time.sleep(5)
                continue

            nums = fetch_numbers()
            if not nums:
                time.sleep(API_INTERVAL)
                continue

            spin = nums[0]
            if state["last_spin"] == spin:
                time.sleep(API_INTERVAL)
                continue

            state["last_spin"] = spin
            state["history"].appendleft(spin)

            analysis = analyze(list(state["history"]))
            if not analysis:
                time.sleep(API_INTERVAL)
                continue

            conf = analysis["conf"]
            play = analysis["play"]

            # estabilidade / confiança
            if conf < MIN_CONF:
                time.sleep(API_INTERVAL)
                continue

            hot = conf >= HOT_CONF
            daily_mult = session_targets()
            state["meta_dia"] = state["banca_inicial"] * daily_mult

            # valores sugeridos (alerta)
            banca = state["banca_atual"]
            v_col = round(banca * 0.05, 2)
            v_zero = round(banca * 0.01, 2)

            msg = (
                f"🚨 *SINAL*\n"
                f"🎯 Colunas: *{play[0]} e {play[1]}*\n"
                f"🪙 R${v_col} cada | Zero: R${v_zero}\n"
                f"📈 Confiança: *{int(conf*100)}%* {'🔥' if hot else ''}\n"
                f"📊 W/R: {state['wins']} / {state['reds']}\n"
                f"🎯 Meta do dia: *{int(daily_mult)}x*"
            )
            bot.send_message(state["chat_id"], msg)

            # simulação de resultado (apenas contagem, não aposta real)
            if spin == 0 or col(spin) in play:
                state["wins"] += 1
                state["errors_row"] = 0
            else:
                state["reds"] += 1
                state["errors_row"] += 1
                if state["errors_row"] >= COLD_ERRORS:
                    state["standby_until"] = time.time() + STANDBY_TIME
                    bot.send_message(
                        state["chat_id"],
                        "❄️ *Roleta instável*. Entrando em standby por 2 minutos."
                    )

            time.sleep(API_INTERVAL)

        except Exception as e:
            print("Loop error:", e)
            time.sleep(10)

# ================== TELEGRAM ==================
@bot.message_handler(commands=["start"])
def start(msg):
    state["chat_id"] = msg.chat.id
    bot.send_message(msg.chat.id, "Qual o valor da sua banca inicial? (ex: 50)")

@bot.message_handler(func=lambda m: state["banca_inicial"] == 0)
def set_bank(msg):
    try:
        v = float(msg.text.replace(",", "."))
        state["banca_inicial"] = v
        state["banca_atual"] = v
        bot.send_message(
            msg.chat.id,
            f"✅ Banca registrada: R${v:.2f}\n"
            "🔎 Iniciando análise contínua..."
        )
        threading.Thread(target=loop_signals, daemon=True).start()
    except:
        bot.send_message(msg.chat.id, "Digite apenas o número. Ex: 50")

# ================== START ==================
if __name__ == "__main__":
    print("Bot iniciado (Render Background Worker)")
    bot.remove_webhook()
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
            
