from pydantic import BaseModel, HttpUrl

class Feed(BaseModel):
    id: int | None = None
    name: str
    url: HttpUrl
    is_active: bool = True
    unread_count: int | None = None