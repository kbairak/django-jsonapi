from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


@dataclass
class Collection(Sequence):
    _sdk: Any = field(repr=False)
    _url: str = field(repr=False)
    _params: dict[str, str] = field(default_factory=dict, repr=False)
    _data: list[Any] | None = None
    _links: dict[str, str] = field(default_factory=dict, repr=False)
    meta: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        parsed = urlparse(self._url)
        if parsed.query:
            self._url = parsed._replace(query="").geturl()
            url_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._params = {**url_params, **self._params}

    async def fetch(self, force=False):
        if self._data is not None and not force:
            return
        assert self._sdk._session is not None
        logger.debug("GET %s params=%s", self._url, self._params)
        async with self._sdk._session.get(self._url, params=self._params) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            self._sdk._raise_for_status(response.status, body)
            self._data = cast(list, self._sdk._parse_response(body))
            self._links = body.get("links", {})
            self.meta = body.get("meta", {})

    def __getitem__(self, index: int) -> Any:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Call 'await collection.fetch()' first.")
        return self._data[index]

    def __len__(self) -> int:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Call 'await collection.fetch()' first.")
        return len(self._data)

    def filter(self, **kwargs: str) -> Collection:
        return self.__class__(self._sdk, self._url, {**self._params, **kwargs})

    def include(self, *names: str) -> Collection:
        return self.__class__(
            self._sdk,
            self._url,
            {**self._params, "include": ",".join(names)},
        )

    def fields(self, **fields: list[str]) -> Collection:
        new_params = {f"fields[{resource}]": ",".join(attrs) for resource, attrs in fields.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def sort(self, *fields: str) -> Collection:
        return self.__class__(self._sdk, self._url, {**self._params, "sort": ",".join(fields)})

    def page(self, _page: int | str | None = None, **params: str):
        if _page is not None:
            new_params = {"page": str(_page)}
        else:
            new_params = {f"page[{key}]": value for key, value in params.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def extra(self, **params: str):
        return self.__class__(self._sdk, self._url, {**self._params, **params})

    def has_next(self) -> bool:
        return "next" in self._links

    def get_next(self) -> Collection:
        return self.__class__(self._sdk, self._links["next"], self._params)

    def has_previous(self) -> bool:
        return "previous" in self._links

    def get_previous(self) -> Collection:
        return self.__class__(self._sdk, self._links["previous"], self._params)

    def has_first(self) -> bool:
        return "first" in self._links

    def get_first(self) -> Collection:
        return self.__class__(self._sdk, self._links["first"], self._params)

    def has_last(self) -> bool:
        return "last" in self._links

    def get_last(self) -> Collection:
        return self.__class__(self._sdk, self._links["last"], self._params)

    async def all_pages(self) -> AsyncIterator[Collection]:
        current_page = self
        while True:
            yield current_page
            if current_page.has_next():
                current_page = current_page.get_next()
            else:
                break

    async def all(self) -> AsyncIterator[Any]:
        async for page in self.all_pages():
            async for item in page:
                yield item

    async def __aiter__(self) -> AsyncIterator[Any]:
        await self.fetch()
        assert self._data is not None
        for item in self._data:
            yield item
