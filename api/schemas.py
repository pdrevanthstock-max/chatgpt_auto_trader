from pydantic import BaseModel, Field


class IndexSelectionUpdate(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    expected_version: int = Field(ge=0)


class IndexSelectionView(BaseModel):
    symbols: list[str]
    version: int
    is_all: bool
    pause_new_entries: bool


class DiagnosticStartRequest(BaseModel):
    top_count: int = Field(default=5)


class PaperCapitalTargetRequest(BaseModel):
    target_equity: float = Field(ge=0)
    note: str = Field(min_length=1, max_length=200)
