import { describe, it, expect, vi, beforeEach } from "vitest"
import { DjsonApiSdk, Resource, Collection } from "../src/index.js"

const HOST = "http://testserver"

function createSdk() {
  return DjsonApiSdk.create({
    host: HOST,
    headers: async () => ({}),
  })
}

const articlePayload = {
  type: "articles",
  id: "1",
  attributes: { title: "Hello World", content: "Some content" },
  relationships: {
    author: {
      data: { type: "users", id: "42" },
      links: { related: `${HOST}/articles/1/author` },
    },
    categories: {
      data: [
        { type: "categories", id: "10" },
        { type: "categories", id: "20" },
      ],
      links: { related: `${HOST}/articles/1/categories` },
    },
  },
  links: { self: `${HOST}/articles/1` },
}

const articleResponse = {
  jsonapi: { version: "1.0" },
  data: articlePayload,
  included: [],
}

const articleListResponse = {
  data: [
    articlePayload,
    {
      ...articlePayload,
      id: "2",
      attributes: { ...articlePayload.attributes, title: "Second Article" },
    },
  ],
  links: {
    first: `${HOST}/articles?page=1`,
    self: `${HOST}/articles?page=1`,
    next: `${HOST}/articles?page=2`,
    last: `${HOST}/articles?page=5`,
  },
  meta: { total: 10 },
}

function mockFetch(status = 200, body: unknown = {}) {
  const hasBody = status !== 204 && body != null
  return vi.fn().mockResolvedValue(
    new Response(hasBody ? JSON.stringify(body) : null, {
      status,
      headers: hasBody ? { "content-type": "application/vnd.api+json" } : undefined,
    }),
  )
}

describe("ResourceGet", () => {
  it("fetches by id", async () => {
    const sdk = createSdk()
    globalThis.fetch = mockFetch(200, articleResponse)

    const article = await (sdk as any).articles.get("1")
    expect(article.id).toBe("1")
    expect(article.get("title")).toBe("Hello World")
  })

  it("passes includes as params", async () => {
    const sdk = createSdk()
    globalThis.fetch = mockFetch(200, articleResponse)

    await (sdk as any).articles.get("1", "author")
    const call = (globalThis.fetch as any).mock.calls[0]
    expect(call[0]).toContain("include=author")
  })
})

describe("ResourceCreate", () => {
  it("creates and returns resource", async () => {
    const sdk = createSdk()
    const payload = {
      data: {
        type: "articles",
        id: "1",
        attributes: { title: "New" },
      },
    }
    globalThis.fetch = mockFetch(201, payload)

    const article = await (sdk as any).articles.create({ title: "New" })
    expect(article.id).toBe("1")
    expect(article.get("title")).toBe("New")
  })

  it("sends POST on create", async () => {
    const sdk = createSdk()
    globalThis.fetch = mockFetch(201, {
      data: { type: "articles", id: "1", attributes: { title: "New" } },
    })

    await (sdk as any).articles.create({ title: "New" })
    const call = (globalThis.fetch as any).mock.calls[0]
    expect(call[1].method).toBe("POST")
  })
})

describe("ResourceSave", () => {
  it("patches existing resource", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ id: "1", title: "Old" })
    globalThis.fetch = mockFetch(200, {
      data: { type: "articles", id: "1", attributes: { title: "Updated" } },
    })

    await article.save({ title: "Updated" })
    expect(article.get("title")).toBe("Updated")
  })

  it("posts new resource", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ title: "New" })
    globalThis.fetch = mockFetch(201, {
      data: { type: "articles", id: "1", attributes: { title: "New" } },
    })

    await article.save()
    expect(article.id).toBe("1")
  })

  it("sends POST for new resources", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ title: "New" })
    globalThis.fetch = mockFetch(201, {
      data: { type: "articles", id: "1", attributes: { title: "New" } },
    })

    await article.save()
    const call = (globalThis.fetch as any).mock.calls[0]
    expect(call[1].method).toBe("POST")
  })

  it("handles 204 no content", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ id: "1", title: "Old" })
    globalThis.fetch = mockFetch(204, null)

    await article.save({ title: "New" })
    expect(article.get("title")).toBe("New")
  })
})

describe("ResourceDelete", () => {
  it("deletes and clears id", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ id: "1" })
    globalThis.fetch = mockFetch(204, null)

    await article.delete()
    expect(article.id).toBeNull()
  })
})

describe("ResourceRefetch", () => {
  it("refetches from self link", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const article = new Article({ _data: articlePayload })
    article._fetched = false

    globalThis.fetch = mockFetch(200, {
      data: {
        ...articlePayload,
        attributes: { title: "Refreshed", content: "Updated" },
      },
    })

    await article.refetch()
    expect(article.get("title")).toBe("Refreshed")
    expect(article.get("content")).toBe("Updated")
  })
})

