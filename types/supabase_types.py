from pydantic import BaseModel
from typing import List, Optional

class ImagesRow(BaseModel):
    id: str
    storage_path: str
    created_at: Optional[str] = None

class CommentsRow(BaseModel):
    email_id: str
    image_id: str
    body: str
    created_at: Optional[str] = None