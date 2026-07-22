# Setup & Usage

## Quick start

Copy the generated package into your project tree. Python SDK needs `aiohttp`
installed; TypeScript SDK has zero dependencies.

=== "Python"

    ```python
    from articles_sdk import sdk

    sdk.setup(
        host="https://api.example.com/",
        headers=lambda: {"Authorization": "Bearer " + token},
    )

    async with sdk:
        article = await sdk.articles.get(1)
        print(article.title)

        article = await sdk.articles.get(1)
    ```

    `async with sdk:` creates and closes an `aiohttp.ClientSession`. The host
    defaults to `http://localhost:8000/`. Configure before making requests:

=== "TypeScript"

    ```typescript
    import { sdk } from "./articles_sdk_ts/index.js";

    sdk.setup({
        host: "http://localhost:8000/api/",
        headers: async () => ({
            Authorization: "Bearer " + token,
        }),
    });

    const article = await sdk.articles.get(1);
    console.log(article.title);
    ```

## Global singleton vs instance

Both Python and TypeScript generated SDKs export a pre-instantiated `sdk`
object. This is convenient for simple apps where all requests use the same host
and auth.

However, a single global config is unsafe when your code makes requests on
behalf of different users — a background task in an OAuth application, for
instance. In that case, create separate instances:

=== "Python"

    ```python
    from articles_sdk import SDK

    admin_sdk = SDK(host="...", headers=lambda: {"Authorization": "Bearer " + admin_token})

    user_sdk = SDK(host="...", headers=lambda: {"Authorization": "Bearer " + user_token})
    ```

=== "TypeScript"

    ```typescript
    import { SDK } from "./articles_sdk_ts/index.js";

    const adminSdk = new SDK({ host: "...", headers: async () => ({ Authorization: "Bearer " + adminToken }) });

    const userSdk = new SDK({ host: "...", headers: async () => ({ Authorization: "Bearer " + userToken }) });
    ```

## SDK lifecycle

=== "Python"

    1. `SDK()` — create instance (no network)
    2. `sdk.setup(host=..., headers=...)` — optional, any time before requests
    3. `async with sdk:` — opens session, closes on exit
    4. Inside context: make requests

    Reuse the same SDK instance across requests. Sessions are cheap.

=== "TypeScript"

    1. `new SDK()` or use exported `sdk` — create instance (no network)
    2. `sdk.setup({host, headers})` — configure host and auth
    3. Start making requests immediately

    No explicit session. Each request calls `fetch()` with configured headers.

## Resource access

=== "Python"

    ```python
    async with sdk:
        user = await sdk.users.get(1)
    ```

=== "TypeScript"

    ```typescript
    const user = await sdk.users.get(1);
    ```

Unknown resource types raise error:

=== "Python"

    ```python
    sdk.unknown  # AttributeError
    ```

=== "TypeScript"

    ```typescript
    (sdk as any).unknown  // TypeError
    ```

## Debug logging

Enable logging to see every HTTP request and response:

=== "Python"

    ```python
    import logging
    logging.basicConfig(level=logging.DEBUG)
    ```

    The Python SDK uses standard `logging.getLogger(__name__)` throughout. Set
    level to `DEBUG` to see method, URL, params, status, and response body for
    every request.

=== "TypeScript"

    ```typescript
    sdk.debug = true
    ```

    Prints `[djsonapi] METHOD url`, `[djsonapi] response STATUS body` to the
    console for every HTTP call.
