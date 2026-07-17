import asyncio
import logging

from djsonapi_client import DjsonApiSdk

logger = logging.getLogger("djsonapi_client")
logger.addHandler(logging.StreamHandler())
logger.handlers[0].setFormatter(logging.Formatter("%(levelname)s %(message)s"))
# logger.setLevel(logging.DEBUG)

sdk = DjsonApiSdk(host="http://localhost:8000/api/")


async def main():
    async with sdk:
        await delete_all()

        author = await sdk.users.get("1")
        article = await sdk.articles.create(title="a", content="a", author=author)
        print(article)

        await delete_all()


async def delete_all():
    async for article in sdk.articles.list().all():
        await article.delete()
    async for category in sdk.categories.list().all():
        await category.delete()


if __name__ == "__main__":
    asyncio.run(main())
