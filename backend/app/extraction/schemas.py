"""Structured output contracts for the extraction models.

These pydantic models are passed to Gemini as `response_schema`, so the model is
forced to return exactly this JSON shape. Keep them flat and union-free: Gemini's
schema dialect does not support unions or free-form dict values.
"""

from typing import Literal

from pydantic import BaseModel, Field

QuestionKind = Literal["mcq_single", "mcq_multi", "numerical", "subjective"]
AnswerLocation = Literal["inline", "answer_key_at_end", "separate_solutions", "mixed", "none"]
PageKind = Literal["cover", "instructions", "questions", "answer_key", "solutions", "other"]


class SectionInfo(BaseModel):
    name: str = Field(description="Section heading exactly as printed, e.g. 'Physics' or 'Part B - Reasoning'.")
    subject: str | None = Field(None, description="Subject this section covers, if identifiable.")
    first_question: str | None = Field(None, description="Number of the first question in the section.")
    last_question: str | None = Field(None, description="Number of the last question in the section.")


class DocumentProfile(BaseModel):
    document_type: Literal["question_paper", "solutions", "answer_key", "mixed"] = Field(
        "question_paper",
        description="question_paper: questions (maybe with answers); solutions/answer_key: only answers/explanations.",
    )
    total_questions: int | None = Field(None, description="Number of questions the paper says it contains, if stated.")
    exam_name: str | None = None
    institution: str | None = None
    year: int | None = None
    languages: list[str] = Field(default_factory=list)
    layout: Literal["single_column", "two_column", "mixed"] = "single_column"
    numbering_style: str = Field("", description="How questions are numbered, e.g. 'Q.1', '1.', '(1)'.")
    numbering_restarts_per_section: bool = False
    option_style: str = Field("", description="How options are labelled, e.g. '(A)', 'a)', '1.'.")
    answer_location: AnswerLocation = "none"
    has_math: bool = False
    has_figures: bool = False
    sections: list[SectionInfo] = Field(default_factory=list)
    marks_correct: float | None = None
    marks_incorrect: float | None = Field(None, description="Negative marks as a negative number, e.g. -1.")
    duration_minutes: int | None = None
    notes: str = Field("", description="Anything unusual about the format that the extractor should know.")


class Box(BaseModel):
    """A figure location, in Gemini's native box convention."""

    page_offset: int = Field(description="0-based index of the image (page) in this request that holds the figure.")
    box_2d: list[int] = Field(description="[ymin, xmin, ymax, xmax] normalised to 0-1000.")
    caption: str | None = None


class ExtractedOption(BaseModel):
    label: str = Field(description="Normalised label: A, B, C, D... even if printed as (1), a), i.")
    text: str = Field(description="Option text, Markdown with LaTeX in $...$. Empty if the option is only a figure.")
    figure: Box | None = Field(None, description="Set when the option is (or contains) a figure.")


class ExtractedQuestion(BaseModel):
    number: str = Field(description="Question number as printed, without decoration: '12', not 'Q.12'.")
    section: str | None = Field(None, description="Section this question belongs to.")
    subject: str | None = None
    topic: str | None = Field(None, description="Best-guess syllabus topic, e.g. 'Rotational Mechanics'.")
    difficulty: Literal["easy", "medium", "hard"] | None = None
    question_type: QuestionKind = "mcq_single"
    year: int | None = Field(None, description="Exam year printed with this question, e.g. '[UPSC 2019]'. Never guess.")
    text: str = Field(description="Full question stem in Markdown; math in LaTeX ($...$ inline, $$...$$ block).")
    options: list[ExtractedOption] = Field(default_factory=list)
    answer: list[str] = Field(default_factory=list, description="Correct option labels, if printed in the PDF.")
    numerical_answer: str | None = Field(None, description="Answer for numerical questions, e.g. '4.5' or '2 to 3'.")
    explanation: str | None = Field(None, description="Solution/explanation if printed in the PDF.")
    figures: list[Box] = Field(default_factory=list, description="Figures/diagrams/tables-as-images in the stem.")
    page_offset: int = Field(0, description="0-based index of the image where the question starts.")
    continues_from_previous_page: bool = Field(
        False, description="True if this is the tail of a question that started before the first image."
    )
    confidence: float = Field(description="0-1: how sure you are that every field is transcribed exactly.")
    notes: str | None = Field(None, description="Any ambiguity: illegible text, unsure answer, odd layout.")


class AnswerKeyEntry(BaseModel):
    number: str = Field(description="Question number the entry belongs to, as printed.")
    section: str | None = None
    answer: list[str] = Field(default_factory=list, description="Correct option label(s) as printed, e.g. ['c'].")
    numerical_answer: str | None = None
    explanation: str | None = Field(None, description="Full explanation text, copied verbatim.")
    page_offset: int = Field(0, description="0-based index of the image where this entry starts.")


class SolutionsExtraction(BaseModel):
    entries: list[AnswerKeyEntry] = Field(default_factory=list)


class ChunkExtraction(BaseModel):
    page_kinds: list[PageKind] = Field(default_factory=list, description="One entry per primary page.")
    current_section_at_end: str | None = Field(None, description="Section heading in force at the end of the chunk.")
    questions: list[ExtractedQuestion] = Field(default_factory=list)
    answer_key: list[AnswerKeyEntry] = Field(
        default_factory=list, description="Entries from answer-key or solutions pages in this chunk."
    )
