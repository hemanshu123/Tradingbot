import time
from datetime import datetime
from decimal import Decimal
from bot.config import DELTA_PRODUCT_ID, LOOKBACK, POLL_SEC, STATE_FILE
from bot.state import BotState
from bot.fisher_transform import get_live_fisher_data
from delta.packages.placeorder import buy, sell, close_position  # ✅ your placeorder.py

# tolerance for "almost equal" cross
FLOAT_TOLERANCE = 0.002  


def detect_crossover(current_fisher, current_trigger, prev_fisher, prev_trigger):
    """Detect Fisher-Trigger crossover with tolerance."""
    # Fisher crosses above Trigger
    if prev_fisher <= prev_trigger and current_fisher > current_trigger:
        return "fisher_above"
    # Fisher crosses below Trigger
    elif prev_fisher >= prev_trigger and current_fisher < current_trigger:
        return "fisher_below"
    # Handle near-equal (parallel) cases
    elif abs(current_fisher - current_trigger) <= FLOAT_TOLERANCE and abs(prev_fisher - prev_trigger) > FLOAT_TOLERANCE:
        if current_fisher > current_trigger:
            return "fisher_above"
        else:
            return "fisher_below"
    return None


def calculate_tp_sl(entry_price, side, leverage=30, tp_pct=0.10, sl_pct=0.15):
    """
    Calculate TP/SL using offset formula with leverage:
    TP_offset = entry * tp_pct / leverage
    SL_offset = entry * sl_pct / leverage
    """
    price = Decimal(entry_price)
    tp_offset = price * Decimal(str(tp_pct)) / Decimal(str(leverage))
    sl_offset = price * Decimal(str(sl_pct)) / Decimal(str(leverage))

    if side == "buy":
        tp = price + tp_offset
        sl = price - sl_offset
    else:  # sell
        tp = price - tp_offset
        sl = price + sl_offset

    return round(float(tp), 2), round(float(sl), 2)


def main():
    state = BotState(STATE_FILE)
    product_id = DELTA_PRODUCT_ID
    asset_name = "ETH" if product_id == 3136 else "BTC" if product_id == 27 else f"Product_{product_id}"
    print(f"[{datetime.now().isoformat()}] Trading {asset_name} using live data for Fisher transform")

    prev_fisher, prev_trigger = None, None
    last_trade_signal = None

    while True:
        try:
            fisher_result = get_live_fisher_data(LOOKBACK)
            if not fisher_result:
                print("[v0] Failed to get Fisher data, retrying...")
                time.sleep(POLL_SEC)
                continue

            current_fisher = round(fisher_result['fisher'], 6)
            current_trigger = round(fisher_result['trigger'], 6)
            current_price = fisher_result['close']

            # --- Logs ---
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📊 {asset_name} Fisher Transform:")
            print(f"[v0]   💰 Price: ${current_price:.2f}")
            print(f"[v0]   🎣 Fisher: {current_fisher}")
            print(f"[v0]   🎯 Trigger: {current_trigger}")
            print(f"[v0]   📈 Difference: {current_fisher - current_trigger:.6f}")

            open_position = state.get_open_position()

            # --- Check TP/SL first if we have open position ---
            if open_position:
                entry_side = open_position["side"]
                tp = open_position["tp"]
                sl = open_position["sl"]

                if (entry_side == "buy" and current_price >= tp) or (entry_side == "sell" and current_price <= tp):
                    print(f"[v0] 🎯 TAKE PROFIT hit at {current_price:.2f}! Closing position...")
                    response = close_position(product_id, entry_side, size=1)
                    if response.get("success"):
                        state.clear_open_position()
                        last_trade_signal = None
                        print(f"[v0] ✅ Position closed at TP")
                    else:
                        print(f"[v0] ❌ Failed to close position: {response}")
                elif (entry_side == "buy" and current_price <= sl) or (entry_side == "sell" and current_price >= sl):
                    print(f"[v0] 🛑 STOP LOSS hit at {current_price:.2f}! Closing position...")
                    response = close_position(product_id, entry_side, size=1)
                    if response.get("success"):
                        state.clear_open_position()
                        last_trade_signal = None
                        print(f"[v0] ✅ Position closed at SL")
                    else:
                        print(f"[v0] ❌ Failed to close position: {response}")

            # --- Detect crossover for new signals ---
            signal = None
            crossover_status = "no crossover"
            if prev_fisher is not None and prev_trigger is not None:
                crossover = detect_crossover(current_fisher, current_trigger, prev_fisher, prev_trigger)
                if crossover:
                    crossover_status = crossover
                    print(f"[v0] 🔄 CROSSOVER DETECTED: {crossover}")
                    if crossover == "fisher_above" and current_fisher < 0 and current_trigger < 0:
                        signal = "buy"
                        print(f"[v0] ✅ BUY SIGNAL (negative zone)")
                    elif crossover == "fisher_below" and current_fisher > 0 and current_trigger > 0:
                        signal = "sell"
                        print(f"[v0] ✅ SELL SIGNAL (positive zone)")
                    else:
                        print(f"[v0] ❌ Crossover ignored - wrong zone")

            print(f"[v0]   🔍 Crossover Status: {crossover_status}")

            # --- Execute new trade if valid ---
            if signal:
                if not open_position or open_position.get('side') != signal:
                    if signal != last_trade_signal:
                        print(f"\n[v0] 🚀 EXECUTING {signal.upper()} TRADE")
                        response = buy(product_id, 1) if signal == "buy" else sell(product_id, 1)

                        if response.get('success'):
                            tp_price, sl_price = calculate_tp_sl(current_price, signal)
                            state.set_open_position({
                                "side": signal,
                                "price": float(current_price),
                                "tp": tp_price,
                                "sl": sl_price
                            })
                            last_trade_signal = signal
                            print(f"[v0] ⚡ Position opened: Entry=${current_price:.2f}, TP=${tp_price}, SL=${sl_price}")
                        else:
                            print(f"[v0] ❌ Trade failed: {response.get('error')}")
                    else:
                        print(f"[v0] ⚠️ Trade skipped — duplicate signal")
                else:
                    print(f"[v0] ⚠️ Trade skipped — already have open {open_position['side']} position")

            # Save for next loop
            prev_fisher, prev_trigger = current_fisher, current_trigger
            time.sleep(POLL_SEC)

        except Exception as e:
            print(f"[v0] ❌ ERROR: {str(e)}")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()