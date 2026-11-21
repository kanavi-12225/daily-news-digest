from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "digest.yml").read_text(
    encoding="utf-8"
)


def _run_script_lines(text: str) -> list[str]:
    """`run:` 항목의 스크립트 줄만 모은다 (한 줄 run과 `run: |` 블록)."""
    lines, in_block, block_indent = [], False, 0
    for raw in text.splitlines():
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())
        if in_block:
            if stripped and indent <= block_indent:
                in_block = False
            else:
                lines.append(raw)
                continue
        key = stripped.lstrip("- ").strip()
        if key.startswith("run:"):
            rest = key[len("run:"):].strip()
            if rest in ("|", ">", "|-", ">-"):
                in_block, block_indent = True, indent
            else:
                lines.append(rest)
    return lines


def test_no_github_expressions_inside_run_scripts():
    offenders = [line for line in _run_script_lines(WORKFLOW) if "${{" in line]
    assert offenders == []


def test_manual_slot_is_a_choice_of_morning_or_evening():
    assert "type: choice" in WORKFLOW
    assert "- morning" in WORKFLOW and "- evening" in WORKFLOW


def test_crons_avoid_the_top_of_the_hour_and_match_slot_decision():
    for cron in ("7 23 * * *", "7 10 * * *"):
        assert f'cron: "{cron}"' in WORKFLOW


def test_scheduled_slot_comes_from_kst_hour_and_repeats_are_skipped():
    assert "TZ=Asia/Seoul" in WORKFLOW
    assert "skip=true" in WORKFLOW
    assert WORKFLOW.count("steps.slot.outputs.skip != 'true'") >= 5


def test_pages_are_published_before_kakao_message_is_sent():
    build = WORKFLOW.index("--phase build")
    publish = WORKFLOW.index("git push")
    send = WORKFLOW.index("--phase send")
    assert build < publish < send


def test_checkout_is_fast_forwarded_before_building_to_avoid_rebase_conflicts():
    assert WORKFLOW.index("pull --ff-only") < WORKFLOW.index("--phase build")
    assert "-X theirs" in WORKFLOW
