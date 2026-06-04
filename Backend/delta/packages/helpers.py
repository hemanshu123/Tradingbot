import os
import requests
from pprint import pprint
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.delta.exchange")


def get_products(contract_type: str = None):
    """
    Get list of products from Delta Exchange.
    Optionally filter by contract type (e.g., perpetual_futures).
    """
    headers = {"Accept": "application/json"}
    params = {}
    if contract_type:
        params["contract_types"] = contract_type

    r = requests.get(f"{BASE_URL}/v2/products", params=params, headers=headers)
    return r.json()


def get_product_by_symbol(symbol: str):
    """
    Get product details by symbol (e.g., BTCUSD, ETHUSD).
    """
    headers = {"Accept": "application/json"}
    r = requests.get(f"{BASE_URL}/v2/products/{symbol}", headers=headers)
    return r.json()


def get_product_id_by_symbol(symbol: str):
    headers = {"Accept": "application/json"}
    r = requests.get(f"https://api.india.delta.exchange/v2/products/{symbol}", headers=headers)
    data = r.json()

    
    return data["result"]["id"]   # <-- this is the product_id (e.g., 3136 for ETHUSD)




def place_order(product_id: int, size: float, side: str, order_type: str = "market_order"):
    """
    Place an order on Delta Exchange.
    Requires authentication headers.
    """
    import time, hmac, hashlib

    timestamp = str(int(time.time() * 1000))
    body = {
        "product_id": product_id,
        "size": size,
        "side": side,
        "order_type": order_type,
    }

    # Create signature (HMAC SHA256)
    signature_payload = timestamp + "POST" + "/v2/orders" + str(body)
    signature = hmac.new(
        API_SECRET.encode(), signature_payload.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": API_KEY,
        "signature": signature,
        "timestamp": timestamp,
    }

    r = requests.post(f"{BASE_URL}/v2/orders", json=body, headers=headers)
    return r.json()
