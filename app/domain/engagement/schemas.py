from pydantic import BaseModel


class ViewCountResponse(BaseModel):
    view_count: int
