from enum import StrEnum


class DatabaseSchema(StrEnum):
    public = "public"


def get_public_shema() -> str:
    return DatabaseSchema.public
