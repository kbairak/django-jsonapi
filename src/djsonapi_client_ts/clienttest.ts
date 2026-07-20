import { DjsonApiSdk, Resource } from "./src/index.js"

const host = "http://localhost:8000/api/"

const sdk = DjsonApiSdk.create({
  host,
  headers: async () => ({}),
})

async function main() {
  const Article = (sdk as any).articles
  const User = (sdk as any).users
  const Category = (sdk as any).categories

  const ts = Date.now().toString(36)

  // Find admin user
  const admin = await User.find({ username: "admin" })
  console.log(`1. admin id=${admin.id} username=${admin.get("username")}`)

  // Create article with unique title
  const article = await Article.create({
    title: `TS SDK Test Article ${ts}`,
    content: "Test content from TypeScript client.",
    author: admin,
  })
  console.log(`2. created article id=${article.id} title="${article.get("title")}"`)

  // Fetch article by id
  const fetched = await Article.get(article.id)
  console.log(`3. fetched article id=${fetched.id} title="${fetched.get("title")}"`)

  // Update article title
  await fetched.save({ title: `TS SDK Updated ${ts}` })
  console.log(`4. after save title="${fetched.get("title")}"`)

  // Create a category with unique name
  const category = await Category.create({ name: `TS SDK Cat ${ts}` })
  console.log(`5. created category id=${category.id} name="${category.get("name")}"`)

  // Add category relationship
  await fetched.add("categories", category)
  console.log(`6. added category to article`)

  // List articles
  const listCol = (sdk as any).articles.list()
  await listCol.fetch()
  console.log(`7. articles count: ${listCol.length}`)

  // Async iterate through articles
  for await (const a of listCol) {
    const title = a.get("title") as string
    console.log(`   - article id=${a.id} title="${title}"`)
  }

  // Fetch categories of the article via relationship
  const catsRel = fetched.get("categories") as any
  if (catsRel) {
    await catsRel.fetch()
    for await (const c of catsRel) {
      console.log(`   - category id=${c.id} name="${c.get("name")}"`)
    }
  }

  // Re-fetch article, verify category relationship persisted
  await fetched.refetch()
  console.log(`8. refetched article, title="${fetched.get("title")}"`)

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
