from datetime import datetime, timedelta, timezone, time as dtime
from collections import deque

# Manaus UTC-4
MANAUS_TZ = timezone(timedelta(hours=-4))

def now_manaus_dt():
    return datetime.now(MANAUS_TZ)

def now_manaus_str():
    return now_manaus_dt().strftime("%d/%m %H:%M:%S")

def is_analysis_window():
    # 00:00–06:00 Manaus
    t = now_manaus_dt().time()
    return dtime(0, 0) <= t < dtime(6, 0)

def analysis_label():
    return "ANALISANDO ROLETA (00:00–06:00 Manaus)" if is_analysis_window() else "OPERANDO (06:00–23:59 Manaus)"

def number_to_col(n: int):
    if n == 0:
        return None
    r = n % 3
    return 3 if r == 0 else r

def classify_columns(numbers):
    cols = {1: 0, 2: 0, 3: 0}
    for n in numbers:
        c = number_to_col(n)
        if c is None:
            continue
        cols[c] += 1
    return cols

def current_col_streak(nums):
    """
    streak na coluna do histórico (mais recente primeiro).
    ignora zeros.
    """
    col0 = None
    streak = 0
    for n in nums:
        c = number_to_col(n)
        if c is None:
            continue
        if col0 is None:
            col0 = c
            streak = 1
        elif c == col0:
            streak += 1
        else:
            break
    return col0, streak

def chi_square_uniform(cols):
    total = sum(cols.values())
    if total == 0:
        return 0.0
    exp = total / 3.0
    return sum(((cols[k] - exp) ** 2) / exp for k in (1, 2, 3))

def clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x

def decide_adaptive_strategy(history_deque, window_size=20, streak_trigger=6):
    """
    Estratégias:
      - exclude_weak: exclui coluna mais fraca (tendência)
      - exclude_hot: exclui coluna mais forte quando streak >= trigger (reversão)
    Proteção:
      - chaotic: se distribuição está muito uniforme e sem streak, não entra.
    """
    hist = list(history_deque)
    if len(hist) < window_size + 2:
        return {
            "play_cols": [1, 2],
            "exclude_col": 3,
            "mode": "exclude_weak",
            "confidence": 0.0,
            "streak_col": None,
            "streak_len": 0,
            "chaotic": True,
        }

    window = hist[:window_size]
    cols = classify_columns(window)
    total = sum(cols.values())

    exclude_weak = min(cols, key=lambda k: cols[k])
    exclude_hot = max(cols, key=lambda k: cols[k])

    streak_col, streak_len = current_col_streak(hist)

    mode = "exclude_hot" if streak_len >= streak_trigger else "exclude_weak"
    exclude = exclude_hot if mode == "exclude_hot" else exclude_weak
    play = [c for c in (1, 2, 3) if c != exclude]

    # caótico: muito uniforme + sem streak => sem edge
    chi2 = chi_square_uniform(cols)
    chaotic = (chi2 < 0.35) and (streak_len <= 2)

    # confiança: 1 - freq(excluída) + bônus de streak
    base_conf = 1.0 - (cols[exclude] / total) if total else 0.0
    streak_bonus = min(0.10, max(0, streak_len - 2) * 0.02)
    confidence = clamp01(base_conf + streak_bonus)

    return {
        "play_cols": play,
        "exclude_col": exclude,
        "mode": mode,
        "confidence": confidence,
        "streak_col": streak_col,
        "streak_len": streak_len,
        "chaotic": chaotic,
    }
