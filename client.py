"""
DoGrade client — ดึงผลการเรียนจากระบบ DoGrade (PhothaSoft/WeSchool, ASP.NET WebForms)
URL รูปแบบ: https://dograde.online/<school>/default.aspx

Flow จริง (ยืนยันด้วยบัญชีจริงแล้ว):
  1) GET  default.aspx                -> เก็บ __VIEWSTATE / __EVENTVALIDATION
  2) POST default.aspx (TxtUser, txtPassword=วันเกิด, ButtonX{n})
        - ถูกต้อง : เซิร์ฟเวอร์ Redirect ไป DooTermX.aspx + ตั้งคุกกี้ SSUser  -> หน้ามีตารางเกรด
        - ผิด     : กลับหน้าเดิม พร้อมสคริปต์ ShowFail1/2/3()
  3) เปลี่ยนภาคเรียน: POST DooTermX.aspx (ButtonX1..X6 / ButtonX7=ปพ.1) โดยใช้ viewstate ของหน้าเกรด
     (คุกกี้ SSUser เก็บ dg_id/dg_term ให้เอง)

ใช้กับบัญชีของตนเอง/ที่ได้รับอนุญาตเท่านั้น — password คือวันเกิด ถือเป็นข้อมูลส่วนบุคคล
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

TERM_BUTTON = {
    "1/1": "ButtonX1", "1/2": "ButtonX2",
    "2/1": "ButtonX3", "2/2": "ButtonX4",
    "3/1": "ButtonX5", "3/2": "ButtonX6",
}

FAIL = {
    "ShowFail1": ("no_db",         "ยังไม่เปิดฐานข้อมูลนักเรียนสำหรับดูเกรด"),
    "ShowFail2": ("bad_credential","รหัสผู้ใช้/วันเกิดไม่ถูกต้อง หรือไม่มีสิทธิ์ดูเกรด"),
    "ShowFail3": ("no_record",     "ไม่พบรายการข้อมูลของนักเรียน"),
}

COLS = ["code", "name", "type", "credit", "unit_score",
        "midterm", "final", "total", "grade", "retake",
        "attribute", "reading", "teacher"]


class DoGradeError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(f"{status}: {message}")
        self.status, self.message = status, message


@dataclass
class Subject:
    code: str = ""; name: str = ""; type: str = ""; credit: str = ""
    unit_score: str = ""; midterm: str = ""; final: str = ""; total: str = ""
    grade: str = ""; retake: str = ""; attribute: str = ""; reading: str = ""
    teacher: str = ""


@dataclass
class TermResult:
    student_id: str = ""
    name: str = ""
    room: str = ""
    ordinal: str = ""
    term_title: str = ""
    subjects: list[Subject] = field(default_factory=list)
    summary: dict[str, str] = field(default_factory=dict)   # gpa, credits ฯลฯ


def _hidden(html: str) -> dict:
    so = BeautifulSoup(html, "html.parser")
    out = {}
    for n in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        t = so.find("input", {"name": n})
        if t:
            out[n] = t.get("value", "")
    return out


def _fail_signal(html: str) -> Optional[tuple[str, str]]:
    tail = html[html.rfind("<![CDATA["):] if "<![CDATA[" in html else html[-2500:]
    for fn, res in FAIL.items():
        if fn + "();" in tail:
            return res
    return None


def parse_grades(html: str) -> TermResult:
    so = BeautifulSoup(html, "html.parser")
    res = TermResult()

    def val(name):
        t = so.find("input", {"name": name})
        return (t.get("value", "") if t else "").strip()

    res.student_id = val("fid")
    res.name = val("fName")
    res.room = val("fRoom")
    res.ordinal = val("fOrdinal")

    node = so.find(string=re.compile("ผลการเรียนชั้น"))
    if node:
        res.term_title = node.strip()

    grid = so.find(id="GridView0")
    if grid:
        for tr in grid.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) >= len(COLS):
                res.subjects.append(Subject(**dict(zip(COLS, cells[:len(COLS)]))))

    # ตารางสรุป (หน่วยกิต/GPA) — เป็นคู่ label:value
    for tbl in so.find_all("table"):
        if tbl.get("id") == "GridView0":
            continue
        for tr in tbl.find_all("tr"):
            tds = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(tds) == 2 and tds[0]:
                res.summary[tds[0]] = tds[1]
    return res


class DoGradeClient:
    def __init__(self, school: str = "yupparaj", session: requests.Session | None = None):
        self.root = f"https://dograde.online/{school}/"
        self.s = session or requests.Session()
        self.s.headers.update({"User-Agent": UA})

    def login(self, student_id: str, birthdate: str, term: str = "1/1") -> str:
        """เข้าสู่ระบบ + โหลดหน้าเกรดของภาคที่เลือก คืน HTML ของหน้าเกรด"""
        if term not in TERM_BUTTON:
            raise ValueError(f"term ต้องเป็นหนึ่งใน {list(TERM_BUTTON)}")
        login_url = self.root + "default.aspx"
        h0 = self.s.get(login_url, timeout=30).text
        data = {**_hidden(h0), "TxtUser": student_id, "txtPassword": birthdate,
                "TextSMS": "", TERM_BUTTON[term]: "x"}
        r = self.s.post(login_url, data=data, timeout=30)
        r.raise_for_status()
        fail = _fail_signal(r.text)
        if fail:
            raise DoGradeError(*fail)
        if "GridView0" not in r.text:
            raise DoGradeError("unknown", "ไม่พบตารางเกรดในผลลัพธ์ (flow อาจเปลี่ยน)")
        self._last = r.text
        return r.text

    def switch_term(self, term: str) -> str:
        """เปลี่ยนภาคเรียนหลังล็อกอินแล้ว (ใช้คุกกี้เดิม)"""
        url = self.root + "DooTermX.aspx"
        data = {**_hidden(self._last), TERM_BUTTON[term]: "x"}
        r = self.s.post(url, data=data, timeout=30)
        r.raise_for_status()
        if "GridView0" not in r.text:
            raise DoGradeError("no_record", "ไม่พบข้อมูลของภาคเรียนที่เลือก")
        self._last = r.text
        return r.text

    def get_term(self, student_id: str, birthdate: str, term: str = "1/1") -> TermResult:
        return parse_grades(self.login(student_id, birthdate, term))

    def get_all_terms(self, student_id: str, birthdate: str) -> dict[str, TermResult]:
        """ดึงทุกภาคที่มีข้อมูล โดยให้ error การล็อกอินส่งต่อถึงผู้เรียก

        ภาคเรียนที่ยังไม่มีผลการเรียนจะตอบ ``no_record`` ซึ่งไม่ใช่ความผิดพลาด
        ของการยืนยันตัวตน จึงข้ามภาคนั้นได้ แต่สถานะอื่น (โดยเฉพาะ
        ``bad_credential``) ต้องไม่ถูกกลืน มิฉะนั้น API จะตอบผลลัพธ์ว่าง
        แทน 401.
        """
        out: dict[str, TermResult] = {}
        logged_in = False
        for term in TERM_BUTTON:
            try:
                html = (
                    self.switch_term(term)
                    if logged_in
                    else self.login(student_id, birthdate, term)
                )
                logged_in = True
                r = parse_grades(html)
                if r.subjects:
                    out[term] = r
            except DoGradeError as exc:
                if exc.status == "no_record":
                    continue
                raise
        return out


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) < 3:
        sys.exit("usage: python client.py <student_id> <dd/mm/yyyy พ.ศ.> [term|all] [school]")
    term = sys.argv[3] if len(sys.argv) > 3 else "1/1"
    school = sys.argv[4] if len(sys.argv) > 4 else "yupparaj"
    c = DoGradeClient(school)
    if term == "all":
        data = {k: asdict(v) for k, v in c.get_all_terms(sys.argv[1], sys.argv[2]).items()}
    else:
        data = asdict(c.get_term(sys.argv[1], sys.argv[2], term))
    print(json.dumps(data, ensure_ascii=False, indent=2))
