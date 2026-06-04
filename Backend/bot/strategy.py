from typing import Optional, Tuple

def detect_fisher_crossover(current_fisher: float, current_trigger: float, 
                          prev_fisher: float, prev_trigger: float) -> Optional[str]:
    """
    Detect Fisher-Trigger crossover signals:
    - Buy when Fisher crosses above Trigger and both are negative
    - Sell when Fisher crosses above Trigger and both are positive
    """
    # Check if Fisher crossed above Trigger
    if prev_fisher <= prev_trigger and current_fisher > current_trigger:
        if current_fisher < 0 and current_trigger < 0:
            return "buy"  # Both negative, buy signal
        elif current_fisher > 0 and current_trigger > 0:
            return "sell"  # Both positive, sell signal
    
    return None

def detect_fisher_equality_cross(fisher: float, trigger: float) -> Optional[str]:
    """
    Detect when Fisher equals Trigger (crossover point):
    - Buy when both are negative and equal
    - Sell when both are positive and equal
    """
    # Check if Fisher and Trigger are approximately equal (within small tolerance)
    if abs(fisher - trigger) < 0.0001:
        if fisher < 0 and trigger < 0:
            return "buy"
        elif fisher > 0 and trigger > 0:
            return "sell"
    
    return None

def zero_decimal_touch_cross(f: float, t: float) -> Optional[str]:
    if round(f) != round(t):
        return None
    if f > 0:
        return "sell"
    if f < 0:
        return "buy"
    return None

def calc_targets(entry: float, side: str, tp_pct: float, sl_pct: float, leverage: float):
    tp_offset = entry * tp_pct / leverage
    sl_offset = entry * sl_pct / leverage
    if side == "buy":
        tp = entry + tp_offset
        sl = entry - sl_offset
    else:
        tp = entry - tp_offset
        sl = entry + sl_offset
    return tp, sl, tp_offset, sl_offset
