"""Entry-point for `python -m testlyn` and the `testlyn` console script."""
from __future__ import annotations

import sys


def main() -> None:  # pragma: no cover
    """Dispatch sub-commands."""
    if len(sys.argv) < 2:
        print("Usage: testlyn <command> [options]")
        print("Commands:")
        print("  data generate  Enqueue a synthetic data generation job")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "data":
        _data_cmd(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd!r}", file=sys.stderr)
        sys.exit(1)


def _data_cmd(argv: list[str]) -> None:
    if not argv or argv[0] == "help":
        print("Usage: testlyn data <subcommand>")
        print("Subcommands:")
        print("  generate  Enqueue a synthetic data generation job")
        return

    sub = argv[0]
    if sub == "generate":
        from testlyn.synthetic import _cli
        _cli(argv[1:])
    else:
        import sys
        print(f"Unknown data subcommand: {sub!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
