import requests
from config import CASINO_API_URL

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.casinoscores.com/",
    "Origin": "https://www.casinoscores.com"
}

def fetch_numbers():
    try:
        print("[DEBUG] Buscando números da roleta...")

        r = requests.get(CASINO_API_URL, headers=HEADERS, timeout=15)

        print(f"[DEBUG] Status HTTP: {r.status_code}")

        if r.status_code != 200:
            return []

        json_data = r.json()

        # 🔹 múltiplos formatos possíveis
        data = []

        if isinstance(json_data, dict):
            if "data" in json_data:
                if isinstance(json_data["data"], list):
                    data = json_data["data"]
                elif isinstance(json_data["data"], dict):
                    data = json_data["data"].get("history", [])

            elif "history" in json_data:
                data = json_data["history"]

        numbers = [
            int(item["result"])
            for item in data
            if isinstance(item, dict) and "result" in item
        ]

        print(f"[DEBUG] Números extraídos: {numbers[:12]}")

        return numbers

    except Exception as e:
        print("[API ERROR]", e)

    return []
