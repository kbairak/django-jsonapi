# SDK Generation

## Command

```bash
./manage.py generate_jsonapi_client <module::attr> --output <dir> [--language python|typescript]
```

- `<module::attr>` — Python import path to your `DjsonApi` instance (e.g.,
  `articles.views::api`)
- `--output` — output directory for the generated SDK package
- `--language` — `python` (default) or `typescript`

### Requirements

- `djsonapi` must be in `INSTALLED_APPS`
- Run from your Django project directory

### Examples

=== "Python"

    ```bash
    ./manage.py generate_jsonapi_client articles.views::api --output ~/articles_sdk
    ```

=== "TypeScript"

    ```bash
    ./manage.py generate_jsonapi_client articles.views::api \
        --output ~/articles_sdk_ts --language typescript
    ```

## Output structure

=== "Python"

    ```
    articles_sdk/
    ├── __init__.py          # Re-exports SDK + resources
    ├── sdk.py               # SDK subclass with sealed types
    ├── resources.py         # Per-resource typed classes
    └── _runtime/            # Copied verbatim from djsonapi_client_py
        ├── __init__.py
        ├── sdk.py
        ├── resource.py
        ├── collection.py
        ├── exceptions.py
        └── ...
    ```

=== "TypeScript"

    ```
    articles_sdk_ts/
    ├── index.ts             # Public exports
    ├── sdk.ts               # SDK subclass
    ├── resources.ts         # Per-resource typed classes
    └── _runtime/            # Copied verbatim from djsonapi_client_ts
        ├── index.ts
        ├── sdk.ts
        ├── resource.ts
        ├── collection.ts
        ├── exceptions.ts
        └── ...
    ```

## What's generated

For each resource type in your API, the generator produces:

- **Typed class** with attribute annotations, relationship types, and
  capabilities baked in
- **CRUD methods** — only those with registered endpoints
- **Query methods** — typed filter/sort/page based on handler parameters
- **Relationship methods** — `add`/`remove`/`reset`/`edit` only when the
  corresponding endpoints exist
- **Type conversions** — annotated types drive runtime conversion (JSON string →
  Python `datetime`, etc.)

## Capability gating

The generated SDK reflects exactly what your server supports:

- No `delete()` if you didn't register `@api.delete_one`
- No `create()` if you didn't register `@api.create_one`
- No relationship mutations if the endpoints don't exist
- `sdk.unknown_type` → `AttributeError` (instead of making up URLs)

This is enforced at the **class level** — capabilities are `frozenset` members,
checked at import time in Python and at class definition in TypeScript.
