import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CASINO_API_URL = "https://api.casinoscores.com/svc-evolution-stats/stats/auto-roulette"

CHECK_INTERVAL = 20          # segundos
WINDOW_SIZE = 20             # giros analisados
CONFIDENCE_THRESHOLD = 0.75  # 75%
MAX_SIGNALS_PER_HOUR = 2
