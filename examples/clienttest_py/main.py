import asyncio
import logging

from articles_sdk import SDK

handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
logging.getLogger("articles_sdk").addHandler(handler)

sdk = SDK(host="http://localhost:8000/api/")


async def main():
    async with sdk:
        # logging.getLogger("articles_sdk").setLevel(logging.DEBUG)
        admin = await sdk.users.find(username="admin")
        article = await sdk.articles.create(
            title="Test Article", content="This is a test article.", author=admin
        )
        print(f"1. {article=}")
        article = await sdk.articles.get(article.id)
        print(f"2. {article=}")

        await delete_all()


async def delete_all():
    logging.getLogger("articles_sdk").setLevel(logging.INFO)
    for article in await sdk.articles.list():
        await article.delete()
    for category in await sdk.categories.list():
        await category.delete()


if __name__ == "__main__":
    asyncio.run(main())
