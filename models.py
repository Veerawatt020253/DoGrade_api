"""Pydantic models used by the public DoGrade API."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from client import Subject, TermResult


def _number(value: str | int | float | None) -> float | None:
    """Return a JSON number when DoGrade supplies one; blanks become null."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "–"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _summary_number(summary: dict[str, str], label: str) -> float | None:
    """Find a summary value despite harmless colon/whitespace differences."""
    expected = label.rstrip(":").strip()
    for key, value in summary.items():
        if key.rstrip(":").strip() == expected:
            return _number(value)
    return None


class SubjectOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    type: int
    # Some schools include activity rows with a type outside the documented 1/2.
    # Preserve the numeric value and leave the friendly label absent for those rows.
    type_label: str | None
    credit: float | None
    unit_score: float | None
    midterm: float | None
    final: float | None
    total: float | None
    grade: str | None
    retake: str | None
    attribute: str | None
    reading: str | None
    teacher: str | None

    @classmethod
    def from_subject(cls, subject: Subject) -> "SubjectOut":
        subject_type = _number(subject.type)
        if subject_type is None:
            raise ValueError("DoGrade ส่งประเภทวิชาที่ไม่ถูกต้อง")
        type_int = int(subject_type)
        return cls(
            code=subject.code,
            name=subject.name,
            type=type_int,
            type_label={1: "พื้นฐาน", 2: "เพิ่มเติม"}.get(type_int),
            credit=_number(subject.credit),
            unit_score=_number(subject.unit_score),
            midterm=_number(subject.midterm),
            final=_number(subject.final),
            total=_number(subject.total),
            grade=subject.grade.strip() or None,
            retake=subject.retake.strip() or None,
            attribute=subject.attribute.strip() or None,
            reading=subject.reading.strip() or None,
            teacher=subject.teacher.strip() or None,
        )


class TermOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: str
    name: str
    room: str
    ordinal: str
    term: str
    term_title: str
    subjects: list[SubjectOut]
    gpa: float | None
    credits_earned: float | None
    credits_total: float | None
    summary_raw: dict[str, str]

    @classmethod
    def from_result(cls, result: TermResult, term: str) -> "TermOut":
        return cls(
            student_id=result.student_id,
            name=result.name,
            room=result.room,
            ordinal=result.ordinal,
            term=term,
            term_title=result.term_title,
            subjects=[SubjectOut.from_subject(subject) for subject in result.subjects],
            gpa=_summary_number(result.summary, "ผลการเรียนเฉลี่ย GPA"),
            credits_earned=_summary_number(result.summary, "รวมจำนวนหน่วยกิตที่ได้"),
            credits_total=_summary_number(result.summary, "รวมจำนวนหน่วยกิตที่เรียน"),
            summary_raw=dict(result.summary),
        )


class ErrorOut(BaseModel):
    status: str
    message: str


class GradeRequest(BaseModel):
    """POST body variant, which avoids putting the birthdate in a URL."""

    school: str = Field(default="yupparaj", pattern=r"^[a-z0-9-]+$", max_length=80)
    student_id: str = Field(pattern=r"^(?:\d{5}|\d{13})$")
    birthdate: str = Field(pattern=r"^\d{2}/\d{2}/\d{4}$")
    term: str = Field(default="1/1", pattern=r"^(?:1/1|1/2|2/1|2/2|3/1|3/2)$")
