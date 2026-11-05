from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from schemas.auth import _check_password_rules


class AdminSignUp(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str | None = Field(default=None, max_length=30)
    password: str = Field(max_length=128)
    invite_code: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _first_and_last_name(cls, value: str) -> str:
        parts = value.split()
        if len(parts) < 2:
            raise ValueError("Enter your first and last name.")
        return " ".join(parts)

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        return _check_password_rules(value)