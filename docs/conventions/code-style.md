# Code Style

## Python

- **Tooling**: [`ruff`](https://docs.astral.sh/ruff/) for lint + format. Config in `pyproject.toml`.
- **Line length**: 100
- **Target**: Python 3.11+
- **Type hints**: required for all public functions, methods, and dataclass / Pydantic fields. `mypy --strict` is enforced.
- **Docstrings**: short. One sentence for purpose, parameters/returns only if non-obvious. Google convention.
- **Imports**: sorted by ruff (`I` rules); first-party last.
- **Avoid**:
  - `from x import *`
  - mutable default args
  - bare `except:` or `except Exception: pass` (CLAUDE.md invariant; banned via custom pre-commit hook)
  - `print()` in production code (use structured logging)

## Module layout

- One responsibility per module
- Public API at top of file (dataclasses, then public functions, then private)
- Helpers prefixed with `_`
- File size soft cap: 300 LOC. When crossed, split with an ADR if non-trivial.
- Tests live alongside the module they test in `tests/unit/test_<module>.py`

## Naming

- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for module-level constants
- Booleans named `is_*`, `has_*`, `should_*`, `can_*`
- Avoid abbreviations except universally understood ones (`url`, `api`, `id`, `uuid`)

## Comments

- **Default to no comments.** Code should be self-documenting via good naming.
- Write a comment only when the WHY is non-obvious (a hidden constraint, workaround, surprising behavior, citation to an ADR or PRD section).
- Never write comments that restate the code.
- Never write multi-paragraph docstrings.
- TODO comments **must** include either a date or an issue reference: `# TODO(2026-06): refactor this once Honcho v2 lands` or `# TODO(#123): handle edge case`.

## Errors

- Raise specific exceptions; don't return `None` to signal an error
- Catch only what you can handle; let the rest bubble
- Always log errors at the boundary that catches them (don't double-log)
- Per CLAUDE.md invariant: every caught exception must be logged with structured context AND either re-raised, returned as a structured error, OR have an explicit comment justifying the swallow

## Pydantic v2

- All data contracts use Pydantic v2 with `frozen=True` (immutable)
- Always include a `schema_version: int = 1` field
- Never drop fields, only deprecate (set default to `None` + add deprecation note)
- Use `model_config = ConfigDict(frozen=True, extra="forbid")` for strictness

## TypeScript

- `tsconfig.json` strict mode (`strict: true`, `noImplicitAny: true`, `strictNullChecks: true`)
- ESLint + Prettier
- Line length: 100
- Use type imports: `import type { Foo } from './foo'`
- Avoid `any`; use `unknown` then narrow

## Shell scripts

- **Bash strict mode at top**: `set -euo pipefail`
- Quote everything: `"$var"` not `$var`
- Use `[[ ]]` not `[ ]`
- No `eval` unless absolutely required and explained in a comment
- All scripts include `#!/usr/bin/env bash` shebang
- All scripts are executable (`chmod +x`)
- All scripts have a header comment explaining purpose + usage

## YAML

- 2-space indent, never tabs
- Comments only for non-obvious fields
- Lists on new lines for >2 items
- Use `null` explicitly, not blank
- Strings that look like booleans/numbers must be quoted (`"yes"`, `"3.11"`)

## Dockerfiles

- Pin base image to a specific tag (not `:latest`) at release time
- One concern per layer (don't combine unrelated `RUN` commands)
- Clean up apt caches in the same layer as `apt-get install`
- Run as non-root in production sandboxes
- Always set `WORKDIR`
- Use `COPY` not `ADD` (unless extracting an archive)

## JSON

- 2-space indent
- Keys in deliberate order (never alphabetical-by-default — use logical groupings)
- All keys quoted with double quotes
- Trailing newline at EOF

## Markdown

- ATX (`#`) heading style, not setext
- Dash (`-`) for unordered lists, never `*` or `+`
- Fenced code blocks with language identifier (` ```python`)
- Backtick code style (` ``` `), not tildes
- Front-matter (YAML) at top of doc files when metadata is needed
- Tables aligned with pipes for readability

## Secrets in code

- **NEVER hardcode a secret**, even a "test" one
- Use `os.environ[...]` (not `os.environ.get` with a default value that looks like a real secret)
- For tests, use string literals that the scrubber will catch and redact (e.g., `sk-test-fake-1234`)
- Pre-commit `detect-secrets` hook catches violations
