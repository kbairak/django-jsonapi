import { describe, it, expect, vi, beforeEach } from "vitest"
import { DjsonApiSdk, Resource } from "../src/index.js"

const HOST = "http://testserver"


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

const userPayload = {
  type: "users",
  id: "42",
  attributes: { username: "jdoe", email: "jdoe@example.com" },
  links: { self: `${HOST}/users/42` },
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

describe("SdkSetup", () => {
  it("creates with host", () => {
    const sdk = DjsonApiSdk.create({ host: HOST, headers: async () => ({}) })
    expect(sdk.host).toBe(HOST)
  })

  it("creates with headers", async () => {
    const headers = async () => ({ Authorization: "Bearer x" })
    const sdk = DjsonApiSdk.create({ host: HOST, headers })
    expect(await sdk.headers()).toEqual({ Authorization: "Bearer x" })
  })
})

describe("SdkGetAttr", () => {
  it("returns resource type via proxy", () => {
    const sdk = DjsonApiSdk.create({ host: HOST, headers: async () => ({}) })
    const articles = (sdk as any).articles
    expect(articles).toBeInstanceOf(Function)
    expect(articles._type).toBe("articles")
    expect(articles._sdk).toBeInstanceOf(DjsonApiSdk)
    expect(articles._sdk.host).toBe(sdk.host)
  })

  it("caches resource types", () => {
    const sdk = DjsonApiSdk.create({ host: HOST, headers: async () => ({}) })
    const a1 = (sdk as any).articles
    const a2 = (sdk as any).articles
    expect(a1).toBe(a2)
  })

  it("plural access works", () => {
    const sdk = DjsonApiSdk.create({ host: HOST, headers: async () => ({}) })
    const articles = (sdk as any).articles
    expect(articles._type).toBe("articles")
  })
})

describe("SdkRequest", () => {
  it("sends JSON:API headers", async () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    globalThis.fetch = mockFetch(200, articleResponse)

    await sdk._request(`${HOST}/articles/1`)

    const call = (globalThis.fetch as any).mock.calls[0]
    const headers = call[1].headers
    expect(headers["content-type"]).toBe("application/vnd.api+json")
    expect(headers.accept).toBe("application/vnd.api+json")
  })

  it("sends custom headers", async () => {
    const sdk = DjsonApiSdk.create({
      host: HOST,
      headers: async () => ({ Authorization: "Bearer tok" }),
    })
    globalThis.fetch = mockFetch(200, articleResponse)

    await sdk._request(`${HOST}/articles/1`)

    const call = (globalThis.fetch as any).mock.calls[0]
    expect(call[1].headers.Authorization).toBe("Bearer tok")
  })
})

describe("SdkCreate", () => {
  it("creates resource from payload", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const resource = sdk._createResource(articlePayload)
    expect(resource._type).toBe("articles")
    expect(resource.id).toBe("1")
    expect(resource.get("title")).toBe("Hello World")
  })
})

describe("SdkParseResponse", () => {
  it("parses single resource", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const parsed = sdk._parseResponse(articleResponse as any)
    expect(parsed instanceof Resource).toBe(true)
    expect((parsed as Resource).id).toBe("1")
  })

  it("parses list response", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const a2 = { ...articlePayload, id: "2" }
    const response = { data: [articlePayload, a2] }
    const parsed = sdk._parseResponse(response as any)
    expect(Array.isArray(parsed)).toBe(true)
    expect(parsed).toHaveLength(2)
  })

  it("resolves included references", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const articleWithRel = {
      ...articlePayload,
      relationships: {
        author: { data: { type: "users", id: "42" } },
      },
    }
    const response = {
      data: articleWithRel,
      included: [userPayload],
    }
    const parsed = sdk._parseResponse(response as any) as Resource
    const author = parsed.get("author")
    expect(author).toBeInstanceOf(Resource)
    expect((author as Resource).id).toBe("42")
    expect((author as Resource).get("username")).toBe("jdoe")
  })

  it("resolves included collection refs", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const categoryPayload = {
      type: "categories",
      id: "10",
      attributes: { name: "Tech" },
    }
    const article = {
      type: "articles",
      id: "1",
      relationships: {
        categories: { data: [{ type: "categories", id: "10" }] },
      },
    }
    const response = { data: article, included: [categoryPayload] }
    const parsed = sdk._parseResponse(response as any) as Resource
    const cats = parsed.get("categories") as any
    expect(cats._data).not.toBeNull()
    expect(cats._data[0].get("name")).toBe("Tech")
  })

  it("sets meta on single resource", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const response = { data: articlePayload, meta: { foo: "bar" } }
    const parsed = sdk._parseResponse(response as any) as Resource
    expect(parsed.meta).toEqual({ foo: "bar" })
  })

  it("sets meta on list", () => {
    const sdk = new DjsonApiSdk({ host: HOST, headers: async () => ({}) })
    const a2 = { ...articlePayload, id: "2" }
    const response = { data: [articlePayload, a2], meta: { total: 10 } }
    const parsed = sdk._parseResponse(response as any) as Resource[]
    for (const r of parsed) {
      expect(r.meta).toEqual({ total: 10 })
    }
  })
})
