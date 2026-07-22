from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self, cast, overload
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from .resource import Resource

logger = logging.getLogger(__name__)


def _csv(value: Any) -> str:
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(v) for v in value)
    return str(value)


def translate_query(query: dict[str, Any]) -> dict[str, str]:
    """Translate dunder-style query kwargs into raw GET params.

    Mirrors the server's expectations (see ``djsonapi.api``):

    - ``title__contains`` -> ``filter[title][contains]``
    - ``page`` -> ``page``, ``page__number`` -> ``page[number]``
    - ``sort`` -> ``sort``
    - ``include__author`` -> ``include=author`` (CSV-merged, dots for nesting)
    - ``fields__articles`` -> ``fields[articles]``
    - ``extra__foo`` -> ``foo``
    - anything else -> passed through unchanged

    Falsy values are skipped; list/tuple/set values become CSV.
    """
    params: dict[str, str] = {}
    includes: list[str] = []
    for key, value in query.items():
        if value is None or value is False:
            continue
        if key.startswith("filter__"):
            parts = key[len("filter__") :].split("__")
            params["filter[" + "][".join(parts) + "]"] = _csv(value)
        elif key == "page":
            params["page"] = str(value)
        elif key.startswith("page__"):
            params[f"page[{key[len('page__') :]}]"] = str(value)
        elif key == "sort":
            params["sort"] = _csv(value)
        elif key.startswith("include__"):
            if value:
                includes.append(key[len("include__") :].replace("__", "."))
        elif key.startswith("fields__"):
            params[f"fields[{key[len('fields__') :]}]"] = _csv(value)
        elif key.startswith("extra__"):
            params[key[len("extra__") :]] = _csv(value)
        else:
            params[key] = _csv(value)
    if includes:
        params["include"] = ",".join(includes)
    return params


@dataclass
class Collection[T: "Resource"](Sequence):
    _sdk: Any = field(repr=False)
    _url: str = field(repr=False)
    _params: dict[str, str] = field(default_factory=dict, repr=False)
    _data: list[T] | None = None
    _links: dict[str, str] = field(default_factory=dict, repr=False)
    meta: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        parsed = urlparse(self._url)
        if parsed.query:
            self._url = parsed._replace(query="").geturl()
            url_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._params = {**url_params, **self._params}

    async def _fetch(self) -> Self:
        if self._data is not None:
            return self
        assert self._sdk._session is not None
        logger.debug("GET %s params=%s", self._url, self._params)
        async with self._sdk._session.get(self._url, params=self._params) as response:
            body = await response.json()
            logger.debug("Response %s: %s", response.status, body)
            self._sdk._raise_for_status(response.status, body)
            self._data = cast(list[T], self._sdk._parse_response(body))
            self._links = body.get("links", {})
            self.meta = body.get("meta", {})
        return self

    async def refetch(self) -> None:
        self._data = None
        await self._fetch()

    def __await__(self):
        return self._fetch().__await__()

    @overload
    def __getitem__(self, index: int) -> T: ...
    @overload
    def __getitem__(self, index: slice) -> list[T]: ...
    def __getitem__(self, index: int | slice) -> T | list[T]:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Use 'await collection' first.")
        return self._data[index]

    def __len__(self) -> int:
        if self._data is None:
            raise RuntimeError("Data not fetched yet. Use 'await collection' first.")
        return len(self._data)

    def filter(self, **kwargs: Any) -> Self:
        return self.__class__(
            self._sdk,
            self._url,
            {**self._params, **translate_query({f"filter__{k}": v for k, v in kwargs.items()})},
        )

    def include(self, *names: str) -> Self:
        return self.__class__(
            self._sdk,
            self._url,
            {**self._params, "include": ",".join(names)},
        )

    def fields(self, **fields: list[str]) -> Self:
        new_params = {f"fields[{resource}]": ",".join(attrs) for resource, attrs in fields.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def sort(self, *fields: str) -> Self:
        return self.__class__(self._sdk, self._url, {**self._params, "sort": ",".join(fields)})

    def page(self, _page: int | str | None = None, **params: str) -> Self:
        if _page is not None:
            new_params = {"page": str(_page)}
        else:
            new_params = {f"page[{key}]": value for key, value in params.items()}
        return self.__class__(self._sdk, self._url, {**self._params, **new_params})

    def extra(self, **params: str) -> Self:
        return self.__class__(self._sdk, self._url, {**self._params, **params})

    def has_next(self) -> bool:
        return "next" in self._links

    def get_next(self) -> Self:
        return self.__class__(self._sdk, self._links["next"], self._params)

    def has_previous(self) -> bool:
        return "previous" in self._links

    def get_previous(self) -> Self:
        return self.__class__(self._sdk, self._links["previous"], self._params)

    def has_first(self) -> bool:
        return "first" in self._links

    def get_first(self) -> Self:
        return self.__class__(self._sdk, self._links["first"], self._params)

    def has_last(self) -> bool:
        return "last" in self._links

    def get_last(self) -> Self:
        return self.__class__(self._sdk, self._links["last"], self._params)

    async def all_pages(self) -> AsyncIterator[Self]:
        current_page = await self._fetch()
        while True:
            yield current_page
            if current_page.has_next():
                current_page = await current_page.get_next()._fetch()
            else:
                break

    async def all(self) -> AsyncIterator[T]:
        async for page in self.all_pages():
            async for item in page:
                yield item

    async def __aiter__(self) -> AsyncIterator[T]:
        await self._fetch()
        assert self._data is not None
        for item in self._data:
            yield item
