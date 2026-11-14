"""The docs name the repository as it is (KeepGlide/askaway-user) and SECURITY.md names the current version."""
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_JSON = REPO_ROOT / "plugins/askaway/.claude-plugin/plugin.json"
DOCS = ["README.md", "README.pt-BR.md", "SECURITY.md", "plugins/askaway/.claude-plugin/plugin.json", "docs/WAVES.md"]
OLD_SLUG = re.compile(r"KeepGlide/askaway(?!-user)\b")  # the slug before the rename; CHANGELOG history keeps it


@pytest.mark.parametrize("doc", DOCS)
def test_doc_names_the_current_repository_slug(doc):
    hits = [line for line in (REPO_ROOT / doc).read_text(encoding="utf-8").splitlines() if OLD_SLUG.search(line)]
    assert hits == [], f"{doc} still names KeepGlide/askaway"


def test_security_names_the_plugin_version_as_latest():
    version = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert f"`{version}` (latest)" in security
