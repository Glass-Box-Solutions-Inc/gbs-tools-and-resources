# @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
"""Entry point for ``python3 -m spectacles_mcp``."""

import asyncio

from .server import create_mcp_server


def main() -> None:
    server = create_mcp_server()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
