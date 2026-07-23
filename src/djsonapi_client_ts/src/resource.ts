import { Collection } from "./collection.js"
import { translateQuery } from "./query.js"
import type { DjsonApiSdk, ResourceConstructor } from "./sdk.js"
import type {
  RelationshipObject,
  ResourceIdentifier,
  ResourceObject,
} from "./types.js"

interface ResourceInit {
  _data?: ResourceObject
  id?: string
  [key: string]: unknown
}

export class Resource {
  id: string | null = null
  attributes: Record<string, unknown> = {}
  relationships: Record<string, RelationshipObject> = {}
  links: Record<string, string> = {}
  meta: Record<string, unknown> = {}
  _related: Record<string, unknown> = {}
  _fetched = false

  static _type = ""
  static _sdk: DjsonApiSdk | null = null
  static _relationshipTypes: Record<string, [string, boolean]> = {}
  static _collectionClass: typeof Collection = Collection
  static _rpcMethods: Record<string, string> = {}

  get _sdk(): DjsonApiSdk {
    return (this.constructor as typeof Resource)._sdk!
  }

  get _type(): string {
    return (this.constructor as typeof Resource)._type
  }

  constructor(props?: ResourceInit) {
    if (!props) return

    if (props._data) {
      const data = props._data
      this.id = data.id
      this.attributes = (data.attributes as Record<string, unknown>) ?? {}
      this.relationships = (data.relationships as Record<string, RelationshipObject>) ?? {}
      this.links = Object.fromEntries(
        Object.entries(data.links ?? {}),
      ) as Record<string, string>
      this._postInit()
      this._fetched = !!(data.attributes || data.relationships)
      return
    }

    if (props.id != null) {
      this.id = props.id
    }

    for (const [key, value] of Object.entries(props)) {
      if (key === "_data" || key === "id") continue
      this._setAttrOrRel(key, value)
    }
  }

  private _postInit(): void {
    for (const [name, relationship] of Object.entries(this.relationships)) {
      if (isSingular(relationship)) {
      this._related[name] = this._relatedSingular(
        (relationship.data as ResourceIdentifier | null) ?? null,
        relationship.links ?? {} as Record<string, string>,
      )
      } else {
        const url = relationship.links?.related ?? ""
        const sdk = this._sdk
        const data = Array.isArray(relationship.data)
          ? relationship.data.map((ri: ResourceIdentifier) => {
              if (sdk) return sdk._createResource(ri as unknown as ResourceObject)
              return new Resource({ _data: { type: ri.type, id: ri.id } })
            })
          : null
        this._related[name] = new (this.constructor as typeof Resource)
          ._collectionClass(sdk, url, { _data: data })
      }
    }
  }

  private _relatedSingular(
    ri: ResourceIdentifier | null,
    links: Record<string, string | undefined>,
  ): Resource | null {
    if (!ri) return null
    const sdk = (this.constructor as typeof Resource)._sdk
    if (sdk) {
      const r = sdk._createResource(ri as unknown as ResourceObject)
      r.links.self = links.related ?? r.links.self
      return r
    }
    const r = new Resource({ _data: { type: ri.type, id: ri.id } })
    r.links.self = links.related ?? r.links.self
    return r
  }

  get<T = unknown>(name: string): T | undefined {
    if (name in this.attributes) {
      return this.attributes[name] as T
    }
    if (name in this._related) {
      return this._related[name] as T
    }
    return undefined
  }

  set(name: string, value: unknown): void {
    if (name in this.attributes) {
      this.attributes[name] = value
      return
    }

    if (name in (this.constructor as typeof Resource)._relationshipTypes) {
      const [target, plural] = (this.constructor as typeof Resource)
        ._relationshipTypes[name]
      this.relationships[name] = this._coerceRelationship(name, value)
      this._related[name] = this._coerceRelated(name, value)
      return
    }

    if (name in this.relationships) {
      this.relationships[name] = toRelationship(value)
      this._related[name] = toRelatedValue(value, this)
      return
    }

    if (isRelationship(value)) {
      this.relationships[name] = toRelationship(value)
      this._related[name] = toRelatedValue(value, this)
    } else {
      this.attributes[name] = value
    }
  }

  private _setAttrOrRel(name: string, value: unknown): void {
    const relTypes = (this.constructor as typeof Resource)._relationshipTypes
    if (name in relTypes) {
      const [target, plural] = relTypes[name]
      this.relationships[name] = this._coerceRelationship(name, value)
      this._related[name] = this._coerceRelated(name, value)
    } else if (isRelationship(value)) {
      this.relationships[name] = toRelationship(value)
      this._related[name] = toRelatedValue(value, this)
    } else {
      this.attributes[name] = value
    }
  }

