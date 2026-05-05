from pydantic import BaseModel, Field


class AiPromptItemOut(BaseModel):
    key: str
    content: str


class AiPromptListResponse(BaseModel):
    prompts: list[AiPromptItemOut]


class AiPromptPatchBody(BaseModel):
    content: str = Field(..., min_length=1, description="Full prompt text; use {context} where document excerpts go (suggested questions & TC generate).")


class AiPromptPatchResponse(BaseModel):
    key: str
    message: str


class AiPromptDeleteResponse(BaseModel):
    key: str
    message: str
