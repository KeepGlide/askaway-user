# Contributing to AskAway User

Thanks for helping. In short: branch from `main`, keep the change small, run both
test suites, and open a pull request.

## Run the tests

AskAway User has two suites.

Mod (TypeScript), from the repository root:

```bash
claude plugin test plugins/askaway
```

CLI and hooks (Python 3.12 or newer is the floor; the script prints an error and exits on an older Python; needs `pytest`: `python3 -m pip install pytest`):

```bash
cd plugins/askaway/scripts && python3 -m pytest tests -q
```

Lint is the Biome 2.x gate, run from the repository root with the real Biome binary. The repository has no formatter config, so `lint` is the only Biome gate. `npx biome` resolves to a different npm package (an unrelated `biome` 0.3.3), so do not use it here:

```bash
biome lint plugins/askaway
```

## Where things live

| Path | What it holds |
|---|---|
| `plugins/askaway/.claude-plugin/plugin.json` | The plugin manifest; it points to the command hooks |
| `plugins/askaway/hooks/` | The mod: `register.tsx` (wiring, polling, commands), `model.ts`, `wizard.ts`, `i18n.ts`, `pane.tsx`, `band.tsx`, `held.ts`, `look.ts`, `logo.ts` (the logo's SVG paths and `LOGO_GLYPH`), `logo-element.tsx` (the logo as one element for the band and the pane heading), `divider.ts` (the 1px rule above the nav row), `keepglide.ts` (the KeepGlide mark in the pane); `hooks.json` loads the mod, `command-hooks.json` holds the command hooks |
| `plugins/askaway/scripts/askaway.py` | The CLI (`ask`, `answer`, `status`, `list`, `wait`, `export`, `away`, `prune`) and the hook modes (`hook ask-guard`, `hook pause-guard`, `hook deliver`, `hook stamp-asker`) |
| `plugins/askaway/skills/askaway-user-question-playbook/SKILL.md` | The skill (`askaway-user:askaway-user-question-playbook`) that tells an agent how to file a question |
| `plugins/askaway/SPEC.md` | The spec: state folder contract, CLI, hooks and panel |
| `plugins/askaway/tests/` | TypeScript tests |
| `plugins/askaway/scripts/tests/` | Python tests |
| `assets/` | `askaway-user-icon.svg` (the logo) and the README cover `askaway-user-cover-1200x630.png`, the same files keepglide.com serves under `assets/products/askaway-user/`, and screenshots `band-en.png`, `window-light-en.png` and `window-dark-en.png`. The plugin ships `plugins/askaway/assets/icon.svg`, a separate file |

## Conventions

- Code, comments, file names and commit messages are in English. Commits follow
  Conventional Commits, for example `feat(panel): ...` or `fix(cli): ...`.
- Branch from `main` as `<type>/<scope>-<slug>`, one change per branch, then open a pull request.
- Keep `README.md` and `README.pt-BR.md` in step: a change to one is a change to both.
- `SPEC.md` describes the public state folder contract. When the code changes it, update the spec in the same pull request.

## Changelog and release

`CHANGELOG.md` feeds the public changelog on keepglide.com, so its text follows the site's feed contract.

- Each release is one heading, `## [X.Y.Z] - YYYY-MM-DD`, newest first; `[Unreleased]` is not published.
- Sections are `Added`, `Changed`, `Fixed`, `Security`, `Performance` and `Documentation`.
- Every bullet opens with a bold feature name in plain words, then plain text, for example
  `- **Pause guard holds every tool**: while a high-risk question waits, only reading tools run.`
- The public text has no backticks, links, SPEC- ids, issue or pull request numbers, milestone names or file paths.
  Keep those in the commit body and the pull request, where they help the next reader. The rule applies from the
  feed's contract version on; older entries stay as written.

Release step: after the release is merged and tagged, run the site exporter in keepglide-web
(`scripts/publish-changelogs.mjs`), which reads this file and publishes the new version.
