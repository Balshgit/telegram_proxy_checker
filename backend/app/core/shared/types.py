from typing import Any


class MissingType:
    """To indicate that a value is not explicitly passed."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "Missing"

    def __deepcopy__(self, memo: dict[int, Any]) -> MissingType:
        """Prevents instantiating a new object when dataclasses.asdict() is called."""
        return self


Missing = MissingType()
