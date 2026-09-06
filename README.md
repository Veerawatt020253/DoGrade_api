# DoGrade API

FastAPI wrapper for DoGrade. Use only with student data you are authorized to access.

## Run

Requires Python 3.11 or later.

```bash
python -m pip install -r requirements.txt
uvicorn app:app --reload --no-access-log
```

The default URL is `http://127.0.0.1:8000`. Configure deployment with these environment variables:

- `HOST` (default `127.0.0.1`)
- `PORT` (default `8000`)
- `ALLOWED_ORIGINS` (comma-separated CORS origins; default `*`)

For public deployments, terminate TLS/HTTPS at the application host or reverse proxy.

## Endpoints

```bash
# GET is convenient, but a URL can be recorded by proxies or access logs.
curl "http://localhost:8000/grades?student_id=YOUR_STUDENT_ID&birthdate=DD/MM/YYYY&term=1/1"

# Prefer POST so the birthdate (which serves as a password) is not in the URL.
curl -X POST http://localhost:8000/grades \
  -H "Content-Type: application/json" \
  -d '{"school":"yupparaj","student_id":"YOUR_STUDENT_ID","birthdate":"DD/MM/YYYY","term":"1/1"}'

curl "http://localhost:8000/grades/all?student_id=YOUR_STUDENT_ID&birthdate=DD/MM/YYYY"
curl http://localhost:8000/health
```

`term` accepts `1/1`, `1/2`, `2/1`, `2/2`, `3/1`, and `3/2`. Each API request creates a new scraper session; sessions and birthdates are never persisted or application-logged.

## Error responses

All application errors return this shape:

```json
{"status":"bad_credential","message":"รหัสผู้ใช้/วันเกิดไม่ถูกต้อง หรือไม่มีสิทธิ์ดูเกรด"}
```

DoGrade authentication failures are `401`; missing records are `404`; unavailable school databases are `503`; upstream failures are `502` or `504`; invalid input is `422`.
