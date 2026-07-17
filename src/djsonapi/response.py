from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from django.http import HttpRequest

from .resource import Resource


@dataclass
class Response[T]:
    data: T | None = None
    included: Sequence[Resource] | None = None
    links: dict[str, dict[str, str | int]] | None = None
    meta: dict | None = None
    status: int = 200

    def serialize(self, request: HttpRequest) -> dict[str, Any]:
        result: dict[str, Any] = {"links": {"self": request.get_full_path()}}
        if self.data is None:
            result["data"] = None
        elif isinstance(self.data, Sequence):
            result["data"] = [item.serialize() for item in self.data]
        elif isinstance(self.data, Resource):
            result["data"] = self.data.serialize()
        else:
            raise ValueError("Cannot serialize response")
        if self.included:
            result["included"] = [item.serialize() for item in self.included]
        if self.meta:
            result["meta"] = self.meta
        for key, value in (self.links or {}).items():
            parameters = {**request.GET.dict(), **value}
            result.setdefault("links", {})[key] = f"{request.path}?{urlencode(parameters)}"
        return result
