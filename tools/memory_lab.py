import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mempilot.i18n import set_language
from mempilot.lab.memory_lab_app import run_lab
from mempilot.services.settings_service import SettingsService

if __name__ == "__main__":
    settings = SettingsService().load()
    set_language(settings.ui.language)
    raise SystemExit(run_lab())
