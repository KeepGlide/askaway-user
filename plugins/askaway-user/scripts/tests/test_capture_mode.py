"""Capture modes (mode.json: strict, auto, off): read when a question is filed or intercepted, and applied to that
question only. Tests run against a scratch state folder (ASKAWAY_HOME under pytest's tmp_path)."""
import io
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import askaway

SESSION = "sess-capture-mode"
WHO = "tester"
OFF_MESSAGE = ("AskAway User capture is off: nothing was filed. Ask the user in this window if the decision needs them; "
               "otherwise continue with the recommended option.")
UNREADABLE_OR_UNKNOWN_MODE = [
    pytest.param(None, id="no-file"),
    pytest.param("{not json", id="damaged"),
    pytest.param('["strict"]', id="not-an-object"),
    pytest.param('"strict"', id="bare-string"),
    pytest.param(json.dumps({"mode": "mirror", "ts": 1}), id="reserved-mirror"),
    pytest.param(json.dumps({"mode": "auto", "ts": 1}), id="auto"),
]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    state = tmp_path / "inbox"
    monkeypatch.setenv("ASKAWAY_HOME", str(state))
    monkeypatch.setenv("ASKAWAY_WHO", WHO)
    monkeypatch.setenv("ASKAWAY_DESKTOP_SESSIONS", str(tmp_path / "desktop"))
    monkeypatch.setenv("ASKAWAY_PROJECTS", str(tmp_path / "projects"))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(askaway, "projects_root", lambda: tmp_path / "projects", raising=False)
    return state


def base_entry(**over) -> dict:
    entry = {
        "title": "Cache backend",
        "lang": "en",
        "question": "Which cache should the service use?",
        "options": [
            {"key": "A", "label": "Redis", "tradeoff": "one more service to run", "fit": 88,
             "does": "The API caches responses in a Redis server.",
             "pros": "Hits are shared across workers.",
             "cons": "One more service to run."},
            {"key": "B", "label": "In-process", "tradeoff": "lost on restart", "fit": 40,
             "does": "Each worker caches responses in its own memory.",
             "pros": "No service to run.",
             "cons": "Each worker caches alone; the cache is lost on restart."},
        ],
        "recommended": "A",
        "what": "Redis is a cache server that runs next to the API. The service would keep its responses there.",
        "problem": "Without a decision, each worker keeps its own cache and the API slows down after a restart.",
        "context": "Sizing the API for three workers.",
        "why": "Shared across workers.",
        "how": "Redis runs as a service next to the API.",
        "gains": "Hits are shared across workers.",
        "losses": "One more service to run.",
        "analogy": "A shared locker instead of one per worker.",
        "urgency": "Can wait",
        "undo": "changing later ~10 min",
        "risk": "low",
    }
    entry.update(over)
    return entry


def write_mode(home: Path, text: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "mode.json").write_text(text, encoding="utf-8")


def mode_json(mode: str) -> str:
    return json.dumps({"mode": mode, "ts": 1_791_993_000_000})


def cli(capsys, *args: str) -> dict:
    assert askaway.main(list(args)) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def ask(capsys, **over) -> dict:
    return cli(capsys, "ask", "--json", json.dumps(base_entry(**over)))


def stored(home: Path, item_id: str) -> dict:
    return json.loads((home / "q" / f"{item_id}.json").read_text(encoding="utf-8"))


def hook_output(capsys, monkeypatch, mode: str, event: dict) -> str:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(event).encode("utf-8")), encoding="utf-8"))
    assert askaway.main(["hook", mode]) == 0
    return capsys.readouterr().out


def bash_event(command: str) -> dict:
    return {"session_id": SESSION, "cwd": os.getcwd(), "hook_event_name": "PreToolUse",
            "tool_name": "Bash", "tool_input": {"command": command}}


def askuser_event(permission_mode: str) -> dict:
    question = {"header": "Cache", "question": "Which cache should the service use?", "multiSelect": False,
                "options": [{"label": "In-process", "description": "lost on restart"},
                            {"label": "Redis (Recommended)", "description": "one more service"}]}
    return {"session_id": SESSION, "cwd": os.getcwd(), "hook_event_name": "PreToolUse",
            "tool_name": "AskUserQuestion", "permission_mode": permission_mode, "tool_input": {"questions": [question]}}