  private _coerceRelationship(
    name: string,
    value: unknown,
  ): RelationshipObject {
    const [target, plural] = (this.constructor as typeof Resource)
      ._relationshipTypes[name]
    if (value == null) {
      return { data: plural ? [] : null }
    }
    if (plural) {
      const items = Array.isArray(value) ? value : [value]
      return {
        data: items.map((v) => toRi(v, target)),
      }
    }
    return { data: toRi(value, target) }
  }

  private _coerceRelated(name: string, value: unknown): unknown {
    const [target, plural] = (this.constructor as typeof Resource)
      ._relationshipTypes[name]

    const stub = (item: unknown): Resource => {
      const ri = toRi(item, target)
      return this._sdk._createResource(
        ri as unknown as ResourceObject,
      )
    }

    if (plural) {
      const items = value == null ? [] : Array.isArray(value) ? value : [value]
      return new (this.constructor as typeof Resource)._collectionClass(
        this._sdk,
        "",
        { _data: items.map(stub) },
      )
    }
    if (value == null) return null
    return stub(value)
  }

  static async get(
    id: string,
    ...includes: string[]
  ): Promise<any> {
    const cls = this as any
    const params: Record<string, string> = {}
    if (includes.length) params.include = includes.join(",")
    const body = await cls._sdk._request(`${cls._type}/${id}`, { params })
    return cls._sdk._parseResponse(body!)
  }

  static async find(
    query: Record<string, unknown>,
  ): Promise<any> {
    if (!Object.keys(query).length) throw new TypeError("find() requires filter arguments")
    const cls = this as any
    const col = cls.list()
    const result = col.filter(query)
    await result.fetch()
    if (result._data!.length !== 1) {
      throw new Error(
        `Expected 1 result, got ${result._data!.length}`,
      )
    }
    return result._data![0]
  }

  static async create(
    props: Record<string, unknown> = {},
  ): Promise<any> {
    const cls = this as any
    const resource = new cls(props)
    const payload = resource._payload()
    const body = await cls._sdk._request(`${cls._type}`, {
      method: "POST",
      body: { data: payload },
    })
    const doc = body
    const data = doc?.data
    if (!data) return new cls()
    return cls._sdk._parseResponse(body!)
  }

  async save(
    ...fieldsOrKwargs: unknown[]
  ): Promise<void> {
    let fields: string[] | undefined
    let kwargs: Record<string, unknown> | undefined

    if (
      fieldsOrKwargs.length === 1 &&
      typeof fieldsOrKwargs[0] === "object" &&
      !Array.isArray(fieldsOrKwargs[0])
    ) {
      kwargs = fieldsOrKwargs[0] as Record<string, unknown>
      for (const [key, value] of Object.entries(kwargs)) {
        this.set(key, value)
      }
      fields = Object.keys(kwargs)
    } else if (
      fieldsOrKwargs.length > 0 &&
      fieldsOrKwargs.every((f) => typeof f === "string")
    ) {
      fields = fieldsOrKwargs as string[]
    }

    const payload = this._payload(fields)
    const sdk = this._sdk

    if (this.id != null) {
      const body = await sdk._request(`${this._type}/${this.id}`, {
        method: "PATCH",
        body: { data: payload },
      })
      if (body) {
        const parsed = sdk._parseResponse(body) as Resource
        this._applyParsed(parsed)
      }
    } else {
      const body = await sdk._request(`${this._type}`, {
        method: "POST",
        body: { data: payload },
      })
      if (body) {
        const data = body.data as ResourceObject
        if (data) {
          const parsed = sdk._parseResponse(body) as Resource
          this._applyParsed(parsed)
        }
      }
    }
  }

  private _applyParsed(parsed: Resource): void {
    this.id = parsed.id
    this.attributes = parsed.attributes
    this.relationships = parsed.relationships
    this.links = parsed.links
    this.meta = parsed.meta
    this._related = parsed._related
  }

  _payload(fields?: string[]): Record<string, unknown> {
    const payload: Record<string, unknown> = { type: this._type }
    if (this.id != null) payload.id = this.id

    let attrs: Record<string, unknown>
    let rels: Record<string, RelationshipObject>

    if (fields) {
      attrs = {}
      rels = {}
      for (const f of fields) {
        if (f in this.attributes) attrs[f] = this.attributes[f]
        if (f in this.relationships) rels[f] = this.relationships[f]
      }
    } else {
      attrs = { ...this.attributes }
      rels = { ...this.relationships }
    }

    if (Object.keys(attrs).length) payload.attributes = attrs
    if (Object.keys(rels).length) {
      payload.relationships = Object.fromEntries(
        Object.entries(rels).map(([k, v]) => [k, strRelationshipIds(v)]),
      )
    }
    return payload
  }

