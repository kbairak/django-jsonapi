# Error Handling

## Exception hierarchy

=== "Python"

    ```
    DjsonApiClientError
    ├── BadRequest            (400)
    ├── Unauthorized          (401)
    ├── Forbidden             (403)
    ├── NotFound              (404)
    ├── MethodNotAllowed      (405)
    ├── Conflict              (409)
    ├── UnprocessableEntity   (422)
    ├── TooManyRequests       (429)
    ├── InternalServerError   (500)
    └── Http{N}               (any other status — dynamic class)
    ```

=== "TypeScript"

    ```
    DjsonApiClientError
    ├── BadRequest            (400)
    ├── Unauthorized          (401)
    ├── Forbidden             (403)
    ├── NotFound              (404)
    ├── MethodNotAllowed      (405)
    ├── Conflict              (409)
    ├── UnprocessableEntity   (422)
    ├── TooManyRequests       (429)
    ├── InternalServerError   (500)
    └── Http{N}               (any other status — dynamic class)
    ```

## Raising

=== "Python"

    ```python
    from articles_sdk.exceptions import NotFound

    try:
        article = await sdk.articles.get(999)
    except* NotFound as e:
        for error in e.exceptions:
            print(error.status)   # 404
            print(error.title)    # "Not Found"
            print(error.detail)   # server-provided detail message
    ```

=== "TypeScript"

    ```typescript
    import { NotFound } from "./articles_sdk_ts/index.js";

    try {
        const article = await sdk.articles.get(999);
    } catch (e) {
        if (e instanceof NotFound) {
            console.log(e.status);  // 404
            console.log(e.title);   // "Not Found"
            console.log(e.detail);  // server detail
        }
    }
    ```

## Error properties

Every error has:

| Property | Type             | Description      |
| -------- | ---------------- | ---------------- |
| `status` | `int` / `number` | HTTP status code |
| `title`  | `str` / `string` | Short title      |
| `detail` | `str` / `string` | Detailed message |

## Multiple errors

When the server returns multiple errors in one response — every error is raised
as an `ExceptionGroup`:

=== "Python"

    ```python
    try:
        article = await sdk.articles.create()
    except* BadRequest as e:
        for error in e.exceptions:
            print(error.detail)
    except* UnprocessableEntity as e:
        for error in e.exceptions:
            print(error.detail)
    ```

    Even a single error is wrapped in `ExceptionGroup`. Catch specific error
    types with `except*`.

=== "TypeScript"

    ```typescript
    try {
        await sdk.articles.create({});
    } catch (e) {
        if (e instanceof AggregateError) {
            for (const error of e.errors) {
                console.log(error.detail);
            }
        }
    }
    ```

    Multiple errors raise `AggregateError` containing individual error
    instances.

## Unknown status codes

Unrecognized HTTP status codes get a dynamic exception class:

=== "Python"

    ```python
    # Server returns 418
    from articles_sdk.exceptions import Http418
    ```

=== "TypeScript"

    ```typescript
    // Server returns 418 — class created dynamically
    // Class is Http418
    ```

## Response parsing errors

Errors during response parsing (malformed JSON, unexpected structure) raise the
base exception type:

=== "Python"

    ```python
    from djsonapi_client_py import DjsonApiClientError
    try:
        article = await sdk.articles.get(1)
    except DjsonApiClientError as e:
        print(e)
    ```

=== "TypeScript"

    ```typescript
    import { DjsonApiClientError } from "./articles_sdk_ts/index.js";
    try {
        const article = await sdk.articles.get(1);
    } catch (e) {
        if (e instanceof DjsonApiClientError) {
            console.log(e);
        }
    }
    ```
        }
    }
    ```
