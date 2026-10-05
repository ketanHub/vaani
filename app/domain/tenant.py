from pydantic import BaseModel, Field


class FAQ(BaseModel):
    id: str
    question: str
    answers: dict[str, str]
    aliases: list[str] = Field(default_factory=list)


class TenantProfile(BaseModel):
    id: str
    business_name: str
    default_language: str = "en"
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en", "hi", "hinglish"]
    )
    faqs: list[FAQ] = Field(default_factory=list)
