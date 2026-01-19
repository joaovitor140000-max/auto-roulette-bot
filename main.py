import threading
import time
from collections import deque, defaultdict, Counter
from datetime import datetime

import telebot
from flask import Flask

from config import (
    TELEGRAM_TOKEN,
    STICKER_WIN,
    STICKER_RED,
    FETCH_INTERVAL,
    SIGNAL_COOLDOWN,
    HISTORY_MAXLEN,
    MIN_BANK,
    CONFIDENCE_THRESHOLD,
    MG_CONF_THRESHOLD,
    BET_COL,
    BET_ZERO,
    STOP_LOSS_HALF,
    MG_MULTIPLIER,
    MG_MAX_STEP,
    HOURLY_TARGET,
    HOURLY_STOP,
)

from roulette_api import fetch_latest_number, last_fetch_status, last_fetch_time
from strategy import (
    now_manaus_dt,
    now_manaus_str,
    is_analysis_window,
    analysis_label,
    number_to_col,
    classify_columns,
    current_col_streak,
    decide_adaptive_strategy,
)

# ------------------ TELEGRAM + FLASK ------------------
bot = telebot.TeleBot(TELEGRAM_TOKEN)  # sem parse_mode pra não quebrar com símbolos
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 BOT ONLINE 24H", 200

@app.route("/favicon.ico")
def favicon():
    return "", 204

def run_flask():
    app.run(host="0.0.0.0", port=5000)

# ------------------ ESTADO GLOBAL ------------------
history = deque(maxlen=HISTORY_MAXLEN)  # mais recente primeiro
last_number = None

users = {}  # chat_id -> dict

daily = {
    "date": now_manaus_dt().date(),
    "wins": 0,
    "reds": 0,
    "signals": 0,
    "max_streak": 0,
    "mode_count": defaultdict(int),
}

hourly = {
    "key": None,    # YYYY-MM-DD HH (Manaus)
    "profit": 0.0,
    "paused": False,
}

def hour_key_manaus():
    return now_manaus_dt().strftime("%Y-%m-%d %H")

def reset_hour_if_needed():
    k = hour_key_manaus()
    if hourly["key"] != k:
        hourly["key"] = k
        hourly["profit"] = 0.0
        hourly["paused"] = False

def reset_daily_if_needed():
    today = now_manaus_dt().date()
    if daily["date"] != today:
        daily["date"] = today
        daily["wins"] = 0
        daily["reds"] = 0
        daily["signals"] = 0
        daily["max_streak"] = 0
        daily["mode_count"] = defaultdict(int)

        # reseta contadores diários por usuário (não força reiniciar banca)
        for u in users.values():
            u["wins_day"] = 0
            u["reds_day"] = 0
            u["signals_day"] = 0
            u["pending"] = None
            u["mg_step"] = 0

def safe_send_sticker(chat_id, sticker_id, fallback_text):
    try:
        if sticker_id and sticker_id.strip() and "COLE_AQUI" not in sticker_id:
            bot.send_sticker(chat_id, sticker_id)
        else:
            bot.send_message(chat_id, fallback_text)
    except Exception:
        bot.send_message(chat_id, fallback_text)