def denied(out: str) -> bool:
    return json.loads(out.splitlines()[0])["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("text", UNREADABLE_OR_UNKNOWN_MODE)
def test_unreadable_or_unknown_mode_reads_as_auto(text, home, capsys):
    if text is not None:
        write_mode(home, text)
    assert askaway.capture_mode() == "auto"
    low = ask(capsys, question="Which cache should it use?", risk="low")
    assert low["action"] == "continue"
    assert stored(home, low["id"])["pause"] is False
    high = ask(capsys, question="Which queue should it use?", risk="high")
    assert high["action"] == "pause"
    assert stored(home, high["id"])["pause"] is True


@pytest.mark.parametrize("text", ['{"mode": "mirror", "ts": 1}', '{"mode": "loud", "ts": 1}', "not json"])
def test_ask_guard_denies_on_a_damaged_or_unknown_mode(text, home, capsys, monkeypatch):
    write_mode(home, text)
    assert denied(hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")))


def test_off_ask_files_nothing_and_replies_continue(home, capsys):
    write_mode(home, mode_json("off"))
    assert askaway.capture_mode() == "off"
    out = ask(capsys, risk="high")
    assert out == {"captured": False, "reason": "off", "action": "continue", "recommended": "A",
                   "message": OFF_MESSAGE}
    assert not (home / "q").is_dir() or not any((home / "q").iterdir())


def test_off_invalid_entry_is_not_validated_and_files_nothing(home, capsys):
    write_mode(home, mode_json("off"))
    out = cli(capsys, "ask", "--json", "{not json")
    assert out == {"captured": False, "reason": "off", "action": "continue", "recommended": None,
                   "message": OFF_MESSAGE}
    assert not (home / "q").is_dir() or not any((home / "q").iterdir())


def test_off_ask_guard_stays_silent(home, capsys, monkeypatch):
    write_mode(home, mode_json("off"))
    assert hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")) == ""


def test_off_ask_guard_stays_silent_in_bypass_mode(home, capsys, monkeypatch):
    write_mode(home, mode_json("off"))
    assert hook_output(capsys, monkeypatch, "ask-guard", askuser_event("bypassPermissions")) == ""


def test_strict_low_risk_ask_pauses_and_keeps_its_risk(home, capsys):
    write_mode(home, mode_json("strict"))
    assert askaway.capture_mode() == "strict"
    out = ask(capsys, risk="low")
    assert out["action"] == "pause"
    record = stored(home, out["id"])
    assert record["pause"] is True
    assert record["risk"] == "low"


def test_strict_pause_holds_the_session_after_the_mode_changes(home, capsys, monkeypatch):
    write_mode(home, mode_json("strict"))
    ask(capsys, risk="low")
    for mode in ("off", "auto"):
        write_mode(home, mode_json(mode))
        assert denied(hook_output(capsys, monkeypatch, "pause-guard", bash_event("rm -rf build")))


def test_strict_repeat_pauses_an_open_low_risk_twin_and_keeps_its_risk(home, capsys):
    first = ask(capsys, risk="low")
    assert first["action"] == "continue"
    write_mode(home, mode_json("strict"))
    repeat = ask(capsys, risk="low")
    assert repeat["id"] == first["id"]
    assert repeat["duplicate"] is True
    assert repeat["action"] == "pause"
    record = stored(home, first["id"])
    assert record["pause"] is True
    assert record["risk"] == "low"


def test_question_filed_in_auto_does_not_hold_after_the_mode_becomes_strict(home, capsys, monkeypatch):
    old = ask(capsys, risk="low")
    write_mode(home, mode_json("strict"))
    assert askaway.capture_mode() == "strict"
    assert stored(home, old["id"])["pause"] is False
    assert hook_output(capsys, monkeypatch, "pause-guard", bash_event("rm -rf build")) == ""


def test_strict_ask_guard_still_denies(home, capsys, monkeypatch):
    write_mode(home, mode_json("strict"))
    assert askaway.capture_mode() == "strict"
    assert denied(hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")))


def deny_reason(out: str) -> str:
    return json.loads(out.splitlines()[0])["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("text", [None, mode_json("auto")], ids=["no-file", "auto"])
def test_ask_guard_denies_an_attended_session_when_no_strict_mode_is_set(text, home, capsys, monkeypatch):
    if text is not None:
        write_mode(home, text)
    out = hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default"))
    assert denied(out)
    assert deny_reason(out).count(" ask --json '") == 1
    assert nothing_filed(home)


def test_ask_guard_denies_an_attended_session_in_strict_mode(home, capsys, monkeypatch):
    write_mode(home, mode_json("strict"))
    assert denied(hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")))


def test_off_ask_guard_stays_silent_for_an_attended_session(home, capsys, monkeypatch):
    write_mode(home, mode_json("off"))
    assert hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")) == ""


def test_a_leftover_away_file_that_is_off_does_not_let_a_question_through(home, capsys, monkeypatch):
    write_mode(home, mode_json("auto"))  # creates the state folder
    (home / "away.json").write_text(json.dumps({"on": False, "ts": 1}), encoding="utf-8")
    assert denied(hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")))


@pytest.mark.parametrize("value", ["0", "1"])
def test_claude_code_session_attended_changes_nothing_for_the_ask_guard(value, home, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", value)
    assert denied(hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")))


@pytest.mark.parametrize("mode", ["auto", "strict"])
def test_goal_session_stays_silent_in_every_capture_mode_that_holds(mode, home, capsys, monkeypatch):
    monkeypatch.setattr(askaway, "goal_active", lambda session, project: True)
    write_mode(home, mode_json(mode))
    assert hook_output(capsys, monkeypatch, "ask-guard", askuser_event("default")) == ""


GOAL_TEXT = ("This session runs under /goal and cannot stop: nothing was filed. Continue with the recommended "
             "option and ask in this window if you must.")
CURRENT_STATE_FOLDER = "~/.claude/state/askaway-user"  # the tamper guard protects this folder by its text
LEGACY_STATE_FOLDER = "~/.claude/state/askaway"


def failing_write(monkeypatch) -> None:
    def raise_os_error(target: Path, data: object) -> None:
        raise OSError("disk failed")

    monkeypatch.setattr(askaway, "write_atomic", raise_os_error)
    monkeypatch.setattr(askaway, "RETRY_BACK_OFF_S", 0)


def nothing_filed(home: Path) -> bool:
    return not (home / "q").is_dir() or not any((home / "q").iterdir())


def test_strict_twin_write_failure_still_pauses_the_session(home, capsys, monkeypatch):
    ask(capsys, risk="low")  # auto: the open twin is filed
    write_mode(home, mode_json("strict"))
    failing_write(monkeypatch)
    out = ask(capsys, risk="low")
    assert out["action"] == "pause"


def test_strict_first_filing_that_cannot_be_written_pauses_and_files_nothing(home, capsys, monkeypatch):
    write_mode(home, mode_json("strict"))
    failing_write(monkeypatch)
    out = ask(capsys, risk="low")
    assert out["action"] == "pause"
    assert "error" in out
    assert nothing_filed(home)


@pytest.mark.parametrize("value", ["banana", "STRICT", 5, ["strict"], None])
def test_capture_mode_reads_any_other_value_as_auto(value, home):
    write_mode(home, json.dumps({"mode": value}))
    assert askaway.capture_mode() == "auto"


def test_strict_high_risk_repeat_pauses_and_marks_the_low_risk_twin_high(home, capsys):
    first = ask(capsys, risk="low")
    write_mode(home, mode_json("strict"))
    repeat = ask(capsys, risk="high")
    assert repeat["id"] == first["id"]
    assert repeat["duplicate"] is True
    assert repeat["action"] == "pause"
    record = stored(home, first["id"])
    assert record["pause"] is True
    assert record["risk"] == "high"


def test_goal_session_gets_the_goal_reply_even_with_capture_off(home, capsys, monkeypatch):
    monkeypatch.setattr(askaway, "goal_active", lambda session, project: True)
    write_mode(home, mode_json("off"))
    assert cli(capsys, "ask", "--json", json.dumps(base_entry(risk="high"))) == {
        "captured": False, "reason": "goal", "action": "continue", "recommended": "A", "message": GOAL_TEXT}
    assert nothing_filed(home)


def test_strict_invalid_entry_is_refiled_and_nothing_is_paused(home, capsys):
    write_mode(home, mode_json("strict"))
    entry = base_entry()
    del entry["why"]
    out = cli(capsys, "ask", "--json", json.dumps(entry))
    assert out["action"] == "refile"
    assert nothing_filed(home)


def test_withdraw_refuses_a_low_risk_strict_question_as_it_refuses_a_paused_one(home, capsys):
    paused = ask(capsys, question="Which queue should it use?", risk="high")["id"]
    write_mode(home, mode_json("strict"))
    strict_low = ask(capsys, question="Which cache should it use?", risk="low")["id"]
    refusal = {"error": "withdraw refused: the question holds a pause; the user answers it in the AskAway User panel"}
    assert cli(capsys, "withdraw", "--id", paused) == refusal
    assert cli(capsys, "withdraw", "--id", strict_low) == refusal
    assert not (home / "w" / f"{strict_low}.json").exists()


@pytest.mark.parametrize("command", [
    f"echo '{{\"mode\":\"off\"}}' > {CURRENT_STATE_FOLDER}/mode.json",
    f"sed -i 's/strict/off/' {LEGACY_STATE_FOLDER}/mode.json",
])
def test_bash_guard_denies_a_shell_write_of_mode_json_in_the_state_folder(command):
    assert askaway.bash_tamper_reason(command) == askaway.STATE_DENIED
