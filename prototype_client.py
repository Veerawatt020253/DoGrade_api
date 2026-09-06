"""
Prototype: ดึงผลการเรียนจาก DoGrade (dograde.online) — ASP.NET WebForms
ยืนยันแล้วว่า:
  - ไม่มี session cookie เลย  -> state อยู่ใน __VIEWSTATE ล้วน ๆ
  - ทุกอย่างโพสต์กลับไปที่ default.aspx เดิม
  - ผลลัพธ์แจ้งผ่าน JS ที่ inject ท้ายหน้า: ShowFail1/2/3() หรือ ShowConfirmSave()

ใช้กับบัญชีของตัวเอง/ที่ได้รับอนุญาตเท่านั้น
"""
import re
import requests
from bs4 import BeautifulSoup

BASE = "https://dograde.online/yupparaj/default.aspx"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# ปุ่มเลือกปี/ภาคเรียน (name ของ submit button)
TERMS = {
    "1/1": "ButtonX1", "1/2": "ButtonX2",
    "2/1": "ButtonX3", "2/2": "ButtonX4",
    "3/1": "ButtonX5", "3/2": "ButtonX6",
    "pp1": "ButtonX7",   # ปพ.1
    "info": "ButtonX8",
}

RESULT_SIGNALS = {
    "ShowConfirmSave": ("ok", "ตรวจสอบสิทธิ์ผ่าน รอยืนยันไปต่อ"),
    "ShowFail1": ("no_db", "ยังไม่เปิดฐานข้อมูลนักเรียนสำหรับดูเกรด"),
    "ShowFail2": ("bad_credential", "รหัสผู้ใช้/วันเกิดไม่ถูกต้อง หรือไม่มีสิทธิ์"),
    "ShowFail3": ("no_record", "ไม่พบรายการข้อมูลของนักเรียน"),
}


def _state(html: str) -> dict:
    """ดึง hidden field ของ WebForms ออกมาเพื่อใช้โพสต์รอบถัดไป"""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        tag = soup.find("input", {"name": name})
        if tag:
            out[name] = tag.get("value", "")
    return out


def _signal(html: str):
    """อ่านผลลัพธ์จากสคริปต์ที่เซิร์ฟเวอร์ inject กลับมาท้ายหน้า (บล็อก CDATA สุดท้าย)"""
    marker = "<![CDATA["
    tail = html[html.rfind(marker):] if marker in html else html[-2000:]
    for fn, res in RESULT_SIGNALS.items():
        if fn + "();" in tail:
            return res
    return (None, None)


class DoGradeClient:
    def __init__(self, base: str = BASE):
        self.base = base
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Referer": base})

    def _post(self, state: dict, **fields) -> str:
        data = {**state, "TxtUser": "", "txtPassword": "", "TextSMS": "", **fields}
        r = self.s.post(self.base, data=data, timeout=30)
        r.raise_for_status()
        return r.text

    def fetch(self, student_id: str, birthdate: str, term: str = "1/1") -> dict:
        """
        student_id : เลขประจำตัวนักเรียน 5 หลัก หรือเลขบัตรประชาชน 13 หลัก
        birthdate  : 'วว/ดด/ปปปป' พ.ศ. เช่น '31/12/2550'
        term       : key ใน TERMS
        """
        html = self.s.get(self.base, timeout=30).text

        # รอบที่ 1: ส่งรหัส + เลือกภาคเรียน
        html = self._post(
            _state(html),
            TxtUser=student_id,
            txtPassword=birthdate,
            **{TERMS[term]: "x"},
        )
        status, msg = _signal(html)
        if status != "ok":
            return {"ok": False, "status": status or "unknown", "message": msg, "html": html}

        # รอบที่ 2: กด "ยืนยันไปต่อ" (Button7) พร้อม viewstate ใหม่
        html = self._post(_state(html), Button7="ยืนยันไปต่อ")
        return {"ok": True, "status": "ok", "grades": parse_grades(html), "html": html}


def parse_grades(html: str) -> list:
    """
    แปลงตารางผลการเรียนเป็น list ของ dict
    NOTE: ต้องมีบัญชีจริงหนึ่งชุดเพื่อ map ชื่อคอลัมน์ให้ตรง — ตอนนี้คืน raw rows ไปก่อน
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = []
    for tbl in soup.find_all("table"):
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                for tr in tbl.find_all("tr")]
        rows = [r for r in rows if any(r)]
        if len(rows) > 1:
            tables.append(rows)
    return tables


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) < 3:
        sys.exit("usage: python prototype_client.py <student_id> <dd/mm/yyyy พ.ศ.> [term]")
    c = DoGradeClient()
    res = c.fetch(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1/1")
    res.pop("html", None)
    print(json.dumps(res, ensure_ascii=False, indent=2))
