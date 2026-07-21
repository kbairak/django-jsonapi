# Typed Features

The generated SDK is more than just a generic HTTP client. It mirrors your
API's exact type system.

## Sealed resource types

The generated `SDK` subclass only exposes resource types that exist on your
server:

=== "Python"
    ```python
    sdk.articles   # ✅ exists
    sdk.users      # ✅ exists
    sdk.unknown    # ❌ AttributeError at runtime
    ```
=== "TypeScript"
    ```typescript
    sdk.articles   // ✅ exists
    sdk.users      // ✅ exists
    (sdk as any).unknown  // ❌ TypeError at runtime
    ```

The generic `DjsonApiSdk` creates resource classes on the fly for any
attribute. The generated `SDK` subclass overrides this with a sealed registry —
only the types declared in your API are accepted.

## Type conversions

Annotated types drive runtime conversion between JSON:API wire format and
native types:

| Python/TS type | JSON:API wire | Client access |
|----------------|---------------|---------------|
| `int` / `number` | `"42"` | `resource.id → 42` |
| `datetime` / `Date` | `"2026-07-17T10:00:00Z"` | `resource.created_at → datetime(...)` |
| `date` | `"2026-07-17"` | `resource.published_on → date(...)` |
| `UUID` / `string` | `"abc-123"` | `resource.uuid → UUID(...)` |
| `str` / `string` | `"hello"` | `resource.title → "hello"` |

Conversions are applied:

- On deserialization (GET responses → resource attributes)
- On serialization (save/create payloads → JSON:API wire format)

The generated code uses `_attribute_types` dict for this:

=== "Python"
    ```python
    class TypedArticle(Resource):
        _attribute_types = {
            "id": int,
            "title": str,
            "created_at": datetime,
        }
    ```
=== "TypeScript"
    ```typescript
    class TypedArticle extends Resource {
        static _attributeTypes: Record<string, string> = {
            id: "number",
            title: "string",
            createdAt: "Date",
        };
    }
    ```

## Relationship types

Relationships are typed to the correct target resource class:

=== "Python"
    ```python
    article = await sdk.articles.get(1, "author")
    # article.author is typed as User (not just Resource)
    reveal_type(article.author)  # User
    ```
=== "TypeScript"
    ```typescript
    const article = await sdk.articles.get(1, "author");
    // article.author is typed as User
    ```

This is driven by `_relationship_types`:

=== "Python"
    ```python
    class TypedArticle(Resource):
        _relationship_types = {
            "author": ("users", False),       # singular → User
            "categories": ("categories", True),  # plural → Collection[Category]
        }
    ```
=== "TypeScript"
    ```typescript
    class TypedArticle extends Resource {
        static _relationshipTypes: Record<string, [string, boolean]> = {
            author: ["users", false],
            categories: ["categories", true],
        };
    }
    ```

## Capability gating

Every resource class has a `_capabilities` frozenset that determines which
methods exist:

=== "Python"
    ```python
    # Generated code:
    class TypedArticle(Resource):
        _capabilities = frozenset({"get", "create", "edit", "delete"})
    ```

    At class definition time, methods are conditionally defined:

    - `"get"` → `get()`, `find()`
    - `"create"` → `create()`
    - `"edit"` → `save()`
    - `"delete"` → `delete()`
    - `"list"` → `list()`
=== "TypeScript"
    ```typescript
    class TypedArticle extends Resource {
        static _capabilities = new Set(["get", "create", "edit", "delete"]);
    }
    ```

Similarly, relationship capabilities gate mutation methods:

=== "Python"
    ```python
    class TypedArticle(Resource):
        _relationship_capabilities = {
            "categories": frozenset({"add", "remove", "reset"}),
            "author": frozenset({"edit"}),
        }
    ```

    No `article.add("categories", ...)` if `add` is not in the frozenset.
=== "TypeScript"
    ```typescript
    class TypedArticle extends Resource {
        static _relationshipCapabilities: Record<string, Set<string>> = {
            categories: new Set(["add", "remove", "reset"]),
            author: new Set(["edit"]),
        };
    }
    ```

## Query method typing

The generated `list()` method and associated `find()` have typed filter
parameters matching your endpoint's declared query parameters:

=== "Python"
    ```python
    articles = sdk.articles.list()
    # .filter() accepts only params your handler declared
    articles.filter(title__contains="django")
    # ❌ TypeError: articles.filter(nonexistent=...)  — unknown param
    ```
=== "TypeScript"
    ```typescript
    const articles = sdk.articles.list();
    articles.filter({ title__contains: "django" });
    ```

## `find()` overload

=== "Python"
    ```python
    # find() accepts filter kwargs + includes
    user = await sdk.users.find(username="admin")
    article = await sdk.articles.find(title__contains="django", "author")
    ```
=== "TypeScript"
    ```typescript
    const user = await sdk.users.find({ username: "admin" });
    const article = await sdk.articles.find(
        { title__contains: "django" },
        "author",
    );
    ```

## Fetch overload

=== "Python"
    ```python
    # Singular relationships return the correct type
    article = await sdk.articles.get(1, "author")
    await article.author  # returns User

    # Plural relationships return Collection of the correct type
    categories = await article.categories  # Collection[Category]
    ```
=== "TypeScript"
    ```typescript
    const article = await sdk.articles.get(1, "author");
    await article.author;  // returns User

    const categories = await article.categories;  // Collection<Category>
    ```
