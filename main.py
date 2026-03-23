"""
Thẩm Định KHTK — Backend Server
API key được giữ phía server, không lộ ra trình duyệt
"""
import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json

app = FastAPI(title="Thẩm Định KHTK")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# Phục vụ file tĩnh (frontend)
app.mount("/static", StaticFiles(directory="static"), name="static")


class AppraisalRequest(BaseModel):
    system: str
    user: str
    max_tokens: Optional[int] = 8000


@app.get("/", response_class=HTMLResponse)
async def root():
    """Phục vụ giao diện chính"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "status": "ok",
        "api_configured": bool(api_key and api_key.startswith("sk-")),
    }


@app.post("/api/appraise")
async def appraise(req: AppraisalRequest):
    """Proxy tới Claude API — API key bảo mật phía server"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY chưa được cấu hình trên server")

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": min(req.max_tokens, 8000),
        "system": req.system,
        "messages": [{"role": "user", "content": req.user}],
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            if resp.status_code != 200:
                detail = resp.json().get("error", {}).get("message", resp.text)
                raise HTTPException(resp.status_code, f"Claude API: {detail}")
            return resp.json()
        except httpx.TimeoutException:
            raise HTTPException(504, "Timeout — hồ sơ quá lớn, vui lòng thử lại")
        except httpx.RequestError as e:
            raise HTTPException(502, f"Lỗi kết nối: {str(e)}")
