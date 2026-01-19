import os

def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))

def _i(name: str, default: str) -> int:
    return int(os.getenv(name, default))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CASINO_API_URL = os.getenv(
    "CASINO_API_URL",
    "https://api-cs.casino.org/svc-evolution-game-events/api/autoroulette/latest"
)

# Stickers (file_id)
STICKER_WIN = os.getenv("STICKER_WIN", "COLE_AQUI_FILE_ID_WIN")
STICKER_RED = os.getenv("STICKER_RED", "COLE_AQUI_FILE_ID_RED")

# Frequências
FETCH_INTERVAL = _i("FETCH_INTERVAL", "8")
SIGNAL_COOLDOWN = _i("SIGNAL_COOLDOWN", "35")
HISTORY_MAXLEN = _i("HISTORY_MAXLEN", "500")

# Regras
MIN_BANK = _f("MIN_BANK", "50")
CONFIDENCE_THRESHOLD = _f("CONFIDENCE_THRESHOLD", "0.75")
MG_CONF_THRESHOLD = _f("MG_CONF_THRESHOLD", "0.80")

# Apostas fixas (sua regra)
BET_COL = _f("BET_COL", "10")
BET_ZERO = _f("BET_ZERO", "1")

# Gestão
STOP_LOSS_HALF = _f("STOP_LOSS_HALF", "0.50")

# Martingale
MG_MULTIPLIER = _f("MG_MULTIPLIER", "2.0")
MG_MAX_STEP = _i("MG_MAX_STEP", "3")

# Meta/stop por hora (opcional)
HOURLY_TARGET = _f("HOURLY_TARGET", "20.0")
HOURLY_STOP = _f("HOURLY_STOP", "-25.0")

if not TELEGRAM_TOKEN:
    # Não estoura aqui pra permitir rodar local/CI, mas o main.py valida.
    pass
