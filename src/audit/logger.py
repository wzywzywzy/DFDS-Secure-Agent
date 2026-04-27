"""JSONL audit log writer.

One file per pipeline run. Each line is a stage transition so we can
replay the full decision trail in the UI or post-mortem.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Use line-buffered append to survive ungraceful exits.
        self._fp = open(self.log_path, "a", encoding="utf-8", buffering=1)
        self._t0 = time.time()

    def write(self, run_id: str, stage: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - self._t0, 4),
            "run_id": run_id,
            "stage": stage,
            "payload": payload,
        }
        self._fp.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")

    def close(self) -> None:
        self._fp.close()

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
