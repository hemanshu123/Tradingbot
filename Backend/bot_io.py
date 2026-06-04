# bot_io.py
import json, os, threading
from datetime import datetime

LOCK = threading.Lock()
DIR = "runtime"               # create a folder for files
os.makedirs(DIR, exist_ok=True)

F_SNAPSHOT = os.path.join(DIR, "latest.json")        # current tick snapshot (fisher/trigger/price/crossover)
F_POSITION = os.path.join(DIR, "open_position.json") # current open position (side, entry, tp, sl, size, opened_at)
F_TRADES   = os.path.join(DIR, "trades.json")        # list of closed trades with PnL
F_LOGS     = os.path.join(DIR, "logs.jsonl")         # append-only, one JSON per line
F_PID      = os.path.join(DIR, "bot.pid")            # created by API when starting bot (optional)

def write_json(path, data):
    with LOCK:
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def append_log(event_type, payload):
    rec = {"ts": datetime.now().isoformat(), "type": event_type, **payload}
    with LOCK:
        with open(F_LOGS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def snapshot_update(data_dict):
    write_json(F_SNAPSHOT, data_dict)

def position_set(pos):
    write_json(F_POSITION, pos)

def position_clear():
    if os.path.exists(F_POSITION):
        write_json(F_POSITION, {})

def trades_append(trade):
    trades = read_json(F_TRADES, default=[])
    trades.append(trade)
    write_json(F_TRADES, trades)
