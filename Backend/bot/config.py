import os
from dotenv import load_dotenv

load_dotenv()

DELTA_PRODUCT_ID  = int(os.getenv("DELTA_PRODUCT_ID", "27"))   # 27=BTC  3136=ETH
ORDER_SIZE        = int(os.getenv("ORDER_SIZE", "1"))
LOOKBACK          = int(os.getenv("LOOKBACK", "9"))
RESOLUTION        = os.getenv("RESOLUTION", "1h")              # changed: 15m -> 1h
TP_PCT            = float(os.getenv("TP_PCT", "0.60"))          # changed: 0.10 -> 0.60  (4:1 R/R)
SL_PCT            = float(os.getenv("SL_PCT", "0.15"))
LEVERAGE          = float(os.getenv("LEVERAGE", "10"))          # changed: 30x -> 10x (safer)
POLL_SEC          = float(os.getenv("POLL_SEC", "1"))
STATE_FILE        = os.getenv("STATE_FILE", "./bot_state.json")
SL_COOLDOWN_BARS  = int(os.getenv("SL_COOLDOWN_BARS", "5"))     # new: skip 5 candles after SL hit
MIN_FISHER_SPREAD = float(os.getenv("MIN_FISHER_SPREAD", "0.05")) # new: ignore weak crossovers
DELTA_API_KEY = os.getenv("DELTA_API_KEY")
DELTA_API_SECRET = os.getenv("DELTA_API_SECRET")

if not DELTA_API_KEY or not DELTA_API_SECRET:
    raise ValueError("DELTA_API_KEY and DELTA_API_SECRET must be set in environment variables")
