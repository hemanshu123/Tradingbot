import time
from datetime import datetime
from decimal import Decimal
from bot.config import (
    DELTA_PRODUCT_ID, LOOKBACK, POLL_SEC, STATE_FILE,
    TP_PCT, SL_PCT, LEVERAGE, ORDER_SIZE,         # FIX: these were never imported before
    SL_COOLDOWN_BARS, MIN_FISHER_SPREAD,           # new anti-whipsaw params
    RESOLUTION,
)
from bot.state import BotState
from bot.fisher_transform import get_live_fisher_data
from delta.packages.placeorder import buy, sell, close_position
from bot_io import snapshot_update, append_log, position_set, position_clear, trades_append

import os, sys
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FLOAT_TOLERANCE = 0.001


def detect_crossover(current_fisher, current_trigger, prev_fisher, prev_trigger):
    if prev_fisher <= prev_trigger and current_fisher > current_trigger:
        return "fisher_above"
    elif prev_fisher >= prev_trigger and current_fisher < current_trigger:
        return "fisher_below"
    elif (abs(current_fisher - current_trigger) <= FLOAT_TOLERANCE
          and abs(prev_fisher - prev_trigger) > FLOAT_TOLERANCE):
        return "fisher_above" if current_fisher > current_trigger else "fisher_below"
    return None


def calculate_tp_sl(entry_price, side,
                    leverage=LEVERAGE, tp_pct=TP_PCT, sl_pct=SL_PCT):
    # FIX: was hardcoded to leverage=30 tp=0.1375 sl=0.15 — now uses config values
    price     = Decimal(str(entry_price))
    tp_offset = price * Decimal(str(tp_pct)) / Decimal(str(leverage))
    sl_offset = price * Decimal(str(sl_pct)) / Decimal(str(leverage))
    if side == "buy":
        tp = price + tp_offset
        sl = price - sl_offset
    else:
        tp = price - tp_offset
        sl = price + sl_offset
    return round(float(tp), 2), round(float(sl), 2)


