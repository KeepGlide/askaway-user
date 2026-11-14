# Waves

Source of truth: the [issues](https://github.com/KeepGlide/askaway/issues) and [milestones](https://github.com/KeepGlide/askaway/milestones) of this repository. This file only summarizes them and is updated when a wave closes.

| Wave | Goal | Status | Milestone |
| --- | --- | --- | --- |
| W1 | Pin every harmless command the frozen guard copy denies, and define the clean review that retires the copy | closed | [W1 · Frozen copy over-denies and its removal](https://github.com/KeepGlide/askaway/milestone/1) |
| W2 | Narrow the two over-denies the scanner shares with the frozen copy, or record why they stay | open | [W2 · Scanner over-denies shared with the copy](https://github.com/KeepGlide/askaway/milestone/2) |
| W3 | Fix the scanner under-denies that the frozen copy hides, so the copy can go | open | [W3 · Scanner under-denies the frozen copy hides](https://github.com/KeepGlide/askaway/milestone/3) |
| W4-hotfix | The pane writes its state on macOS (`mv -T` dropped, BSD-safe stale lock); release 1.1.3, merged in #54 on 2026-11-14; by-hand Mac check pending | closed | [W4-hotfix · The pane writes its state on macOS](https://github.com/KeepGlide/askaway/milestone/10) |
| W4 | Typed Other text is the answer without Enter, a window's draft writes run in order, moves never eat a press (#32, #33 step A, #34); release 1.1.4 in #56; #31 and #33 step B (#55) moved to W5 | closed | [W4 · Typed Other text is the answer without Enter](https://github.com/KeepGlide/askaway/milestone/4) |
| W5 | Card details fold by default, urgency colour only from `urgency_level`, paused count on the band (#35, #36, #37); release 1.1.5 in #57; #31 and #55 moved to W6; by-hand check on Claude Desktop pending | closed | [W5 · Card details fold by default](https://github.com/KeepGlide/askaway/milestone/5) |
| W6 | A paused session resumes only on a delivered answer: a subagent turn never marks the session busy (#38), a refused hand-off is retried (#39); #31 and #55 moved to W8; release 1.1.6 in #60 | closed | [W6 · A paused session resumes only on a delivered answer](https://github.com/KeepGlide/askaway/milestone/6) |
| W7 | The pause guard holds every tool by default, with a read-only allow-list and a fast exit (#41, #42); documented ask examples are tested against the validator (#40); the ask-guard notes a multi-select question (#43); release 1.1.7 in #61 | closed | [W7 · Guard and contract hardening](https://github.com/KeepGlide/askaway/milestone/7) |
| W8 | Every process run of the pane has a timeout and the token folder is made once per session (#45); session start clears stale fades, a failed session id read is retried, a press on a narrow terminal shows a toast (#46); the `wait` default stays under the Bash tool timeout (#47); #31 and #55 moved to W9; release 1.1.8 in PR pending | open | [W8 · Runtime robustness and platforms](https://github.com/KeepGlide/askaway/milestone/8) |
