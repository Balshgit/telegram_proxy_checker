from typing import Annotated

from pydantic import Field, HttpUrl

SOURCE_NAME_MAX_LENGTH = 200
SOURCE_URL_MAX_LENGTH = 4000

SourceName = Annotated[str, Field(min_length=1, max_length=SOURCE_NAME_MAX_LENGTH)]
SourceUrl = Annotated[HttpUrl, Field(max_length=SOURCE_URL_MAX_LENGTH)]
