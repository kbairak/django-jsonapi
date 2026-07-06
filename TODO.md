# TODO

- [ ] Built-in `JsonApi404Middleware`: override Django's HTML 404 with JSON:API response for `/api/`-prefixed paths. Detect prefix from registered URL patterns in `DjsonApi._registry` so user doesn't hardcode it.
