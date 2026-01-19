import requests
from config import CASINO_API_URL

HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

_last_status = "—"
_last_time = "—"

def last_fetch_status():
    return _last_status

def last_fetch_time():
    return _last_time

def fetch_latest_number():
    """
    Suporta formatos:
    1) {"data":{"result":{"outcome":{"number":16}}}}
    2) {"data":[{"result":16}, ...]}
    """
    global _last_status, _last_time
    try:
        r = requests.get(CASINO_API_URL, headers=HEADERS, timeout=15)
        _last_time = __import__("datetime").datetime.now().strftime("%H:%M:%S")

        if r.status_code != 200:
            _last_status = f"HTTP {r.status_code}"
            return None

        js = r.json()

        # formato 1
        try:
            n = js["data"]["result"]["outcome"]["number"]
            _last_status = "OK"
            return int(n)
        except Exception:
            pass

        # formato 2
        data = js.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "result" in item:
                    _last_status = "OK"
                    return int(item["result"])

        _last_status = "JSON inesperado"
        return None

    except Exception:
        _last_status = "ERR"
        _last_time = __import__("datetime").datetime.now().strftime("%H:%M:%S")
        return None
