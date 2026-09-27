from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class SourceParagraph:
    title: str
    text: str
    paragraph_id: int | None = None


class InformationObject(BaseModel):
    type: str
    content: str


class ParagraphSummary(BaseModel):
    summary: str
    key_points: list[str]


class ParagraphResult(BaseModel):
    summary: ParagraphSummary
    info_objects: list[InformationObject]


class SynthesisResult(BaseModel):
    summary_block: str
    information_block: str