# ------------------ RESOLVE WIN/RED AUTOMÁTICO ------------------
def resolve_pending(new_number: int):
    col = number_to_col(new_number)

    for chat_id, u in list(users.items()):
        if not u.get("active"):
            continue

        s = u.get("pending")
        if not s:
            continue

        # Zero coberto: ignora win/red
        if new_number == 0 or col is None:
            u["pending"] = None
            bot.send_message(chat_id, "🟢 Saiu 0 (coberto). Resultado ignorado.")
            continue

        if col in s["cols"]:
            # Em 2 colunas: lucro líquido = +col_bet - zero_bet
            profit = float(s["col_bet"]) - float(s["zero_bet"])
            u["bank"] += profit
            u["mg_step"] = 0

            daily["wins"] += 1
            u["wins_day"] += 1
            hourly["profit"] += profit

            safe_send_sticker(chat_id, STICKER_WIN, "✅ WIN")
            bot.send_message(chat_id, f"✅ WIN | +R$ {profit:.2f} hookups | Banca: R$ {u['bank']:.2f}")

        else:
            # Perde 2 colunas + zero
            loss = (float(s["col_bet"]) * 2.0) + float(s["zero_bet"])
            u["bank"] -= loss

            daily["reds"] += 1
            u["reds_day"] += 1
            hourly["profit"] -= loss

            if s.get("mg_allowed"):
                u["mg_step"] = min(MG_MAX_STEP, u["mg_step"] + 1)
            else:
                u["mg_step"] = 0

            safe_send_sticker(chat_id, STICKER_RED, "❌ RED")
            bot.send_message(chat_id, f"❌ RED | −R$ {loss:.2f} | Banca: R$ {u['bank']:.2f}")

        u["pending"] = None

        # Stop/Meta por hora
        if hourly["profit"] >= HOURLY_TARGET:
            hourly["paused"] = True
            bot.send_message(chat_id, f"⏱ Meta da hora batida: R$ {hourly['profit']:.2f}. Pausando até virar a hora.")
        elif hourly["profit"] <= HOURLY_STOP:
            hourly["paused"] = True
            bot.send_message(chat_id, f"🛑 Stop da hora: R$ {hourly['profit']:.2f}. Pausando até virar a hora.")

        # Meta/Stop diário
        if u["bank"] >= u["meta"]:
            u["active"] = False
            bot.send_message(chat_id, f"🏁 META DIÁRIA BATIDA! Banca: R$ {u['bank']:.2f}")
        elif u["bank"] <= u["stop"]:
            u["active"] = False
            bot.send_message(chat_id, f"🛑 STOP-LOSS DIÁRIO! Banca: R$ {u['bank']:.2f}")

# ------------------ COLETOR ------------------
def collector_loop():
    global last_number
    while True:
        reset_daily_if_needed()
        reset_hour_if_needed()

        n = fetch_latest_number()
        if n is not None and n != last_number:
            last_number = n
            history.appendleft(n)

            # streak do dia
            _, st = current_col_streak(list(history))
            daily["max_streak"] = max(daily["max_streak"], st)

            resolve_pending(n)

        time.sleep(FETCH_INTERVAL)

# ------------------ LOOP DE SINAIS ------------------
def signals_loop(chat_id: int):
    while users.get(chat_id, {}).get("active"):
        reset_daily_if_needed()
        reset_hour_if_needed()

        u = users.get(chat_id)
        if not u or not u.get("active"):
            break

        # Análise 00:00–06:00 Manaus: SEM SINAIS
        if is_analysis_window():
            time.sleep(30)
            continue

        # pausa por meta/stop da hora
        if hourly["paused"]:
            time.sleep(20)
            continue

        # meta/stop diário
        if u["bank"] >= u["meta"] or u["bank"] <= u["stop"]:
            u["active"] = False
            break

        # histórico mínimo
        if len(history) < 25:
            time.sleep(12)
            continue

        # não manda novo sinal se ainda aguardando resultado
        if u.get("pending"):
            time.sleep(10)
            continue

        d = decide_adaptive_strategy(history)

        # Roleta caótica: jamais entrar
        if d["chaotic"]:
            time.sleep(12)
            continue

        # Confiança mínima
        if d["confidence"] < CONFIDENCE_THRESHOLD:
            time.sleep(12)
            continue

        # MG só se confiança >= 80%
        mg_allowed = d["confidence"] >= MG_CONF_THRESHOLD

        # aposta com MG se permitido e mg_step > 0
        if mg_allowed and u["mg_step"] > 0:
            col_bet = float(BET_COL) * (MG_MULTIPLIER ** u["mg_step"])
        else:
            col_bet = float(BET_COL)

        u["pending"] = {
            "cols": d["play_cols"],
            "col_bet": round(col_bet, 2),
            "zero_bet": float(BET_ZERO),
            "mg_allowed": mg_allowed,
        }

        daily["signals"] += 1
        u["signals_day"] += 1
        daily["mode_count"][d["mode"]] += 1

        bot.send_message(
            chat_id,
            "🚨 SINAL\n\n"
            f"Colunas: {d['play_cols']}\n"
            f"Modo: {d['mode']}\n"
            f"Confiança: {int(d['confidence']*100)}%\n"
            f"Aposta: R$ {u['pending']['col_bet']} em cada coluna + R$ {BET_ZERO} no zero\n"
            f"MG: {'AUTORIZADO' if mg_allowed else 'NÃO autorizado'}\n"
            f"Streak col atual: C{d['streak_col']} x{d['streak_len']}\n"
        )

        time.sleep(SIGNAL_COOLDOWN)

