"""The ask examples the docs tell agents to copy must pass the ask validator (SPEC.md, ask).

Payloads are taken from three shapes: an `ask --json '{...}'` call anywhere in a doc (inline or fenced), a
`ask <<'JSON'` heredoc whose body is an object, and a fenced ```json block. Placeholders such as `<JSON>` are not
examples. A ```json block that is only the members of an object (the `translations` addition) joins the example
before it, as the doc describes it.
"""
import json
import os
import re
from pathlib import Path

import pytest
from test_askaway import (  # noqa: F401  (home is the autouse state folder fixture of test_askaway.py)
    cli,
    home,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS = {
    "skill": REPO_ROOT / "plugins/askaway/skills/askaway-user-question-playbook/SKILL.md",
    "readme": REPO_ROOT / "README.md",
}
ASK_JSON_ARG = re.compile(r"ask --json '(\{[^']*)'")  # an object literal; `<JSON>` placeholders are not examples
ASK_HEREDOC = re.compile(r"ask <<'JSON'\n(\{.*?)\nJSON\n", re.DOTALL)
JSON_FENCE = re.compile(r"^[ \t]*```json[ \t]*\n(.*?)^[ \t]*```[ \t]*$", re.DOTALL | re.MULTILINE)


def _parses(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _is_fragment(block: str) -> bool:
    """Members only, as in the translations addition: no object of their own, but they parse inside braces."""
    return not _parses(block) and _parses("{" + block + "}")


def _pieces(text: str) -> list[tuple[int, str, bool]]:
    """(position, JSON text, is_fragment) of every ask payload piece in a doc, in document order."""
    found = [(match.start(), match[1], False) for match in ASK_JSON_ARG.finditer(text)]
    found += [(match.start(), match[1], False) for match in ASK_HEREDOC.finditer(text)]
    found += [(match.start(), match[1], _is_fragment(match[1])) for match in JSON_FENCE.finditer(text)]
    return sorted(found)


def _examples(text: str) -> list[list[tuple[str, bool]]]:
    """One example per payload; a fragment piece joins the example before it."""
    examples: list[list[tuple[str, bool]]] = []
    for _, raw, fragment in _pieces(text):
        if fragment and examples:
            examples[-1].append((raw, True))
        else:
            examples.append([(raw, fragment)])
    return examples


EXAMPLES = {name: _examples(path.read_text(encoding="utf-8")) for name, path in DOCS.items()}
CASES = [(name, index) for name, examples in EXAMPLES.items() for index in range(len(examples))]


def _entry(pieces: list[tuple[str, bool]]) -> dict:
    entry: dict = {}
    for raw, fragment in pieces:
        entry.update(json.loads("{" + raw + "}" if fragment else raw))
    return entry


@pytest.mark.parametrize("doc", list(DOCS))
def test_each_doc_has_ask_examples(doc):
    assert EXAMPLES[doc], f"no ask example found in {DOCS[doc]}"


@pytest.mark.parametrize(("doc", "index"), CASES, ids=[f"{doc}-{index}" for doc, index in CASES])
def test_documented_ask_example_is_accepted_not_refiled(doc, index, capsys):
    out = cli(capsys, "ask", "--json", json.dumps(_entry(EXAMPLES[doc][index])))
    assert out["action"] in ("continue", "pause"), out.get("error")
    assert (Path(os.environ["ASKAWAY_HOME"]) / "q" / f"{out['id']}.json").exists()
