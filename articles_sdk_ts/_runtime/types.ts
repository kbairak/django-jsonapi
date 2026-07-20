export interface Document<T = ResourceObject | ResourceObject[]> {
  data: T
  included?: ResourceObject[]
  links?: Links
  meta?: Record<string, unknown>
  jsonapi?: { version: string }
  errors?: ErrorObject[]
}

export interface ResourceObject {
  type: string
  id: string
  attributes?: Record<string, unknown>
  relationships?: Record<string, RelationshipObject>
  links?: Links
  meta?: Record<string, unknown>
}

export interface RelationshipObject {
  data?: ResourceIdentifier | ResourceIdentifier[] | null
  links?: Links
  meta?: Record<string, unknown>
}

export interface ResourceIdentifier {
  type: string
  id: string
  meta?: Record<string, unknown>
}

export interface Links {
  [key: string]: string | undefined
  self?: string
  related?: string
  first?: string
  prev?: string
  next?: string
  last?: string
}

export interface ErrorObject {
  status?: string
  code?: string
  title?: string
  detail?: string
  source?: { pointer?: string; parameter?: string }
  meta?: Record<string, unknown>
}
