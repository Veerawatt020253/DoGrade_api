"""FastAPI wrapper around the per-request DoGrade scraper client."""
from __future__ import annotations

import asyncio
import os
from typing import Annotated

import requests
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from client import DoGradeClient, DoGradeError
from models import ErrorOut, GradeRequest, TermOut

APP_TITLE = "DoGrade API"
DEFAULT_SCHOOL = "yupparaj"
ERROR_STATUS_CODES = {
    "bad_credential": 401,
    "no_record": 404,
    "no_db": 503,
    "unknown": 502,
}

origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app = FastAPI(title=APP_TITLE, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=origins != ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo the invalid input: it could contain a birthdate.
    return JSONResponse(
        status_code=422,
        content=ErrorOut(status="validation_error", message="รูปแบบพารามิเตอร์ไม่ถูกต้อง").model_dump(),
    )


def _error_response(status: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=ERROR_STATUS_CODES.get(status, 502),
        content=ErrorOut(status=status, message=message).model_dump(),
    )


async def _get_term(school: str, student_id: str, birthdate: str, term: str):
    try:
        # A client/session is deliberately created inside each request.
        result = await asyncio.to_thread(
            DoGradeClient(school=school).get_term, student_id, birthdate, term
        )
        return TermOut.from_result(result, term)
    except DoGradeError as exc:
        return _error_response(exc.status, exc.message)
    except (requests.Timeout, requests.ConnectionError):
        return _error_response("upstream_timeout", "ไม่สามารถเชื่อมต่อระบบ DoGrade ได้ภายในเวลาที่กำหนด")
    except requests.RequestException:
        return _error_response("upstream_error", "ระบบ DoGrade ตอบกลับผิดปกติ")
    except Exception:
        # Avoid logging request fields: birthdate is a password/PII.
        return _error_response("unknown", "เกิดข้อผิดพลาดขณะดึงผลการเรียน")


async def _get_all_terms(school: str, student_id: str, birthdate: str):
    try:
        results = await asyncio.to_thread(
            DoGradeClient(school=school).get_all_terms, student_id, birthdate
        )
        return {term: TermOut.from_result(result, term) for term, result in results.items()}
    except DoGradeError as exc:
        return _error_response(exc.status, exc.message)
    except (requests.Timeout, requests.ConnectionError):
        return _error_response("upstream_timeout", "ไม่สามารถเชื่อมต่อระบบ DoGrade ได้ภายในเวลาที่กำหนด")
    except requests.RequestException:
        return _error_response("upstream_error", "ระบบ DoGrade ตอบกลับผิดปกติ")
    except Exception:
        return _error_response("unknown", "เกิดข้อผิดพลาดขณะดึงผลการเรียน")


School = Annotated[str, Query(pattern=r"^[a-z0-9-]+$", max_length=80)]
StudentId = Annotated[str, Query(pattern=r"^(?:\d{5}|\d{13})$")]
Birthdate = Annotated[str, Query(pattern=r"^\d{2}/\d{2}/\d{4}$")]
Term = Annotated[str, Query(pattern=r"^(?:1/1|1/2|2/1|2/2|3/1|3/2)$")]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/grades", response_model=TermOut, responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 422: {"model": ErrorOut}, 502: {"model": ErrorOut}, 503: {"model": ErrorOut}, 504: {"model": ErrorOut}})
async def grades(student_id: StudentId, birthdate: Birthdate, school: School = DEFAULT_SCHOOL, term: Term = "1/1"):
    return await _get_term(school, student_id, birthdate, term)


@app.post("/grades", response_model=TermOut, responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 422: {"model": ErrorOut}, 502: {"model": ErrorOut}, 503: {"model": ErrorOut}, 504: {"model": ErrorOut}})
async def grades_post(payload: GradeRequest):
    return await _get_term(payload.school, payload.student_id, payload.birthdate, payload.term)


@app.get("/grades/all", response_model=dict[str, TermOut], responses={401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 422: {"model": ErrorOut}, 502: {"model": ErrorOut}, 503: {"model": ErrorOut}, 504: {"model": ErrorOut}})
async def grades_all(student_id: StudentId, birthdate: Birthdate, school: School = DEFAULT_SCHOOL):
    return await _get_all_terms(school, student_id, birthdate)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "").lower() in {"1", "true", "yes"},
        # GET endpoints can carry a birthdate, so do not let Uvicorn log URLs.
        access_log=False,
    )
