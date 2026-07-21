import { describe, it, expect, vi } from "vitest"
import { DjsonApiSdk, Collection, Resource } from "../src/index.js"

const HOST = "http://testserver"


const articlePayload = {
  type: "articles",
  id: "1",
  attributes: { title: "Hello World" },
}

const articlePayload2 = {
  type: "articles",
  id: "2",
  attributes: { title: "Second Article" },
}

const articleListResponse = {
  data: [articlePayload, articlePayload2],
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

describe("CollectionAwait", () => {
  it("populates data on await", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {})
    expect(col._data).toBeNull()

    globalThis.fetch = mockFetch(200, articleListResponse)

    const result = await col.fetch()
    expect(result).toBe(col)
    expect(col._data).not.toBeNull()
    expect(col._data).toHaveLength(2)
  })

  it("sets links on fetch", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col._links.next).toBeDefined()
    expect(col._links.last).toBeDefined()
  })

  it("sets meta on fetch", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.meta).toEqual({ total: 10 })
  })

  it("is idempotent", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    const first = col._data
    await col.fetch()
    expect(col._data).toBe(first)
  })
})

describe("CollectionChaining", () => {
  it("filter", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).filter({
      title: "hello",
    })
    expect(col._params["filter[title]"]).toBe("hello")
  })

  it("filter chains", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {})
      .filter({ title: "hello" })
      .filter({ author: "42" })
    expect(col._params).toEqual({
      "filter[title]": "hello",
      "filter[author]": "42",
    })
  })

  it("include", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).include(
      "author",
      "categories",
    )
    expect(col._params.include).toBe("author,categories")
  })

  it("sort", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).sort(
      "title",
      "-created_at",
    )
    expect(col._params.sort).toBe("title,-created_at")
  })

  it("fields", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).fields({
      articles: ["title", "content"],
    })
    expect(col._params["fields[articles]"]).toBe("title,content")
  })

  it("page with number", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).page(2)
    expect(col._params.page).toBe("2")
  })

  it("page with params", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).page({
      size: "20",
      number: "3",
    })
    expect(col._params["page[size]"]).toBe("20")
    expect(col._params["page[number]"]).toBe("3")
  })

  it("extra", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {}).extra({
      custom: "value",
    })
    expect(col._params.custom).toBe("value")
  })

  it("returns new collection on filter", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {})
    const filtered = col.filter({ title: "hello" })
    expect(col === filtered).toBe(false)
    expect(col._params).toEqual({})
  })

  it("extracts url params on init", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles?foo=bar`, {})
    expect(col._url).toBe(`${HOST}/articles`)
    expect(col._params).toEqual({ foo: "bar" })
  })
})

describe("CollectionAccess", () => {
  it("at returns item by index", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.at(0)!.get("title")).toBe("Hello World")
    expect(col.at(1)!.get("title")).toBe("Second Article")
  })

  it("at unfetched throws", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {})
    expect(() => col.at(0)).toThrow("not fetched")
  })

  it("length", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.length).toBe(2)
  })

  it("length unfetched throws", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const col = new Collection(sdk, `${HOST}/articles`, {})
    expect(() => col.length).toThrow("not fetched")
  })
})

describe("CollectionIteration", () => {
  it("async iterator yields items", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    const titles: string[] = []
    for await (const item of col) {
      titles.push(item.get("title") as string)
    }
    expect(titles).toEqual(["Hello World", "Second Article"])
  })
})

describe("CollectionPagination", () => {
  it("hasNext", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.hasNext()).toBe(true)
  })

  it("hasNext false when missing", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, { data: [] })

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.hasNext()).toBe(false)
  })

  it("getNext", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    const next = col.getNext()
    expect(next._url).toBe(`${HOST}/articles`)
    expect(next._params).toEqual({ page: "2" })
  })

  it("hasPrevious", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.hasPrevious()).toBe(false)
  })

  it("hasFirst and hasLast", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleListResponse)

    const col = new Collection(sdk, `${HOST}/articles`, {})
    await col.fetch()
    expect(col.hasFirst()).toBe(true)
    expect(col.hasLast()).toBe(true)
  })

  it("allPages follows pagination", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const p1 = {
      data: [{ type: "articles", id: "1" }],
      links: { next: `${HOST}/articles?page=2` },
    }
    const p2 = { data: [{ type: "articles", id: "2" }] }

    const mock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(p1), {
          status: 200,
          headers: { "content-type": "application/vnd.api+json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(p2), {
          status: 200,
          headers: { "content-type": "application/vnd.api+json" },
        }),
      )
    globalThis.fetch = mock

    const col = new Collection(sdk, `${HOST}/articles`, {})
    const pages: Collection[] = []
    for await (const page of col.allPages()) {
      pages.push(page)
    }
    expect(pages).toHaveLength(2)
    expect(pages[0]._data![0].id).toBe("1")
    expect(pages[1]._data![0].id).toBe("2")
  })

  it("all yields all items across pages", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const p1 = {
      data: [
        {
          type: "articles",
          id: "1",
          attributes: { title: "A" },
        },
      ],
      links: { next: `${HOST}/articles?page=2` },
    }
    const p2 = {
      data: [
        {
          type: "articles",
          id: "2",
          attributes: { title: "B" },
        },
      ],
    }

    const mock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(p1), {
          status: 200,
          headers: { "content-type": "application/vnd.api+json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(p2), {
          status: 200,
          headers: { "content-type": "application/vnd.api+json" },
        }),
      )
    globalThis.fetch = mock

    const col = new Collection(sdk, `${HOST}/articles`, {})
    const titles: string[] = []
    for await (const item of col.all()) {
      titles.push(item.get("title") as string)
    }
    expect(titles).toEqual(["A", "B"])
  })
})
