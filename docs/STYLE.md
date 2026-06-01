# Atelier — Repository Style Guide

Applies to all committed `.md` and `.py` files. Violations are caught by
`scripts/check_hygiene.py` and will fail CI.

## Anti-tell rules

### No pictographic emoji in code or documentation

Emoji signal a rushed or AI-generated artifact to technically literate reviewers.
Use plain English or standard typographic symbols instead.

Banned: pictographic emoji in the Unicode range U+1F000-U+1FAFF and the symbols
`✅ ❌ ⚠ ⭐ ✨` and related pictographs.

Permitted (not emoji; standard technical typography):
`→ ← ≥ ≤ × — • § ✓ ✗`

Examples:

| Instead of   | Write                      |
| ------------ | -------------------------- |
| `✅ Shipped` | `Shipped` or `[x] Shipped` |
| `❌ No`      | `No` or `Not supported`    |
| `⚠️ Warning` | `Warning:` or `Note:`      |
| `🟢 Live`    | `Live`                     |
| `📝 Draft`   | `Draft`                    |

### No AI-authorship strings

The following strings — and any close variants — must not appear in committed
files. They reveal that content was drafted by a language model without editorial
review.

- `Co-Authored-By: Claude` (any capitalisation)
- `Generated with Claude`
- `🤖` (robot face)
- `vibe cod` (as in "vibe coding")
- `as an AI`
- `I'll help you`

### No aspirational-stub comments

Comments that describe what the code _will_ do someday rather than what it _does
now_ are misleading. They indicate unfinished work that should be tracked in a
GitHub Issue, not embedded in source.

Banned phrases (case-insensitive):

- `current implementation` — implies the code is a placeholder; describe the
  actual behavior instead.
- `replaces this with` — aspirational; describe what the code does, not a future
  replacement.
- `in a real implementation` — implies the code is a mock; use `NOTE:` or open
  an issue.
- `in a production implementation` — same as above.

If a function is intentionally a heuristic proxy pending a more accurate
implementation, document it accurately:

```python
# Heuristic proxy for Lighthouse score (static HTML analysis; no browser sandbox).
# Full accuracy requires @lighthouse-ci integration. See issue #NNN.
```

## Tone and precision

- Target audience: technically literate reviewers (engineers, hiring managers,
  competition judges). Write as you would write internal engineering documentation.
- Prefer named technologies and numbers over adjectives.
  - Good: "7-node DAG with 3 deterministic gates and 5-axis consensus judge"
  - Weak: "a highly sophisticated multi-stage pipeline"
- Use the active voice for descriptions of what the code does.
- Avoid marketing language, filler phrases, and vague claims.

## Enforcement

The hygiene gate (`scripts/check_hygiene.py`) scans all committed `.md` and
`.py` files on every PR. Failures include:

- A `path:line: <reason>` report for each violation
- A reference back to this file (`docs/STYLE.md`) for remediation guidance

Fix violations before merging. Do not use `# noqa` or similar suppression
mechanisms to bypass the hygiene scan.
