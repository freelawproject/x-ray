import asyncio

from . import cli


def main() -> None:
    asyncio.run(cli())


if __name__ == "__main__":
    main()
