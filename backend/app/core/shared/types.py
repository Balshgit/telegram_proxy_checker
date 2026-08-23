import re
from datetime import timedelta
from typing import Annotated, Any

from pydantic import BeforeValidator

_SECONDS_RE = re.compile(r"-?\d+(\.\d+)?")


def _seconds_to_timedelta(value: Any) -> Any:
    """Разрешает задавать интервал числом секунд, в том числе строкой из `.env` (например, "3600")."""
    if isinstance(value, str) and _SECONDS_RE.fullmatch(value.strip()):
        return float(value)
    return value


# Интервал, который можно указать как число секунд ("3600"), так и в ISO 8601 ("PT1H").
IntervalSeconds = Annotated[timedelta, BeforeValidator(_seconds_to_timedelta)]


class MissingType:
    """To indicate that a value is not explicitly passed."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Missing"

    def __deepcopy__(self, memo: dict[int, Any]) -> MissingType:
        """Prevents instantiating a new object when dataclasses.asdict() is called."""
        return self


Missing = MissingType()
