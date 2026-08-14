import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_agent.agent import main


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAgent stopped by user.")
    except Exception as exc:
        print(f"\n[FATAL] Agent crashed: {exc}")
        input("\nPress ENTER to exit...")