# ------------------ COMANDOS TELEGRAM ------------------
@bot.message_handler(commands=["start"])
def start_cmd(msg):
    bot.send_message(msg.chat.id, f"Digite sua banca inicial (mínimo R$ {MIN_BANK:.0f}):")
    bot.register_next_step_handler(msg, set_bank)

def set_bank(msg):
    try:
        bank = float(msg.text.replace(",", "."))
        if bank < MIN_BANK:
            bot.send_message(msg.chat.id, "❌ Banca mínima é R$ 50.")
            return

        users[msg.chat.id] = {
            "start_bank": bank,
            "bank": bank,
            "meta": bank * 4.0,
            "stop": bank * STOP_LOSS_HALF,
            "mg_step": 0,
            "pending": None,
            "active": True,
            "wins_day": 0,
            "reds_day": 0,
            "signals_day": 0,
        }

        threading.Thread(target=signals_loop, args=(msg.chat.id,), daemon=True).start()

        bot.send_message(
            msg.chat.id,
            "✅ Bot iniciado.\n"
            "Use /status para ver o estado e últimos números.\n"
            "Use /statistics para estatísticas completas.\n"
            "Envie um sticker para eu te mostrar o file_id (WIN/RED)."
        )
    except Exception:
        bot.send_message(msg.chat.id, "❌ Digite apenas números. Ex: 50")

@bot.message_handler(commands=["status"])
def status_cmd(msg):
    u = users.get(msg.chat.id)

    top12 = list(history)[:12]
    lastn = top12[0] if top12 else None

    phase = analysis_label()
    if u:
        if not u.get("active") and u["bank"] >= u["meta"]:
            phase = "FINALIZADO (meta batida)"
        elif not u.get("active") and u["bank"] <= u["stop"]:
            phase = "FINALIZADO (stop-loss)"

    text = []
    text.append("📡 STATUS")
    text.append(f"Manaus: {now_manaus_str()}")
    text.append(f"Fase: {phase}")
    text.append(f"API: {last_fetch_status()} às {last_fetch_time()}")
    text.append(f"Analisando roleta (00-06): {'SIM' if is_analysis_window() else 'NAO'}")
    text.append(f"Último número: {lastn}")
    text.append(f"Últimos 12: {top12 if top12 else '—'}")
    text.append("")

    if not u:
        text.append("Use /start para iniciar.")
        bot.send_message(msg.chat.id, "\n".join(text))
        return

    text.append(f"Banca: R$ {u['bank']:.2f}")
    text.append(f"Meta diária (4x): R$ {u['meta']:.2f}")
    text.append(f"Stop diário (50%): R$ {u['stop']:.2f}")
    text.append("")
    text.append(f"Hora: lucro R$ {hourly['profit']:.2f} | pausado: {hourly['paused']}")
    text.append(f"Hoje: WIN {u['wins_day']} | RED {u['reds_day']} | sinais {u['signals_day']}")

    bot.send_message(msg.chat.id, "\n".join(text))

