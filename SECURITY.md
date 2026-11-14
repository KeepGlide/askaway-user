# Security policy

## Supported versions

AskAway User is stable from `1.0.0`. Fixes land on the latest `1.x` release.

| Version | Supported |
| ------- | --------- |
| `1.1.10` (latest) | ✅ |
| `1.0.3`, `1.0.2`, `1.0.1`, `1.0.0`, `0.4.3`, `0.4.2`, `0.4.1`, `0.4.0`, `0.4.0` betas and earlier `0.x` releases | ❌ |

## Reporting a vulnerability

Do not open a public issue or pull request for a vulnerability. Report it privately with GitHub's private vulnerability reporting: open the Security tab of [KeepGlide/askaway-user](https://github.com/KeepGlide/askaway-user/security) and choose "Report a vulnerability". Include the affected version, the steps to reproduce and the impact you expect.

## Response time

We acknowledge a report within 7 days and aim to publish a fix or a mitigation within 30 days, depending on severity.

## Known limits

AskAway User keeps its state in one folder for one user. These limits are known and documented in [the spec](plugins/askaway/SPEC.md#security); a report that shows a larger impact is still welcome.

- The CLI trusts the `CLAUDE_CODE_SESSION_ID` environment variable to decide which session is the caller. A process that sets it can act as that session's agent on the state folder.
- Any process of the same user that can write the state folder can mint a panel token. The panel credential is a second layer behind the Bash guard, not isolation ([spec](plugins/askaway/SPEC.md#panel-credential)).
- The Bash guard is a deterrent, not a guarantee: the panel calls the CLI itself, which is not a tool call ([README](README.md#-why-it-exists)).
- While a high-risk question holds a session, the pause guard holds every tool call except a read-only allow-list (`READ_ONLY_TOOLS` in `scripts/askaway.py`, read-only MCP tools, and one simple inbox call); a tool added later is held until it is listed there ([spec](plugins/askaway/SPEC.md#hook-modes)). `Skill` is on that list by the owner's choice; the inline `` !`command` `` lines of a skill run before its text reaches Claude, and the Claude Code docs do not say that PreToolUse hooks see them, so such a line may run during a hold. `WebSearch` passes too, although it sends model-chosen text to a search provider.
- The pause guard blocks the call when it times out or crashes only through the hook's `"onFailure": "block"` field, which needs Claude Code 2.1.295 or later ([hooks reference](https://code.claude.com/docs/en/hooks)). On an older Claude Code, a timeout or a crash of the pause guard lets the call through ([spec](plugins/askaway/SPEC.md#hook-modes)).
- Below Python 3.12 every hook, the pause guard included, prints a version error on stderr and exits 0, which `onFailure` does not count as a failure: there the pause and the Bash and file guard hold nothing ([spec](plugins/askaway/SPEC.md#hook-modes)).
- AskAway User makes no network calls of its own.
