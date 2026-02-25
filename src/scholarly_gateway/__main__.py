"""CLI entrypoint for scholarly-gateway-mcp."""
from __future__ import annotations

from scholarly_gateway.server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
