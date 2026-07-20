import { createSdk } from "./index.js"

const host = "http://localhost:8000/api/"

const sdk = createSdk({
  host,
  headers: async () => ({}),
})

async function main() {
  const ts = Date.now().toString(36)

  // Find admin user
  const admin = await sdk.users.find({ username: "admin" })
  console.log(`1. admin id=${admin.id} username=${admin.username}`)

  // Create article with unique title
  const article = await sdk.articles.create({
    title: `gen TS SDK Test Article ${ts}`,
    content: "Test content from generated TS SDK.",
    author: admin,
  })
  console.log(`2. created article id=${article.id} title="${article.title}"`)

  // Fetch article by id
  const fetched = await sdk.articles.get(article.id!)
  console.log(`3. fetched article id=${fetched.id} title="${fetched.title}"`)

  // Update article title
  await fetched.save({ title: `gen TS SDK Updated ${ts}` })
  console.log(`4. after save title="${fetched.title}"`)

  // Create a category with unique name
  const category = await sdk.categories.create({ name: `gen TS SDK Cat ${ts}` })
  console.log(`5. created category id=${category.id} name="${category.name}"`)

  // Add category relationship
  await fetched.add("categories", category)
  console.log(`6. added category to article`)

  // List articles
  const listCol = sdk.articles.list()
  await listCol.fetch()
  console.log(`7. articles count: ${listCol.length}`)

  for await (const a of listCol) {
    console.log(`   - article id=${a.id} title="${a.title}"`)
  }

  // Fetch categories of the article via relationship
  const catsRel = fetched.categories
  if (catsRel) {
    await catsRel.fetch()
    for await (const c of catsRel) {
      console.log(`   - category id=${c.id} name="${c.name}"`)
    }
  }

  // Re-fetch article
  await fetched.refetch()
  console.log(`8. refetched article, title="${fetched.title}"`)

  // Remove category relationship
  await fetched.remove("categories", category)
  console.log(`9. removed category from article`)

  // Cleanup
  console.log("10. cleaning up...")
  await fetched.delete()
  console.log(`   deleted article id=${article.id}`)
  await category.delete()
  console.log(`   deleted category id=${category.id}`)
}

main().then(
  () => console.log("Done."),
  (err) => {
    console.error("Error:", err)
    process.exit(1)
  },
)
