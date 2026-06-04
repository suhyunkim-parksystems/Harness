from __future__ import annotations

import sys
from pathlib import Path


def ensure_ai_path() -> Path:
    ai_dir = Path(__file__).resolve().parents[1]
    ai_text = str(ai_dir)
    if ai_text not in sys.path:
        sys.path.insert(0, ai_text)
    return ai_dir
