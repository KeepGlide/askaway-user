"""Every `wait <id>` example the docs tell agents to run must pass --timeout, at most 110 s, so the call returns before
the Bash tool's 120 s limit (SPEC.md, wait).

A span runs from `wait <id>` to the closing backtick or the end of its line. Prose such as `wait --strict` without an
id is not an example and is not checked.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS = {
    "readme": REPO_ROOT / "README.md",
    "readme-pt-br": REPO_ROOT / "README.pt-BR.md",
    "spec": REPO_ROOT / "plugins/askaway/SPEC.md",
    "skill": REPO_ROOT / "plugins/askaway/skills/askaway-user-question-playbook/SKILL.md",
}
WAIT_EXAMPLE = re.compile(r"wait <id>[^`\n]*")
TIMEOUT_SECONDS = re.compile(r"--timeout (\d+)")
MAX_WAIT_TIMEOUT_S = 110  # the wait default, below the Bash tool's 120 s limit


def _spans(text: str) -> list[str]:
    return [match.group(0) for match in WAIT_EXAMPLE.finditer(text)]


EXAMPLES = {name: _spans(path.read_text(encoding="utf-8")) for name, path in DOCS.items()}
CASES = [(name, index) for name, spans in EXAMPLES.items() for index in range(len(spans))]


@pytest.mark.parametrize("doc", list(DOCS))
def test_each_doc_has_wait_examples(doc):
    assert EXAMPLES[doc], f"no `wait <id>` example found in {DOCS[doc]}"


@pytest.mark.parametrize(("doc", "index"), CASES, ids=[f"{doc}-{index}" for doc, index in CASES])
def test_wait_example_passes_a_timeout_under_the_bash_tool_limit(doc, index):
    span = EXAMPLES[doc][index]
    seconds = TIMEOUT_SECONDS.search(span)
    assert seconds, f"{doc}: `{span}` has no --timeout <seconds>"
    assert int(seconds[1]) <= MAX_WAIT_TIMEOUT_S, f"{doc}: `{span}` passes more than {MAX_WAIT_TIMEOUT_S} s"
