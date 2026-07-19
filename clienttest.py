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
        category1 = await sdk.categories.create(name="one")
        category2 = await sdk.categories.create(name="two")
        category3 = await sdk.categories.create(name="three")
        article = await sdk.articles.create(title="one", content="one", author=admin)

        await article.add("categories", category1, category2)
        print([c.name async for c in article.categories])

        await article.remove("categories", category2)
        print([c.name async for c in article.categories])

        await article.reset("categories", category2, category3)
        print([c.name async for c in article.categories])

        await delete_all()


async def delete_all():
    logging.getLogger("articles_sdk").setLevel(logging.INFO)
    for article in await sdk.articles.list():
        await article.delete()
    for category in await sdk.categories.list():
        await category.delete()


if __name__ == "__main__":
    asyncio.run(main())
