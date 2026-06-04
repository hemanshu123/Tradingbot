from typing import Iterable, Optional, TypeVar
from stock_indicators._cslib import CsIndicator
from stock_indicators._cstypes import List as CsList
from stock_indicators.indicators.common.helpers import CondenseMixin
from stock_indicators.indicators.common.results import IndicatorResults, ResultBase
from stock_indicators.indicators.common.quote import Quote
import ccxt
from datetime import datetime
from bot.config import RESOLUTION


# ----------------- Klinger Oscillator ----------------- #
def get_klinger(quotes: Iterable[Quote], fast_period: int = 34, slow_period: int = 55, signal_period: int = 13):
    results = CsIndicator.GetKvo[Quote](CsList(Quote, quotes), fast_period, slow_period, signal_period)
    return KlingerResults(results, KlingerResult)


class KlingerResult(ResultBase):
    @property
    def oscillator(self) -> Optional[float]:
        return self._csdata.Oscillator

    @property
    def signal(self) -> Optional[float]:
        return self._csdata.Signal


_T = TypeVar("_T", bound=KlingerResult)
class KlingerResults(CondenseMixin, IndicatorResults[_T]):
    pass


def get_live_klinger_data(fast_period: int = 34, slow_period: int = 55, signal_period: int = 13):
    try:
        exchange = ccxt.binance()
        bars = exchange.fetch_ohlcv('ETH/USDT', timeframe=RESOLUTION, limit=200)

        quotes = [
            Quote(date=datetime.utcfromtimestamp(bar[0] / 1000),
                  open=bar[1], high=bar[2], low=bar[3],
                  close=bar[4], volume=bar[5])
            for bar in bars
        ]

        results = get_klinger(quotes, fast_period, slow_period, signal_period)
        latest = results[-1]

        # --- scale to TradingView-like range ---
        osc = latest.oscillator
        sig = latest.signal

        # normalize using last close price
        scale = float(quotes[-1].close) / 1000.0
        osc = float(osc) / scale
        sig = float(sig) / scale


        return {
            'oscillator': osc,
            'signal': sig,
            'close': quotes[-1].close,
            'time': bars[-1][0]
        }
    except Exception as e:
        print(f"[v0] Error fetching Binance Klinger data: {e}")
        return None
