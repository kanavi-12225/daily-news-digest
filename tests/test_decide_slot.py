import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "decide_slot.sh"
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")


def decide(tmp_path, event, hour, schedule="", slot="", force="false", sent=()):
    sent_dir = tmp_path / ".sent"
    sent_dir.mkdir(exist_ok=True)
    for name in sent:
        (sent_dir / name).touch()
    env = {
        "PATH": __import__("os").environ["PATH"],
        "EVENT_NAME": event,
        "INPUT_SLOT": slot,
        "FORCE": force,
        "SCHEDULE": schedule,
        "KST_HOUR": hour,
        "KST_DATE": "2026-11-22",
        "SENT_DIR": str(sent_dir),
    }
    out = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, check=True).stdout
    return dict(line.split("=", 1) for line in out.splitlines())


MORNING = "7 23 * * *"
EVENING = "7 10 * * *"


@pytest.mark.parametrize("hour", ["08", "09"])  # 8진수로 읽히면 깨지는 시각
def test_on_time_morning_backup_runs(tmp_path, hour):
    r = decide(tmp_path, "schedule", hour, schedule=MORNING)
    assert (r["value"], r["skip"]) == ("morning", "false")


def test_on_time_evening_backup_runs(tmp_path):
    r = decide(tmp_path, "schedule", "19", schedule=EVENING)
    assert (r["value"], r["skip"]) == ("evening", "false")


def test_morning_cron_delayed_to_afternoon_is_dropped_not_relabeled(tmp_path):
    r = decide(tmp_path, "schedule", "15", schedule=MORNING)
    assert r["value"] == "morning" and r["skip"] == "true"


def test_evening_cron_delayed_past_midnight_is_dropped(tmp_path):
    for hour in ("00", "02", "05"):
        assert decide(tmp_path, "schedule", hour, schedule=EVENING)["skip"] == "true"


def test_morning_backup_in_small_hours_is_dropped(tmp_path):
    assert decide(tmp_path, "schedule", "03", schedule="37 0 * * *")["skip"] == "true"


def test_dispatch_always_uses_its_input_slot(tmp_path):
    r = decide(tmp_path, "workflow_dispatch", "08", slot="evening")
    assert (r["value"], r["skip"]) == ("evening", "false")


def test_second_runner_skips_when_marker_exists_for_any_trigger(tmp_path):
    sent = ["2026-11-22-morning"]
    assert decide(tmp_path, "workflow_dispatch", "08", slot="morning", sent=sent)["skip"] == "true"
    assert decide(tmp_path, "schedule", "08", schedule=MORNING, sent=sent)["skip"] == "true"


def test_force_resends_even_when_marker_exists(tmp_path):
    r = decide(tmp_path, "workflow_dispatch", "08", slot="morning", force="true", sent=["2026-11-22-morning"])
    assert r["skip"] == "false"


def test_marker_of_other_slot_or_day_does_not_block(tmp_path):
    sent = ["2026-11-22-evening", "2026-11-21-morning"]
    assert decide(tmp_path, "workflow_dispatch", "08", slot="morning", sent=sent)["skip"] == "false"


def test_unknown_schedule_or_invalid_slot_is_skipped(tmp_path):
    assert decide(tmp_path, "schedule", "08", schedule="1 2 * * *")["skip"] == "true"
    assert decide(tmp_path, "workflow_dispatch", "08", slot="noon")["skip"] == "true"
