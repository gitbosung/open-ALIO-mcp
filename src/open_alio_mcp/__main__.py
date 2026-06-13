"""Command-line entrypoint for open-alio-mcp."""

from __future__ import annotations


def main() -> None:
    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
