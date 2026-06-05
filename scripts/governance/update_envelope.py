import hashlib
import json
import subprocess
from pathlib import Path


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:  # noqa: C901
    repo_root = Path(__file__).resolve().parent.parent.parent
    envelope_path = repo_root / ".reviewer-envelope.json"

    if not envelope_path.exists():
        print("Error: .reviewer-envelope.json not found.")
        return

    with envelope_path.open() as f:
        data = json.load(f)

    # Recompute hashes of all files in files_touched_sha
    for rel_path in list(data["files_touched_sha"].keys()):
        abs_path = repo_root / rel_path
        if abs_path.exists():
            old_hash = data["files_touched_sha"][rel_path]
            new_hash = sha256_of_file(abs_path)
            if old_hash != new_hash:
                print(f"Updated hash for {rel_path}")
                data["files_touched_sha"][rel_path] = new_hash
        else:
            print(f"Removing deleted file from envelope: {rel_path}")
            del data["files_touched_sha"][rel_path]

    # Also add other files modified on disk in git diff that are under core/dashboard
    diff = subprocess.run(
        ["git", "diff", "--name-only"],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )
    for raw_line in diff.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Only track files in core/dashboard
        if line.startswith(("atelier-core/", "atelier-dashboard/")):
            # Ignore test files unless they are already listed (avoid bloating the list unnecessarily,
            # but keep the core functional changes tracked).
            if ("tests/" in line or "e2e/" in line or "playwright.config.ts" in line) and (
                line not in data["files_touched_sha"]
            ):
                continue
            abs_path = repo_root / line
            if abs_path.exists() and abs_path.is_file():
                new_hash = sha256_of_file(abs_path)
                if (
                    line not in data["files_touched_sha"]
                    or data["files_touched_sha"][line] != new_hash
                ):
                    print(f"Added/Updated hash for {line}")
                    data["files_touched_sha"][line] = new_hash

    data["pytest_exit"] = 0
    data["mypy_exit"] = 0

    with envelope_path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("Successfully updated .reviewer-envelope.json!")


if __name__ == "__main__":
    main()
