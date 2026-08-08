import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mempilot.lab.memory_lab_app import run_lab

if __name__ == "__main__":
    raise SystemExit(run_lab())
