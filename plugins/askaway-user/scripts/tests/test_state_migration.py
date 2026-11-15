"""Tests for the one-time move of the legacy state folder (state/askaway) to the default one (state/askaway-user).

Every test runs in a sandbox HOME under tmp_path; the real home is never touched. The CLI runs as a subprocess with an
explicit environment, so the migration sees only the HOME the test gives it.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import askaway

SCRIPT = SCRIPTS / "askaway.py"
ENTRY = {
    "title": "Migration cache",
    "lang": "en",
    "question": "Which cache should the service use?",
    "options": [
        {"key": "A", "label": "Redis", "tradeoff": "one more service to run", "fit": 88,
         "does": "The API caches responses in Redis.", "pros": "Shared across workers.", "cons": "One more service."},
        {"key": "B", "label": "In-process", "tradeoff": "lost on restart", "fit": 40,
         "does": "Each worker caches in memory.", "pros": "No service to run.", "cons": "Lost on restart."},
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


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A sandbox HOME for in-process calls: the migration reads HOME at call time, and ASKAWAY_HOME is unset."""
    home = tmp_path / "home"
    (home / ".claude" / "state").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ASKAWAY_HOME", raising=False)
    monkeypatch.setattr(askaway, "_legacy_checked", False)
    return home


def legacy_of(home: Path) -> Path:
    return home / ".claude" / "state" / "askaway"


def default_of(home: Path) -> Path:
    return home / ".claude" / "state" / "askaway-user"


def cli_env(home: Path, askaway_home: Path | None = None) -> dict[str, str]:
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "ASKAWAY_WHO": "migration-test",
           "CLAUDE_CODE_SESSION_ID": "sess-migration", "ASKAWAY_DESKTOP_SESSIONS": str(home / "desktop"),
           "ASKAWAY_PROJECTS": str(home / "projects")}
    if askaway_home is not None:
        env["ASKAWAY_HOME"] = str(askaway_home)
    return env


def run_cli(home: Path, *args: str, askaway_home: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=cli_env(home, askaway_home), cwd=home, timeout=60, check=False)


def ask_id(home: Path, askaway_home: Path) -> str:
    proc = run_cli(home, "ask", "--json", json.dumps(ENTRY), askaway_home=askaway_home)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["id"]


def seed_legacy_question(home: Path) -> str:
    """A question filed into a real legacy folder, the way an older plugin version leaves it."""
    legacy_of(home).mkdir()
    return ask_id(home, legacy_of(home))


def test_a_real_legacy_folder_moves_to_the_default_name_with_its_content(sandbox: Path):
    item = seed_legacy_question(sandbox)
    question = legacy_of(sandbox) / "q" / f"{item}.json"
    before = question.read_bytes()

    proc = run_cli(sandbox, "list")

    assert proc.returncode == 0, proc.stderr
    assert item in proc.stdout
    assert default_of(sandbox).is_dir() and not default_of(sandbox).is_symlink()
    assert (default_of(sandbox) / "q" / f"{item}.json").read_bytes() == before
    assert os.readlink(legacy_of(sandbox)) == str(default_of(sandbox))


def test_both_real_folders_are_left_alone_and_the_default_is_used(sandbox: Path):
    item = seed_legacy_question(sandbox)
    default_of(sandbox).mkdir()
    (default_of(sandbox) / "marker.txt").write_text("kept", encoding="utf-8")

    proc = run_cli(sandbox, "list")

    assert proc.returncode == 0, proc.stderr
    assert not legacy_of(sandbox).is_symlink()
    assert (legacy_of(sandbox) / "q" / f"{item}.json").exists()
    assert (default_of(sandbox) / "marker.txt").read_text(encoding="utf-8") == "kept"
    assert not (default_of(sandbox) / "q").exists()


def test_a_legacy_symlink_is_left_alone(sandbox: Path):
    elsewhere = sandbox / "elsewhere"
    elsewhere.mkdir()
    legacy_of(sandbox).symlink_to(elsewhere)

    proc = run_cli(sandbox, "list")

    assert proc.returncode == 0, proc.stderr
    assert os.readlink(legacy_of(sandbox)) == str(elsewhere)
    assert not default_of(sandbox).exists()


def test_an_asked_askaway_home_never_migrates(sandbox: Path):
    seed_legacy_question(sandbox)
    custom = sandbox / "custom"

    proc = run_cli(sandbox, "list", askaway_home=custom)

    assert proc.returncode == 0, proc.stderr
    assert legacy_of(sandbox).is_dir() and not legacy_of(sandbox).is_symlink()
    assert not default_of(sandbox).exists()


