"""The model can select categories, never filesystem paths."""
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class Category(str, Enum):
    EDUCATION = "Education"
    CAREER = "Career"
    FINANCE = "Finance"
    LEGAL = "Legal"
    OTHER = "Other"


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Category
    reason: str = Field(min_length=1, max_length=400)