def main():
    state      = BotState(STATE_FILE)
    product_id = DELTA_PRODUCT_ID
    asset_name = "ETH" if product_id == 3136 else "BTC" if product_id == 27 else f"Product_{product_id}"

    print(f"[{datetime.now().isoformat()}] Bot starting — {asset_name}")
    print(f"[config] RESOLUTION={RESOLUTION} | LEVERAGE={LEVERAGE}x | "
          f"TP={TP_PCT} ({TP_PCT/LEVERAGE*100:.1f}% price move) | "
          f"SL={SL_PCT} ({SL_PCT/LEVERAGE*100:.1f}% price move)")
    print(f"[config] Cooldown={SL_COOLDOWN_BARS} candles after SL | "
          f"Min spread={MIN_FISHER_SPREAD}")

    prev_fisher, prev_trigger = None, None
    last_trade_signal         = None
    cooldown_bars_remaining   = 0       # skip N candles after SL hit (anti-whipsaw)
    last_seen_candle_time     = None    # track candle closes to count cooldown bars

    while True:
        try:
            fisher_result = get_live_fisher_data(LOOKBACK)
            if not fisher_result:
                print("[v0] Failed to get Fisher data, retrying...")
                time.sleep(POLL_SEC)
                continue

            current_fisher      = round(fisher_result["fisher"],  6)
            current_trigger     = round(fisher_result["trigger"], 6)
            current_price       = float(fisher_result["close"])
            current_candle_time = fisher_result.get("time")

            # --- Count cooldown by candle closes, not by seconds ---
            if current_candle_time != last_seen_candle_time:
                last_seen_candle_time = current_candle_time
                if cooldown_bars_remaining > 0:
                    cooldown_bars_remaining -= 1
                    print(f"[v0] New candle — cooldown: {cooldown_bars_remaining} bars left")

            spread = round(abs(current_fisher - current_trigger), 6)

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {asset_name} "
                  f"Price=${current_price:.2f} | "
                  f"Fisher={current_fisher:.4f} Trigger={current_trigger:.4f} "
                  f"Spread={spread:.4f}"
                  + (f" | COOLDOWN {cooldown_bars_remaining}" if cooldown_bars_remaining > 0 else ""))

            open_position = state.get_open_position()

            # --- Check TP / SL on open position ---
            if open_position:
                entry_side  = open_position["side"]
                entry_price = float(open_position.get("price") or
                                    open_position.get("entry_price", current_price))
                tp = float(open_position["tp"])
                sl = float(open_position["sl"])

                hit_tp = ((entry_side == "buy"  and current_price >= tp) or
                          (entry_side == "sell" and current_price <= tp))
                hit_sl = ((entry_side == "buy"  and current_price <= sl) or
                          (entry_side == "sell" and current_price >= sl))

                if hit_tp or hit_sl:
                    reason = "TP" if hit_tp else "SL"
                    print(f"[v0] {'TAKE PROFIT' if hit_tp else 'STOP LOSS'} "
                          f"hit at {current_price:.2f}! Closing position...")
                    # FIX: was hardcoded size=1, now uses ORDER_SIZE from config
                    response = close_position(product_id, entry_side, size=ORDER_SIZE)

                    if response.get("success"):
                        pnl = (current_price - entry_price) * (1 if entry_side == "buy" else -1)
                        trade = {
                            "side":        entry_side,
                            "entry_price": round(entry_price, 4),
                            "exit_price":  round(current_price, 4),
                            "size":        ORDER_SIZE,
                            "pnl":         round(pnl, 4),
                            "opened_at":   open_position.get("opened_at"),
                            "closed_at":   datetime.now().isoformat(),
                            "reason":      reason,
                        }
                        trades_append(trade)
                        append_log("close", trade)
                        position_clear()
                        state.clear_open_position()
                        last_trade_signal = None
                        print(f"[v0] Position closed: {reason} | PnL={pnl:+.4f}")

                        # Anti-whipsaw: start cooldown after every SL hit
                        if hit_sl:
                            cooldown_bars_remaining = SL_COOLDOWN_BARS
                            print(f"[v0] Cooldown started — skipping next "
                                  f"{SL_COOLDOWN_BARS} candles to avoid re-entering same chop")
                    else:
                        print(f"[v0] Failed to close position: {response}")

            # --- Detect crossover signal ---
            signal           = None
            crossover_status = "no crossover"

            if prev_fisher is not None and prev_trigger is not None:
                crossover = detect_crossover(current_fisher, current_trigger,
                                             prev_fisher, prev_trigger)
                if crossover:
                    crossover_status = crossover
                    if crossover == "fisher_above" and current_fisher < 0 and current_trigger < 0:
                        signal = "buy"
                    elif crossover == "fisher_below" and current_fisher > 0 and current_trigger > 0:
                        signal = "sell"

            # --- Anti-whipsaw filter 1: cooldown ---
            if signal and cooldown_bars_remaining > 0:
                print(f"[v0] {signal.upper()} signal SKIPPED — cooldown "
                      f"({cooldown_bars_remaining} bars remaining)")
                signal = None

            # --- Anti-whipsaw filter 2: minimum spread ---
            if signal and spread < MIN_FISHER_SPREAD:
                print(f"[v0] {signal.upper()} signal SKIPPED — crossover too weak "
                      f"(spread={spread:.4f} < min={MIN_FISHER_SPREAD})")
                signal = None

            # --- Snapshot for dashboard ---
            try:
                snapshot_update({
                    "time":        datetime.now().strftime("%H:%M:%S"),
                    "price":       float(current_price),
                    "fisher":      float(current_fisher),
                    "trigger":     float(current_trigger),
                    "difference":  float(current_fisher - current_trigger),
                    "crossover":   crossover_status,
                    "cooldown":    cooldown_bars_remaining,
                })
                append_log("tick", {
                    "price":    float(current_price),
                    "fisher":   float(current_fisher),
                    "trigger":  float(current_trigger),
                    "diff":     float(current_fisher - current_trigger),
                    "crossover": crossover_status,
                })
            except Exception as log_err:
                print(f"[v0] Logging error (non-fatal): {log_err}")

            # --- Execute new trade ---
            if signal:
                if not open_position:
                    if signal != last_trade_signal:
                        print(f"\n[v0] EXECUTING {signal.upper()} | "
                              f"Price={current_price:.2f} Spread={spread:.4f}")
                        # FIX: was hardcoded size=1, now uses ORDER_SIZE from config
                        response = (buy(product_id, ORDER_SIZE)
                                    if signal == "buy"
                                    else sell(product_id, ORDER_SIZE))

                        if response.get("success"):
                            # FIX: calculate_tp_sl now uses TP_PCT/SL_PCT/LEVERAGE from config
                            tp_price, sl_price = calculate_tp_sl(current_price, signal)

                            opened = {
                                "side":        signal,
                                "entry_price": float(current_price),
                                "tp":          tp_price,
                                "sl":          sl_price,
                                "size":        ORDER_SIZE,
                                "opened_at":   datetime.now().isoformat(),
                            }
                            try:
                                position_set(opened)
                                append_log("open", opened)
                            except Exception as log_err:
                                print(f"[v0] Position logging error (non-fatal): {log_err}")

                            state.set_open_position({
                                "side":      signal,
                                "price":     float(current_price),
                                "tp":        tp_price,
                                "sl":        sl_price,
                                "opened_at": opened["opened_at"],
                            })
                            last_trade_signal = signal
                            print(f"[v0] Position opened: "
                                  f"Entry={current_price:.2f} "
                                  f"TP={tp_price} SL={sl_price} "
                                  f"({TP_PCT/LEVERAGE*100:.1f}% / {SL_PCT/LEVERAGE*100:.1f}% moves)")
                        else:
                            print(f"[v0] Trade failed: {response.get('error')}")
                    else:
                        print(f"[v0] Signal skipped — duplicate {signal}")
                else:
                    print(f"[v0] Signal skipped — already in {open_position['side']} position")

            prev_fisher, prev_trigger = current_fisher, current_trigger
            time.sleep(POLL_SEC)

        except Exception as e:
            print(f"[v0] ERROR: {str(e)}")
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()