describe("ResourceAttributeAccess", () => {
  it("get reads attributes", () => {
    const sdk = createSdk()
    const r = new Resource({ _data: { type: "x", id: "1", attributes: { foo: "bar" } } })
    expect(r.get("foo")).toBe("bar")
  })

  it("get reads related", () => {
    const sdk = createSdk()
    const r = sdk._createResource({
      type: "x",
      id: "1",
      relationships: { author: { data: { type: "users", id: "42" } } },
    })
    expect(r.get("author")).toBeInstanceOf(Resource)
    expect((r.get("author") as Resource).id).toBe("42")
  })

  it("get returns undefined on unknown", () => {
    const r = new Resource({ _data: { type: "x", id: "1" } })
    expect(r.get("nonexistent")).toBeUndefined()
  })

  it("set updates attributes", () => {
    const r = new Resource({ _data: { type: "x", id: "1", attributes: { foo: "bar" } } })
    r.set("foo", "baz")
    expect(r.attributes.foo).toBe("baz")
    expect(r.get("foo")).toBe("baz")
  })

  it("set updates relationships", () => {
    const r = new Resource({
      _data: {
        type: "x",
        id: "1",
        relationships: { author: { data: { type: "users", id: "42" } } },
      },
    })
    r.set("author", { type: "users", id: "99" })
    expect(r.relationships.author?.data).toEqual({ type: "users", id: "99" })
  })

  it("toString shows id and attrs", () => {
    const r = new Resource({ _data: { type: "x", id: "1", attributes: { foo: "bar" } } })
    const str = r.toString()
    expect(str).toContain("id=1")
    expect(str).toContain("foo")
  })
})

describe("ResourcePostInit", () => {
  it("resolves singular relationship", () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const r = new Article({
      _data: {
        type: "articles",
        id: "1",
        relationships: { author: { data: { type: "users", id: "42" } } },
      },
    })
    const author = r.get("author")
    expect(author).toBeInstanceOf(Resource)
    expect((author as Resource).id).toBe("42")
  })

  it("resolves null singular relationship", () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const r = new Article({
      _data: {
        type: "articles",
        id: "1",
        relationships: { author: { data: null } },
      },
    })
    expect(r.get("author")).toBeNull()
  })

  it("resolves plural relationship to collection", () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const r = new Article({
      _data: {
        type: "articles",
        id: "1",
        relationships: {
          categories: {
            data: [{ type: "categories", id: "10" }],
            links: { related: `${HOST}/articles/1/categories` },
          },
        },
      },
    })
    const cats = r.get("categories")
    expect(cats).toBeInstanceOf(Collection)
    expect((cats as Collection)._data).not.toBeNull()
    expect(((cats as Collection)._data![0] as Resource).id).toBe("10")
  })

  it("constructs from kwargs", () => {
    const r = new Resource({ id: "1", foo: "bar" })
    expect(r.id).toBe("1")
    expect(r.attributes.foo).toBe("bar")
  })

  it("constructs with relationship kwargs", () => {
    const sdk = createSdk()
    const User = (sdk as any).users
    const author = new User({ id: "42" })
    const r = new Resource({ id: "1", author })
    expect(r.get("author")).toBeInstanceOf(Resource)
    expect((r.get("author") as Resource).id).toBe("42")
  })
})

describe("ResourceRelationshipMutation", () => {
  it("add", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const Category = (sdk as any).categories
    const article = new Article({ id: "1", categories: [] })
    globalThis.fetch = mockFetch(204, null)

    await article.add("categories", new Category({ id: "10" }))
    const call = (globalThis.fetch as any).mock.calls[0]
    expect(call[1].method).toBe("POST")
  })

  it("add multiple", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const Category = (sdk as any).categories
    const article = new Article({ id: "1", categories: [] })
    globalThis.fetch = mockFetch(204, null)

    await article.add("categories", new Category({ id: "10" }), new Category({ id: "20" }))
    expect((globalThis.fetch as any).mock.calls[0][1].method).toBe("POST")
  })

  it("remove", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const Category = (sdk as any).categories
    const article = new Article({ id: "1", categories: [] })
    globalThis.fetch = mockFetch(204, null)

    await article.remove("categories", new Category({ id: "10" }))
    expect((globalThis.fetch as any).mock.calls[0][1].method).toBe("DELETE")
  })

  it("reset", async () => {
    const sdk = createSdk()
    const Article = (sdk as any).articles
    const Category = (sdk as any).categories
    const article = new Article({ id: "1", categories: [] })
    globalThis.fetch = mockFetch(204, null)

    await article.reset("categories", new Category({ id: "10" }), new Category({ id: "20" }))
    expect((globalThis.fetch as any).mock.calls[0][1].method).toBe("PATCH")
  })
})
