"""pre-commit hook: block .env files and Mistral-API-key-shaped tokens.

Rejects:
- any staged file matching .env* (except .env.example)
- any staged file that mentions MISTRAL (case-insensitive) on a line that
  also contains a 32-44 char alphanumeric token that isn't pure hex (looks
  like an API key, not a sha256/sha1/md5 hash)

Pre-commit passes the staged file paths as argv.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Real Mistral keys are short-ish random alphanumeric strings. Bound the
# upper end and exclude pure-hex tokens so we don't flag dependency-lockfile
# hashes (sha256 etc.) that happen to sit on a line mentioning "mistral".
KEY_PATTERN = re.compile(r"\b[A-Za-z0-9]{32,44}\b")
HEX_ONLY = re.compile(r"^[0-9a-fA-F]+$")

# Machine-generated dependency manifests never contain hand-pasted secrets;
# they just list package hashes, which collide with the heuristic above.
LOCKFILE_NAMES = {"uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json"}


def is_blocked_env_file(path: Path) -> str | None:
    name = path.name
    if name == ".env.example":
        return None
    if name == ".env" or name.startswith(".env."):
        return f"{path.as_posix()}: .env files must never be committed"
    return None


def find_leaked_key(path: Path) -> str | None:
    if path.name in LOCKFILE_NAMES:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "mistral" not in line.lower():
            continue
        for token in KEY_PATTERN.findall(line):
            if not HEX_ONLY.match(token):
                return f"{path.as_posix()}:{lineno}: looks like a Mistral API key"
    return None


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for raw_path in argv:
        path = Path(raw_path)
        if (msg := is_blocked_env_file(path)) is not None:
            violations.append(msg)
            continue
        if not path.is_file():
            continue
        if (msg := find_leaked_key(path)) is not None:
            violations.append(msg)

    if violations:
        print("check_no_secrets: blocked commit -- possible secret detected:", file=sys.stderr)
        for msg in violations:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
