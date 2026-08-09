from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


class Base:
    @classmethod
    def get_real_column_name(cls, attr_name: str) -> str:
        insp = inspect(cls)
        if insp is None or not hasattr(insp, "c"):
            raise ValueError(f"Cannot inspect class {cls.__name__} or has no columns")
        return getattr(insp.c, attr_name).name

    def __str__(self) -> str:
        return self.__repr__()

    def __repr__(self) -> str:
        try:
            return f"{self.__class__.__name__}(id={self.id})"  # type: ignore[attr-defined]
        except AttributeError:
            return super().__repr__()


class DBBase(Base, DeclarativeBase): ...
