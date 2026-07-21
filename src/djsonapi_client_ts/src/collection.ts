import { translateQuery } from "./query.js"
import type { Resource } from "./resource.js"
import type { DjsonApiSdk } from "./sdk.js"
import type { Links } from "./types.js"

interface CollectionInit {
  _data?: Resource[] | null
}

export class Collection<T extends Resource = Resource> {
  _sdk: DjsonApiSdk
  _url: string
  _params: Record<string, string>
  _data: T[] | null
  _links: Links = {}
  meta: Record<string, unknown> = {}

  constructor(
    sdk: DjsonApiSdk,
    url: string,
    init: CollectionInit | Record<string, unknown> = {},
  ) {
    this._sdk = sdk
    this._url = url
    this._params = {}

    const parsedUrl = new URL(url, "http://x")
    if (parsedUrl.search) {
      this._url = url.split("?")[0]
      for (const [k, v] of parsedUrl.searchParams.entries()) {
        this._params[k] = v
      }
    }

    if (init && "_data" in init) {
      this._data = (init as CollectionInit)._data as T[] | null
    } else {
      this._data = null
      if (init && Object.keys(init).length > 0) {
        for (const [k, v] of Object.entries(init)) {
          this._params[k] = String(v)
        }
      }
    }
  }

  async fetch(): Promise<this> {
    if (this._data != null) return this
    const body = await this._sdk._request(this._url, {
      params: this._params,
    })
    if (!body) return this
    const parsed = this._sdk._parseResponse(body)
    this._data = (Array.isArray(parsed) ? parsed : [parsed]) as T[]
    const rec = body as unknown as Record<string, unknown>
    this._links = (rec.links as Links) ?? {}
    this.meta = (rec.meta as Record<string, unknown>) ?? {}
    return this
  }

  async refetch(): Promise<void> {
    this._data = null
    await this.fetch()
  }

  /**
   * Access item at index. For array methods (map, filter, slice, etc.),
   * spread into array first: `[...articles].map(...)`
   */
  at(index: number): T | undefined {
    if (this._data == null) {
      throw new Error("Data not fetched yet. Use 'await collection' first.")
    }
    return this._data[index]
  }

  get length(): number {
    if (this._data == null) {
      throw new Error("Data not fetched yet. Use 'await collection' first.")
    }
    return this._data.length
  }

  *[Symbol.iterator](): Generator<T> {
    if (this._data == null) {
      throw new Error("Data not fetched yet. Use 'await collection' first.")
    }
    for (const item of this._data) {
      yield item
    }
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<T> {
    await this.fetch()
    for (const item of this._data!) {
      yield item
    }
  }

  filter(kwargs: Record<string, unknown>): this {
    const prefixed: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(kwargs)) {
      prefixed[`filter__${k}`] = v
    }
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      { ...this._params, ...translateQuery(prefixed) },
    )
  }

  include(...names: string[]): this {
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      { ...this._params, include: names.join(",") },
    )
  }

  fields(fieldMap: Record<string, string[]>): this {
    const newParams: Record<string, string> = { ...this._params }
    for (const [resource, attrs] of Object.entries(fieldMap)) {
      newParams[`fields[${resource}]`] = attrs.join(",")
    }
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      newParams,
    )
  }

  sort(...fields: string[]): this {
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      { ...this._params, sort: fields.join(",") },
    )
  }

  page(pageOrParams: number | string | Record<string, string>): this {
    let newParams: Record<string, string>
    if (typeof pageOrParams === "number" || typeof pageOrParams === "string") {
      newParams = { page: String(pageOrParams) }
    } else {
      newParams = {}
      for (const [k, v] of Object.entries(pageOrParams)) {
        newParams[`page[${k}]`] = v
      }
    }
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      { ...this._params, ...newParams },
    )
  }

  extra(params: Record<string, string>): this {
    return new (this.constructor as new (
      ...args: unknown[]
    ) => this)(
      this._sdk,
      this._url,
      { ...this._params, ...params },
    )
  }

  hasNext(): boolean {
    return "next" in this._links
  }

  getNext(): this {
    return new (this.constructor as new (...args: unknown[]) => this)(
      this._sdk,
      this._links.next!,
      this._params,
    )
  }

  hasPrevious(): boolean {
    return "prev" in this._links
  }

  getPrevious(): this {
    return new (this.constructor as new (...args: unknown[]) => this)(
      this._sdk,
      this._links.prev!,
      this._params,
    )
  }

  hasFirst(): boolean {
    return "first" in this._links
  }

  getFirst(): this {
    return new (this.constructor as new (...args: unknown[]) => this)(
      this._sdk,
      this._links.first!,
      this._params,
    )
  }

  hasLast(): boolean {
    return "last" in this._links
  }

  getLast(): this {
    return new (this.constructor as new (...args: unknown[]) => this)(
      this._sdk,
      this._links.last!,
      this._params,
    )
  }

  async *allPages(): AsyncGenerator<Collection<Resource>> {
    let current: Collection<Resource> = await (this.fetch() as any)
    while (true) {
      yield current
      if (current.hasNext()) {
        current = await (current.getNext().fetch() as any)
      } else {
        break
      }
    }
  }

  async *all(): AsyncGenerator<Resource> {
    for await (const page of (this.allPages() as any)) {
      for (const item of page) {
        yield item as Resource
      }
    }
  }
}