  async delete(): Promise<void> {
    if (this.id == null) throw new Error("Cannot delete resource without id")
    await this._sdk._request(`${this._type}/${this.id}`, {
      method: "DELETE",
    })
    this.id = null
  }

  async refetch(): Promise<void> {
    const url = this.links.self || `${this._type}/${this.id}`
    const body = await this._sdk._request(url)
    const parsed = this._sdk._parseResponse(body!) as Resource
    this._applyParsed(parsed)
    this._fetched = true
  }

  static list(): Collection {
    const cls = this as unknown as typeof Resource & { _sdk: DjsonApiSdk; _type: string }
    const colClass = cls._collectionClass as unknown as typeof Collection
    return new colClass(cls._sdk, `${cls._type}`, {})
  }

  private _mutationRis(
    relationship: string,
    resources: unknown[],
  ): ResourceIdentifier[] {
    if (resources.length === 1 && Array.isArray(resources[0])) {
      resources = resources[0]
    }
    const relTypes = (this.constructor as typeof Resource)._relationshipTypes
    if (relationship in relTypes) {
      const target = relTypes[relationship][0]
      return resources.map((r) => toRi(r, target))
    }
    return resources.map((r) => toRi(r))
  }

  async add(relationship: string, ...resources: unknown[]): Promise<void> {
    await this._mutateRelationship(
      "POST",
      relationship,
      this._mutationRis(relationship, resources),
    )
  }

  async remove(
    relationship: string,
    ...resources: unknown[]
  ): Promise<void> {
    await this._mutateRelationship(
      "DELETE",
      relationship,
      this._mutationRis(relationship, resources),
    )
  }

  async reset(relationship: string, ...resources: unknown[]): Promise<void> {
    await this._mutateRelationship(
      "PATCH",
      relationship,
      this._mutationRis(relationship, resources),
    )
  }

  async rpc(action: string, payload?: unknown, mimetype?: string): Promise<any> {
    const method = (this.constructor as typeof Resource)._rpcMethods[action] ?? "POST"
    const url = new URL(`${this._type}/${this.id}/${action}`, this._sdk.host).toString()
    const headers: Record<string, string> = {}
    let body: BodyInit | undefined
    if (payload !== undefined) {
      if (mimetype) {
        headers["content-type"] = mimetype
        body = JSON.stringify(payload)
      } else {
        body = JSON.stringify(payload)
      }
    }
    const res = await fetch(url, { method, headers, body })
    if (!res.ok) {
      const text = await res.text()
      let parsed: any
      try { parsed = JSON.parse(text) } catch { throw new Error(`RPC failed: ${res.status}`) }
      this._sdk._raiseForStatus(res.status, parsed)
    }
    const text = await res.text()
    try { return JSON.parse(text) } catch { return text }
  }

  async edit(relationship: string, resource: unknown): Promise<void> {
    const ri = this._mutationRis(relationship, [resource])[0]
    await this._sdk._request(
      `${this._type}/${this.id}/relationship/${relationship}`,
      { method: "PATCH", body: { data: ri } },
    )
    const rel = (this.relationships[relationship] ??= { data: ri })
    rel.data = ri
    this._invalidateRelated(relationship)
  }

  private _invalidateRelated(name: string): void {
    if (!(name in this._related)) return
    const rel = this.relationships[name]
    if (isSingular(rel)) {
      this._related[name] = this._relatedSingular(
        (rel.data as ResourceIdentifier | null) ?? null,
        rel.links ?? {} as Record<string, string>,
      )
    } else {
      const url = rel.links?.related ?? ""
      this._related[name] = new (this.constructor as typeof Resource)
        ._collectionClass(this._sdk, url, {})
    }
  }

  private async _mutateRelationship(
    method: string,
    relationship: string,
    data: ResourceIdentifier[],
  ): Promise<void> {
    await this._sdk._request(
      `${this._type}/${this.id}/relationship/${relationship}`,
      {
        method,
        body: { data },
      },
    )

    const rel = (this.relationships[relationship] ??= { data: [] })

    if (method === "PATCH") {
      ;(rel.data as ResourceIdentifier[]) = [...data]
    } else {
      if (!Array.isArray(rel.data)) rel.data = []
      const existing = rel.data as ResourceIdentifier[]
      if (method === "POST") {
        const existingIds = new Set(
          existing.map((ri) => ri.id).filter(Boolean),
        )
        for (const ri of data) {
          if (!existingIds.has(ri.id)) {
            existing.push(ri)
            existingIds.add(ri.id)
          }
        }
      } else {
        const removeIds = new Set(data.map((ri) => ri.id))
        rel.data = existing.filter(
          (ri) => !removeIds.has(ri.id),
        ) as ResourceIdentifier[]
      }
    }

    this._invalidateRelated(relationship)
  }

