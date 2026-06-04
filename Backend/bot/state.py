import json
import os
from typing import Any, Dict

class BotState:
    def __init__(self, path: str):
        self.path = path
        self.data: Dict[str, Any] = {
            "last_candle_time": None,
            "open_position": None
        }
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def set_last_candle_time(self, t):
        self.data["last_candle_time"] = t
        self.save()

    def get_last_candle_time(self):
        return self.data.get("last_candle_time")

    def set_open_position(self, pos):
        self.data["open_position"] = pos
        self.save()

    def get_open_position(self):
        return self.data.get("open_position")

    def clear_open_position(self):
        self.data["open_position"] = None
        self.save()
