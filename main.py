"""
Thẩm Định KHTK — Backend v2
- Đọc PDF trực tiếp trên server (pdfplumber + PyMuPDF fallback)
- API key bảo mật hoàn toàn phía server
"""
import os, io, httpx, pdfplumber, fitz
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Thẩm Định KHTK v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

class AppraisalRequest(BaseModel):
    system: str
    user: str
    max_tokens: Optional[int] = 8000

def extract_pdf_text(data: bytes, filename: str = "") -> str:
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages[:30]):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(f"[Trang {i+1}]\n{t}")
                for tbl in (page.extract_tables() or []):
                    for row in tbl:
                        r = " | ".join(str(c or "").strip() for c in row if c)
                        if r.strip():
                            pages.append(r)
            text = "\n".join(pages)
    except Exception:
        pass
    if len(text.strip()) < 100:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            pages = []
            for i, page in enumerate(doc):
                if i >= 30: break
                t = page.get_text()
                if t.strip():
                    pages.append(f"[Trang {i+1}]\n{t}")
            text = "\n".join(pages)
        except Exception:
            pass
    return text[:8000] if text.strip() else f"(Không đọc được nội dung: {filename})"

async def call_claude(system: str, user: str, max_tokens: int = 8000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY chưa được cấu hình")
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": min(max_tokens, 8000),
                  "system": system, "messages": [{"role": "user", "content": user}]},
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, f"Claude API: {resp.json().get('error',{}).get('message', resp.text)}")
        return "".join(c.get("text","") for c in resp.json().get("content",[]))

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    key = os.environ.get("ANTHROPIC_API_KEY","")
    return {"status":"ok","version":"2.0","api_configured":bool(key)}

@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    data = await file.read()
    text = extract_pdf_text(data, file.filename or "")
    return {"filename": file.filename, "text": text, "chars": len(text)}

@app.post("/api/appraise")
async def appraise(req: AppraisalRequest):
    result = await call_claude(req.system, req.user, req.max_tokens or 8000)
    return {"content": [{"text": result}]}
