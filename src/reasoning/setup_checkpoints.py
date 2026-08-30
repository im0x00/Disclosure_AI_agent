import asyncio

from .app_lifecycle import ReasoningAppSettings, setup_checkpoint_database


async def _main() -> None:
    settings = ReasoningAppSettings.from_environment()
    await setup_checkpoint_database(settings.checkpoint_database_url)


if __name__ == "__main__":
    asyncio.run(_main())