@bot.message_handler(commands=["statistics"])
def statistics_cmd(msg):
    if not history:
        bot.send_message(
            msg.chat.id,
            "📊 STATISTICS\n"
            f"Manaus: {now_manaus_str()}\n"
            f"API: {last_fetch_status()} às {last_fetch_time()}\n"
            "Ainda sem números coletados."
        )
        return

    nums = list(history)
    top12 = nums[:12]
    top25 = nums[:25]
    top100 = nums[:100]

    cols25 = classify_columns(top25)
    cols100 = classify_columns(top100)

    def pct(cols):
        total = sum(cols.values())
        if total <= 0:
            return {1: 0.0, 2: 0.0, 3: 0.0}
        return {k: (cols[k] / total) * 100.0 for k in (1, 2, 3)}

    pct25 = pct(cols25)
    pct100 = pct(cols100)

    zeros25 = sum(1 for n in top25 if n == 0)
    zeros100 = sum(1 for n in top100 if n == 0)

    sc, sl = current_col_streak(nums)

    c25 = Counter(top25)
    c100 = Counter(top100)

    top5_25 = c25.most_common(5)
    top5_100 = c100.most_common(5)

    nz25 = [n for n in top25 if n != 0]
    nz100 = [n for n in top100 if n != 0]
    hot25 = Counter(nz25).most_common(1)[0] if nz25 else (None, 0)
    hot100 = Counter(nz100).most_common(1)[0] if nz100 else (None, 0)

    def fmt_top(lst):
        return ", ".join([f"{n}×{cnt}" for n, cnt in lst]) if lst else "—"

    modes = dict(daily["mode_count"])
    mode_str = ", ".join([f"{k}:{v}" for k, v in modes.items()]) if modes else "—"

    bot.send_message(
        msg.chat.id,
        "📊 STATISTICS\n"
        f"Manaus: {now_manaus_str()}\n"
        f"Fase: {analysis_label()}\n"
        f"API: {last_fetch_status()} às {last_fetch_time()}\n\n"
        f"Últimos 12: {top12}\n"
        f"Últimos 25: {top25}\n\n"
        "Colunas Top25:\n"
        f"C1 {cols25[1]} ({pct25[1]:.1f}%) | C2 {cols25[2]} ({pct25[2]:.1f}%) | C3 {cols25[3]} ({pct25[3]:.1f}%)\n"
        f"Zeros Top25: {zeros25}\n\n"
        "Colunas Top100:\n"
        f"C1 {cols100[1]} ({pct100[1]:.1f}%) | C2 {cols100[2]} ({pct100[2]:.1f}%) | C3 {cols100[3]} ({pct100[3]:.1f}%)\n"
        f"Zeros Top100: {zeros100}\n\n"
        f"Top5 Top25: {fmt_top(top5_25)}\n"
        f"Número mais saiu Top25 (sem 0): {hot25[0]} ({hot25[1]}x)\n\n"
        f"Top5 Top100: {fmt_top(top5_100)}\n"
        f"Número mais saiu Top100 (sem 0): {hot100[0]} ({hot100[1]}x)\n\n"
        f"Streak atual (coluna): C{sc} por {sl}x\n"
        f"Maior streak do dia: {daily['max_streak']}\n"
        f"Modos usados hoje: {mode_str}\n"
    )

@bot.message_handler(content_types=["sticker"])
def sticker_id(msg):
    bot.send_message(msg.chat.id, f"file_id do sticker:\n{msg.sticker.file_id}")

# ------------------ START ------------------
def start_threads():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=collector_loop, daemon=True).start()

if __name__ == "__main__":
    print("🤖 BOT ONLINE 24H")
    start_threads()
    bot.infinity_polling(skip_pending=True)