def test_a_question_filed_through_the_legacy_symlink_is_listed_by_the_new_default(sandbox: Path):
    seed_legacy_question(sandbox)
    assert run_cli(sandbox, "list").returncode == 0  # the one-time move leaves the symlink behind

    item = ask_id(sandbox, legacy_of(sandbox))  # an older version files through the old path

    proc = run_cli(sandbox, "list")

    assert proc.returncode == 0, proc.stderr
    assert item in proc.stdout
    assert (default_of(sandbox) / "q" / f"{item}.json").exists()


@pytest.mark.parametrize("layout", ["absent", "file", "symlink"])
def test_only_a_real_legacy_directory_is_moved(layout: str, sandbox: Path):
    legacy = legacy_of(sandbox)
    if layout == "file":
        legacy.write_text("not a folder", encoding="utf-8")
    elif layout == "symlink":
        (sandbox / "elsewhere").mkdir()
        legacy.symlink_to(sandbox / "elsewhere")

    askaway._move_legacy_folder(str(legacy), str(default_of(sandbox)))

    assert not default_of(sandbox).exists()


def test_a_failed_rename_leaves_both_folders_and_the_command_working(sandbox: Path, monkeypatch: pytest.MonkeyPatch):
    legacy_of(sandbox).mkdir()

    def refuse(source: str, target: str) -> None:
        raise PermissionError(13, "denied", source)

    monkeypatch.setattr(askaway.os, "rename", refuse)

    askaway._migrate_legacy_home()

    assert legacy_of(sandbox).is_dir() and not legacy_of(sandbox).is_symlink()
    assert not default_of(sandbox).exists()


def test_the_migration_is_checked_once_per_process(sandbox: Path):
    askaway._migrate_legacy_home()  # nothing to move yet: the check is spent
    legacy_of(sandbox).mkdir()

    askaway._migrate_legacy_home()

    assert legacy_of(sandbox).is_dir() and not legacy_of(sandbox).is_symlink()
    assert not default_of(sandbox).exists()


def test_asked_home_skips_the_migration_in_process(sandbox: Path, monkeypatch: pytest.MonkeyPatch):
    legacy_of(sandbox).mkdir()
    monkeypatch.setenv("ASKAWAY_HOME", str(sandbox / "custom"))

    askaway._migrate_legacy_home()

    assert legacy_of(sandbox).is_dir() and not legacy_of(sandbox).is_symlink()
    assert not default_of(sandbox).exists()


@pytest.mark.parametrize("spelling", ["plain", "through-a-link"])
def test_an_askaway_home_that_names_the_default_folder_migrates(spelling: str, sandbox: Path):
    """The pane calls the CLI with ASKAWAY_HOME set to the default folder: that call moves the legacy folder too."""
    item = seed_legacy_question(sandbox)
    asked = default_of(sandbox)
    if spelling == "through-a-link":
        (sandbox / "alias").symlink_to(sandbox / ".claude")
        asked = sandbox / "alias" / "state" / "askaway-user"

    proc = run_cli(sandbox, "list", askaway_home=asked)

    assert proc.returncode == 0, proc.stderr
    assert item in proc.stdout
    assert os.readlink(legacy_of(sandbox)) == str(default_of(sandbox))


def test_an_empty_default_folder_does_not_block_the_move(sandbox: Path):
    """A pane call may have made the default folder first; while it is empty, the legacy folder still moves onto it."""
    item = seed_legacy_question(sandbox)
    default_of(sandbox).mkdir()

    proc = run_cli(sandbox, "list")

    assert proc.returncode == 0, proc.stderr
    assert item in proc.stdout
    assert (default_of(sandbox) / "q" / f"{item}.json").exists()
    assert os.readlink(legacy_of(sandbox)) == str(default_of(sandbox))


def test_a_dangling_default_symlink_is_left_alone_and_nothing_is_raised(sandbox: Path):
    item = seed_legacy_question(sandbox)
    default_of(sandbox).symlink_to(sandbox / "nowhere")

    askaway._migrate_legacy_home()  # the rename onto a symlink is refused, and the refusal is not raised

    assert default_of(sandbox).is_symlink()
    assert legacy_of(sandbox).is_dir() and not legacy_of(sandbox).is_symlink()
    assert (legacy_of(sandbox) / "q" / f"{item}.json").exists()