  toString(): string {
    const parts: string[] = []
    if (this.id != null) parts.push(`id=${this.id}`)
    if (Object.keys(this.attributes).length) {
      parts.push(
        `attributes={${Object.keys(this.attributes).join(", ")}}`,
      )
    }
    if (Object.keys(this.relationships).length) {
      parts.push(
        `relationships={${Object.keys(this.relationships).join(", ")}}`,
      )
    }
    return `${this.constructor.name}(${parts.join(", ")})`
  }
}

export function isSingular(
  relationship: RelationshipObject,
): boolean {
  return "data" in relationship && !Array.isArray(relationship.data)
}

export function isRelationship(value: unknown): boolean {
  if (value instanceof Resource) return true
  if (Array.isArray(value)) {
    if (value.length === 0) return true
    if (value.every((v) => v instanceof Resource)) return true
    if (
      value.every(
        (v) =>
          typeof v === "object" &&
          v != null &&
          "type" in v &&
          "id" in v,
      )
    )
      return true
    return false
  }
  if (typeof value === "object" && value != null) {
    if ("type" in value && "id" in value) return true
    if ("data" in value) return true
  }
  return false
}

export function toRelationship(value: unknown): RelationshipObject {
  if (value instanceof Resource) {
    return { data: { type: value._type, id: value.id! } }
  }
  if (Array.isArray(value)) {
    return { data: value.map((v) => toRi(v)) }
  }
  if (typeof value === "object" && value != null) {
    const obj = value as Record<string, unknown>
    if ("type" in obj && "id" in obj) return { data: { type: String(obj.type), id: String(obj.id) } }
    if ("data" in obj) return value as unknown as RelationshipObject
  }
  return { data: { type: "", id: String(value) } }
}

export function toRi(
  value: unknown,
  target?: string,
): ResourceIdentifier {
  if (value instanceof Resource) {
    return { type: value._type, id: value.id! }
  }
  if (typeof value === "object" && value != null) {
    const obj = value as Record<string, unknown>
    if ("type" in obj && "id" in obj) return { type: String(obj.type), id: String(obj.id) }
    const rel = value as RelationshipObject
    if (rel.data && !Array.isArray(rel.data))
      return rel.data as ResourceIdentifier
  }
  return { type: target ?? "", id: String(value) }
}

export function toRelatedValue(
  value: unknown,
  ctx: Resource,
): unknown {
  const sdk = ctx._sdk

  if (value instanceof Resource) return value

  if (Array.isArray(value)) {
    const items: Resource[] = []
    for (const v of value) {
      if (v instanceof Resource) items.push(v)
      else if (
        typeof v === "object" &&
        v != null &&
        "type" in v &&
        "id" in v
      ) {
        items.push(sdk._createResource(v as unknown as ResourceObject))
      } else if (
        typeof v === "object" &&
        v != null &&
        "data" in (v as Record<string, unknown>)
      ) {
        const d = (v as unknown as RelationshipObject).data
        if (Array.isArray(d)) {
          for (const item of d)
            items.push(sdk._createResource(item as unknown as ResourceObject))
        } else if (d != null) {
          items.push(sdk._createResource(d as unknown as ResourceObject))
        }
      }
    }
    return new (ctx.constructor as typeof Resource)._collectionClass(
      sdk,
      "",
      { _data: items },
    )
  }

  if (typeof value === "object" && value != null) {
    const obj = value as Record<string, unknown>
    if ("type" in obj && "id" in obj) {
      if (sdk) return sdk._createResource(obj as unknown as ResourceObject)
      return new Resource({ _data: obj as unknown as ResourceObject })
    }
    if ("data" in obj) {
      const data = obj.data as unknown
      if (data === null) return null
      if (Array.isArray(data)) {
        const items = data.map((item: ResourceObject) =>
          sdk ? sdk._createResource(item) : new Resource({ _data: item }),
        )
        return new (ctx.constructor as typeof Resource)._collectionClass(
          sdk,
          "",
          { _data: items },
        )
      }
      if (sdk) return sdk._createResource(data as ResourceObject)
      return new Resource({ _data: data as ResourceObject })
    }
  }
  return value
}

export function strRelationshipIds(
  relationship: RelationshipObject,
): RelationshipObject {
  if (!relationship || typeof relationship !== "object") return relationship
  const data = relationship.data
  if (Array.isArray(data)) {
    return {
      ...relationship,
      data: data.map((ri) => ({ ...ri, id: String(ri.id) })),
    }
  }
  if (data && typeof data === "object") {
    return {
      ...relationship,
      data: { ...data, id: String(data.id) },
    }
  }
  return relationship
}
