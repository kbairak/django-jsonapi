import { sdk, User } from "./articles_sdk/index.js";

sdk.setup({ host: "http://localhost:8000/api/" });

async function main() {
  const admin = await sdk.users.find({ username: "admin" });
  const regularUser = await sdk.users.find({ username: "regular_user" });

  const article = await sdk.articles.create({
    title: "one",
    content: "one",
    author: admin,
  });
  await article.author.refetch();
  console.log(article.author);

  // await article.save({ author: regularUser });
  await article.edit("author", regularUser);

  await article.author.refetch();
  console.log(article.author);

  await deleteAll();
}

async function deleteAll() {
  const articles = sdk.articles.list();
  for await (const article of articles) {
    await article.delete();
  }
}

main().then(
  () => console.log("Done."),
  (err) => {
    console.error("Error:", err);
    process.exit(1);
  },
);
