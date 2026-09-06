import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app
from client import DoGradeClient, DoGradeError, Subject, TermResult
from models import TermOut


def sample_result() -> TermResult:
    return TermResult(
        student_id="12345",
        name="Test Student",
        room="1",
        ordinal="2",
        term_title="ผลการเรียนชั้นมัธยมศึกษาปีที่ 4 ภาคเรียนที่ 1",
        subjects=[Subject(code="ท31101", name="ภาษาไทย 1", type="1", credit="1.0", midterm="0", final="11", total="67", grade="2.5")],
        summary={"ผลการเรียนเฉลี่ย GPA": "3.38", "รวมจำนวนหน่วยกิตที่เรียน": "18.0", "รวมจำนวนหน่วยกิตที่ได้": "17.0"},
    )


class SuccessClient:
    def __init__(self, school: str):
        self.school = school

    def get_term(self, student_id: str, birthdate: str, term: str):
        return sample_result()

    def get_all_terms(self, student_id: str, birthdate: str):
        return {"1/1": sample_result()}


class BadCredentialClient(SuccessClient):
    def get_term(self, *args):
        raise DoGradeError("bad_credential", "credentials rejected")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)

    def test_health(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    @patch("app.DoGradeClient", SuccessClient)
    def test_grades_converts_result(self):
        response = self.client.get("/grades?student_id=12345&birthdate=01/01/2550&term=1/1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["subjects"][0]["type_label"], "พื้นฐาน")
        self.assertEqual(payload["subjects"][0]["midterm"], 0.0)
        self.assertEqual(payload["gpa"], 3.38)
        self.assertEqual(payload["credits_earned"], 17.0)

    @patch("app.DoGradeClient", SuccessClient)
    def test_all_returns_available_terms_only(self):
        response = self.client.get("/grades/all?student_id=12345&birthdate=01/01/2550")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.json()), ["1/1"])

    @patch("app.DoGradeClient", BadCredentialClient)
    def test_upstream_credential_error_is_401(self):
        response = self.client.get("/grades?student_id=12345&birthdate=01/01/2550")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "bad_credential")

    def test_invalid_parameters_are_422_without_echoing_input(self):
        response = self.client.get("/grades?student_id=abc&birthdate=2550-01-01")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["status"], "validation_error")
        self.assertNotIn("2550-01-01", response.text)

    def test_term_model_empty_grade_is_null(self):
        result = sample_result()
        result.subjects[0].grade = ""
        self.assertIsNone(TermOut.from_result(result, "1/1").subjects[0].grade)

    def test_all_terms_does_not_hide_bad_credentials(self):
        scraper = DoGradeClient(school="yupparaj")

        def fail_login(*args):
            raise DoGradeError("bad_credential", "credentials rejected")

        scraper.login = fail_login
        with self.assertRaisesRegex(DoGradeError, "bad_credential"):
            scraper.get_all_terms("12345", "01/01/2550")


if __name__ == "__main__":
    unittest.main()
