from pydantic import BaseModel, Field


class QuickRecipient(BaseModel):
    bank: str = Field(min_length=1, max_length=100)
    account: str = Field(pattern=r"^\d{6,20}$")
    recipient: str = Field(min_length=1, max_length=150)
    nickname: str = Field(default="", max_length=150)


class RecipientContext(BaseModel):
    quick_recipients: list[QuickRecipient] = Field(default_factory=list, max_length=200)
