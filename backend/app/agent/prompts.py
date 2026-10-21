"""Versioned prompt definitions rendered and validated by LangChain."""

from pathlib import Path
from typing import Literal

import yaml
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, ConfigDict, Field

PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "system_prompt.yaml"


class PromptDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    template_format: Literal["f-string"] = "f-string"
    input_variables: list[str]
    template: str = Field(min_length=1)


def load_system_prompt(path=PROMPT_PATH) -> PromptTemplate:
    definition = PromptDefinition.model_validate(
        yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    )
    if definition.input_variables != ["max_steps"]:
        raise ValueError("System prompt must declare exactly the max_steps input variable")
    prompt = PromptTemplate(
        template=definition.template,
        template_format=definition.template_format,
        input_variables=definition.input_variables,
        validate_template=True,
        metadata={"prompt_name": definition.name, "prompt_version": definition.version},
    )
    if prompt.input_variables != definition.input_variables:
        raise ValueError("System prompt variables do not match the declared inputs")
    return prompt


SYSTEM_PROMPT = load_system_prompt()


def build_system_prompt(max_steps: int = 5) -> str:
    return SYSTEM_PROMPT.format(max_steps=max_steps)
