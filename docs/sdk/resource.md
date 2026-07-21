# Resources & CRUD

## Fetching

### `get(id, *includes)`

=== "Python"
    ```python
    article = await sdk.articles.get(1)
    # GET /articles/1

    article = await sdk.articles.get(1, "author", "categories")
    # GET /articles/1?include=author,categories
    ```
=== "TypeScript"
    ```typescript
    const article = await sdk.articles.get(1);
    // GET /articles/1

    const article2 = await sdk.articles.get(1, "author", "categories");
    // GET /articles/1?include=author,categories
    ```

### `find(**query, *includes)`

Fetch a single resource by filter. Asserts exactly one result.

=== "Python"
    ```python
    user = await sdk.users.find(username="admin")
    # GET /users?filter[username]=admin

    article = await sdk.articles.find(title__contains="django", "author")
    # GET /articles?filter[title][contains]=django&include=author
    ```
=== "TypeScript"
    ```typescript
    const user = await sdk.users.find({ username: "admin" });
    // GET /users?filter[username]=admin

    const article = await sdk.articles.find(
        { title__contains: "django" },
        "author",
    );
    // GET /articles?filter[title][contains]=django&include=author
    ```

### `list()`

Returns a lazy `Collection` — see [Collections](collection.md).

=== "Python"
    ```python
    articles = sdk.articles.list()
    # No HTTP request yet

    articles = await articles
    # GET /articles
    ```
=== "TypeScript"
    ```typescript
    const articles = sdk.articles.list();
    // No HTTP request yet

    await articles.fetch();
    // GET /articles
    ```

## Creating

=== "Python"
    ```python
    article = await sdk.articles.create(
        title="New Post",
        content="Hello",
        author=admin_user,  # Resource or ID
    )
    # POST /articles
    ```

    If you `save()` a resource without an ID, it issues a POST (not PATCH):

    ```python
    article = sdk.articles._new(title="New Post", content="Hello")
    # article.id is None
    await article.save()
    # POST /articles — creates, returns with server-assigned ID
    ```

    For client-generated IDs, use `create()`:

    ```python
    article = await sdk.articles.create(id=42, title="New Post")
    # POST /articles — server must support client IDs
    ```

=== "TypeScript"
    ```typescript
    const article = await sdk.articles.create({
        title: "New Post",
        content: "Hello",
        author: adminUser,  // Resource or ID
    });
    // POST /articles
    ```

Available only if `@api.create_one` was registered.

## Updating

Two equivalent forms:

=== "Python"
    ```python
    # Form 1 — pass fields as kwargs
    await article.save(title="Updated", content="New content")
    # PATCH /articles/1

    # Form 2 — set attributes, then save with field names
    article.title = "Updated"
    article.content = "New content"
    await article.save("title", "content")
    # PATCH /articles/1
    ```
=== "TypeScript"
    ```typescript
    // Form 1 — pass fields as object
    await article.save({ title: "Updated", content: "New content" });
    // PATCH /articles/1

    // Form 2 — set attributes, then save with field names
    article.title = "Updated";
    article.content = "New content";
    await article.save("title", "content");
    // PATCH /articles/1
    ```

### `refetch()`

Always hits the network, replaces local state:

=== "Python"
    ```python
    await article.refetch()
    # GET /articles/1
    ```
=== "TypeScript"
    ```typescript
    await article.refetch();
    // GET /articles/1
    ```

## Deleting

=== "Python"
    ```python
    await article.delete()
    # DELETE /articles/1  → 204
    # article.id is now None
    ```
=== "TypeScript"
    ```typescript
    await article.delete();
    // DELETE /articles/1  → 204
    // article.id is now null
    ```

Available only if `@api.delete_one` was registered.

## Relationships

### Accessing relationships

When a resource has a relationship, you access it as a regular attribute.
Whether it's immediately usable depends on whether it was **included**.

=== "Python"
    ```python
    async with sdk:
        # Without include — unfetched stub
        article = await sdk.articles.get(1)
        # article.author is Resource(id=42) — only knows ID
        # article.author.username → AttributeError

        await article.author  # GET /articles/1/author
        print(article.author.username)  # "jdoe"

        # With include — fully populated
        article = await sdk.articles.get(1, "author")
        print(article.author.username)  # "jdoe", no extra HTTP call
    ```
=== "TypeScript"
    ```typescript
    // Without include — unfetched stub
    const article = await sdk.articles.get(1);
    // article.author is Resource — only knows id=42

    await article.author;  // GET /articles/1/author
    console.log(article.author.username);  // "jdoe"

    // With include — fully populated
    const article2 = await sdk.articles.get(1, "author");
    console.log(article2.author.username);  // "jdoe", no extra HTTP
    ```

### Plural relationships

Plural relationships return a `Collection` instead of a single resource.

=== "Python"
    ```python
    article = await sdk.articles.get(1)
    # article.categories → unfetched Collection

    await article.categories  # GET /articles/1/categories
    for category in article.categories:
        print(category.name)

    # With include — pre-populated
    article = await sdk.articles.get(1, "categories")
    for cat in article.categories:
        print(cat.name)
    ```
=== "TypeScript"
    ```typescript
    const article = await sdk.articles.get(1);
    // article.categories → unfetched Collection

    await article.categories.fetch();  // GET /articles/1/categories
    for (const cat of article.categories) {
        console.log(cat.name);
    }
    ```

### Mutating relationships

=== "Python"
    ```python
    await article.add("categories", cat1, cat2)
    # POST /articles/1/relationship/categories

    await article.remove("categories", cat1)
    # DELETE /articles/1/relationship/categories

    await article.reset("categories", cat1, cat2, cat3)
    # PATCH /articles/1/relationship/categories (replaces all)

    await article.edit("author", new_author)
    # PATCH /articles/1/relationship/author (singular replace)
    ```
=== "TypeScript"
    ```typescript
    await article.add("categories", cat1, cat2);
    // POST /articles/1/relationship/categories

    await article.remove("categories", cat1);
    // DELETE /articles/1/relationship/categories

    await article.reset("categories", cat1, cat2, cat3);
    // PATCH /articles/1/relationship/categories

    await article.edit("author", newAuthor);
    // PATCH /articles/1/relationship/author
    ```

After mutation, local relationship is invalidated. Next `await` fetches fresh:

=== "Python"
    ```python
    await article.add("categories", cat1)
    await article.categories  # GET /articles/1/categories
    ```
=== "TypeScript"
    ```typescript
    await article.add("categories", cat1);
    await article.categories.fetch();  // GET /articles/1/categories
    ```

Only operations with registered endpoints exist. Calling
`article.add("categories", ...)` without a matching server endpoint raises
`AttributeError` at class definition time.
