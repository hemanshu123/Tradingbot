import hashlib
import hmac
import requests
import time
import json
import os
from dotenv import load_dotenv
from bot.config import ORDER_SIZE

# Load environment variables
load_dotenv()

BASE_URL = 'https://api.india.delta.exchange'
API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")


def generate_signature(secret, message: str) -> str:
    """Generate HMAC SHA256 signature."""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def place_order(side: str, product_id: int, size: float = ORDER_SIZE, order_type: str = "market_order"):
    """Place an order (buy or sell) on Delta Exchange."""
    method = 'POST'
    timestamp = str(int(time.time()))
    path = '/v2/orders'
    url = f'{BASE_URL}{path}'

    payload_dict = {
        "order_type": order_type,
        "size": size,
        "side": side,          # "buy" or "sell"
        "product_id": product_id
    }
    payload = json.dumps(payload_dict)

    # Signature string
    signature_data = method + timestamp + path + "" + payload
    signature = generate_signature(API_SECRET, signature_data)

    # Headers
    headers = {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'python-rest-client',
        'Content-Type': 'application/json'
    }

    # Request
    response = requests.post(url, data=payload, headers=headers, timeout=(3, 27))
    return response.json()


# ---------------- EXPORTABLE FUNCTIONS ---------------- #

def buy(product_id: int, size: float = ORDER_SIZE, order_type: str = "market_order"):
    """Place a buy order."""
    return place_order("buy", product_id, size, order_type)


def sell(product_id: int, size: float = ORDER_SIZE, order_type: str = "market_order"):
    """Place a sell order."""
    return place_order("sell", product_id, size, order_type)


def close_position(product_id, side, size: float = ORDER_SIZE):
    """
    Close an open position by sending a market order in the opposite direction.
    side: 'buy' or 'sell' (the current open position)
    size: quantity to close
    """
    opposite_side = "sell" if side == "buy" else "buy"
    return place_order(opposite_side, product_id, size)
