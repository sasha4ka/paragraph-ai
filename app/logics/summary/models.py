from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.logics.summary.models import *


@dataclass
class SourceParagraph:
    title: str
    text: str
    paragraph_id: int | None = None


class PlanItem(BaseModel):
    id: int
    title: str
    question: str


class TextFact(BaseModel):
    type: Literal["text"]
    plan_item: int
    content: str
    source_fragment: str

    def __str__(self):
        return self.content


class ListFact(BaseModel):
    type: Literal["list"]
    plan_item: int
    title: str
    lines: list[str]
    is_numbered: bool
    source_fragment: str

    def __str__(self):
        def format_line(i: int, line: str):
            return f"{i}. {line}" if self.is_numbered else f"- {line}"

        return f"""\
{self.title}
{"\n".join([format_line(i + 1, line) for i, line in enumerate(self.lines)])}\
"""


class TableFact(BaseModel):
    type: Literal["table"]
    plan_item: int
    title: str
    lines: list[list[str]]
    source_fragment: str

    def __str__(self):
        result = ""
        for line in self.lines:
            result += "\t".join(line)
            result += "\n"
        return result[:-1]


Fact = Annotated[TextFact | ListFact | TableFact, Field(discriminator="type")]


class BakedBlock(BaseModel):
    plan_item: int
    text: str
