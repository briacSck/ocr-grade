"""pre-commit hook: block real student data from ever being staged.

Rejects:
- any staged file under tests/fixtures/real/
- any staged *.pdf outside tests/fixtures/synthetic/

Pre-commit passes the staged file paths as argv.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_blocked(path: Path) -> str | None:
    posix = path.as_posix()
    if "tests/fixtures/real/" in posix:
        return f"{posix}: files under tests/fixtures/real/ must never be committed"
    if path.suffix.lower() == ".pdf" and "tests/fixtures/synthetic/" not in posix:
        return f"{posix}: PDFs may only be committed under tests/fixtures/synthetic/"
    return None


def main(argv: list[str]) -> int:
    violations = [msg for p in argv if (msg := is_blocked(Path(p))) is not None]
    if violations:
        print(
            "check_fixture_paths: blocked commit -- real/unexpected data detected:",
            file=sys.stderr,
        )
        for msg in violations:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
