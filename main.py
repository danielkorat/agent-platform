"""Agent Platform — main entry point."""

from __future__ import annotations

import logging
import sys

import uvicorn

from config import get_settings


def main():
    s = get_settings()

    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stdout,
    )

    uvicorn.run(
        "api:app",
        host=s.api_host,
        port=s.api_port,
        reload=False,
        log_level=s.log_level.lower(),
    )


if __name__ == "__main__":
    main()
