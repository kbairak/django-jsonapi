function csv(value: unknown): string {
  if (Array.isArray(value)) return value.map(String).join(",")
  if (value instanceof Set) return Array.from(value).map(String).join(",")
  return String(value)
}

export function translateQuery(
  query: Record<string, unknown>,
): Record<string, string> {
  const params: Record<string, string> = {}
  const includes: string[] = []

  for (let [key, value] of Object.entries(query)) {
    if (value == null || value === false) continue

    if (key.startsWith("filter__")) {
      const parts = key.slice("filter__".length).split("__")
      params[`filter[${parts.join("][")}]`] = csv(value)
    } else if (key === "page") {
      params.page = String(value)
    } else if (key.startsWith("page__")) {
      params[`page[${key.slice("page__".length)}]`] = String(value)
    } else if (key === "sort") {
      params.sort = csv(value)
    } else if (key.startsWith("include__")) {
      includes.push(key.slice("include__".length).replace(/__/g, "."))
    } else if (key.startsWith("fields__")) {
      params[`fields[${key.slice("fields__".length)}]`] = csv(value)
    } else if (key.startsWith("extra__")) {
      params[key.slice("extra__".length)] = csv(value)
    } else {
      params[key] = csv(value)
    }
  }

  if (includes.length) params.include = includes.join(",")
  return params
}
