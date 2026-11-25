"""Source checkout launcher; works with the shared Python/test virtual environment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from robotstudio_ai.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
