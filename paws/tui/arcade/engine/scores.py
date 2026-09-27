from __future__ import annotations

import json
import os
from pathlib import Path


class HighScores:
    def __init__(self, path: Path | None = None):
        self.path = path or (Path(os.environ.get("PAWS_CONFIG_DIR", Path.home() / ".config/paws")) / "highscores.json")

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
            return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def get(self, key: str) -> int:
        return self._load().get(key, 0)

    def submit(self, key: str, score: int) -> bool:
        data = self._load()
        if score <= data.get(key, 0):
            return False
        data[key] = int(score)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_name(self.path.name + ".tmp")
            temporary_path.write_text(json.dumps(data, indent=1))
            os.replace(temporary_path, self.path)
        except OSError:
            return False
        return True
