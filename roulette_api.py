import requests
from config import CASINO_API_URL

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def fetch_numbers():
    try:
        r = requests.get(CASINO_API_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", [])
            return [int(i["result"]) for i in data if "result" in i]
    except Exception as e:
        print("API ERROR:", e)
    return []
