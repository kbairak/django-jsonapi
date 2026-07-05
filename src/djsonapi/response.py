from collections.abc import Sequence
from dataclasses import dataclass, field

from .resource import Resource


@dataclass
class Response[T]:
    data: T | None = None
    included: Sequence[Resource] | None = None

