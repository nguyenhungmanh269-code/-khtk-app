"""
Thẩm Định KHTK — Backend v3.1
- PDF điện tử: pdfplumber
- PDF scan (ảnh): gọi Claude Vision để đọc từng trang
- Bảng trạng thái file rõ ràng
- Kiến trúc 2 bước: extract → appraise
"""
import os, io, base64, httpx, pdfplumber
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Thẩm Định KHTK v3.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

# ══════════════════════════════════════════════════════════════════
# MẪU CHUẨN — Trích từ Báo cáo CPXD Cầu Châu Phong FINAL
# ══════════════════════════════════════════════════════════════════
MAU_BAO_CAO = """
=== VÍ DỤ MẪU BÁO CÁO ĐẠT CHUẨN (CPXD Cầu Châu Phong — trích tiêu biểu) ===

CÁCH VIẾT PHẦN I — PHẠM VI & NGUYÊN TẮC:
1. Phiếu trình không lặp lại nội dung hồ sơ chi tiết đính kèm.
2. Tập trung vào vấn đề trọng yếu: tính hợp lệ–logic–khả thi; điểm bất thường; rủi ro then chốt; kiến nghị.
3. Kết luận thể hiện rõ: (i) đạt/không đạt điều kiện trình; (ii) điều kiện bắt buộc hoàn thiện trước triển khai.

CÁCH VIẾT PHẦN II — THÔNG TIN HỢP ĐỒNG (cụ thể từng đồng):
"- GT HĐXD phần Công ty CP Tây An: 18.427.982.000đ; đã tạm ứng 5.528.000.000đ (tối đa 30% GT HĐ). Tiến độ HĐ: 720 ngày.
- Thu hồi TU qua các lần TT, mỗi lần tối thiểu 1% GTKL nghiệm thu; thu hồi hết khi giải ngân đạt 80% GT HĐ. Điều kiện TT khi lũy kế NT đạt 5% GT HĐ. Tạm giữ 7% (2% QT + 5% BH).
- Nguồn vốn ĐTC; vốn giao 2026 phần Công ty: 12,902 tỷ; vốn phải lập KH: 18,43 tỷ."

CÁCH VIẾT BẢNG 1 — hình thức, ghi rõ file gốc + mức ảnh hưởng:
Hồ sơ HĐ–NV: "1. HĐ 238...pdf"; "1.2 Nguồn vốn...pdf" | Đủ 2/2 | Chữ ký đủ; ngày đủ; BM phù hợp | Rất cao – căn cứ chốt GT HĐ, TU, TT, nguồn vốn | Giữ làm căn cứ pháp lý chính.
Hồ sơ CDTC: "2.5 CDTC.pdf" | Có đầu mục; chưa đủ chi tiết | HDTC đang lập chưa đúng ĐMNB | Rất cao – ảnh hưởng giao khoán, NT, hao hụt | Lập lại đúng ĐMNB trước giao khoán kết cấu chính.

CÁCH VIẾT BẢNG 3 — ghi số tiền cụ thể, file gốc, chênh lệch so với NS:
Vật tư | NS: 7.817.662.415đ; PLHĐ: 8.238.613.912đ (chưa VAT). Quy đổi 8% = 8.897.703.025đ khớp dòng 5.2.2.1 file 1.3 | Đã PK T3+T4; còn lại cập nhật N/N+1 | Biến động giá; nguồn K95 chưa khóa | Khả thi có ĐK | Chốt nguồn, cự ly, đầu mối dự phòng.
XMTB | NS: 400.024.826đ; PLHĐ: 651.736.156đ (chưa VAT). Tăng 271.851.859đ so với bước lập NS | Huy động theo giai đoạn nền–cọc–đúc/lắp | Đơn giá ca máy cao hơn NS; chưa phản ánh lợi thế XM nội bộ | Khả thi có ĐK | ĐV cung ứng tính lại KH, nhiên liệu, NC vận hành.

CÁCH VIẾT BẢNG 6 — so sánh 2.3 vs 1.3, quy đổi VAT, nêu chênh lệch:
DT theo HĐ/KH DT | Đủ có ĐK | "1.5": tổng DT 16.752.710.913đ; Tiết kiệm 34.778.191đ; NT 16.717.932.724đ | "1.5";"1.2" | Đủ căn cứ; cần khóa ghi chú thời gian file 1.5 | Dùng cột NT phân khai dòng tiền.
CP Vật tư | Đủ | "2.3" chưa VAT; "1.3" có VAT. PLHĐ VT 8.238.613.912đ → 8.897.703.025đ (dòng 5.2.2.1 file 1.3). Tăng 296.652.951đ so NS | "2.3";"1.3" | Đàm phán lại đơn giá, tối ưu nguồn.
NS DA theo vòng đời (dòng H) | Đủ | DT 16.752.710.913đ; CP lập NS 17.218.107.864đ; CP lập KHTK 18.240.228.853đ; tăng 1.022.120.989đ; hiệu quả: -2,78% → -8,88%. Dòng I = 17.366.404.725đ chỉ dùng so BSC sau tách NS QLDN 873.824.127đ | "1.3";"BSC" | Phê chuẩn dòng H; BSC dùng dòng I.

CÁCH VIẾT PHỤ BIỂU 01 — BẢNG DÒNG TIỀN THU TỪNG THÁNG (bắt buộc):
Tháng | Giá trị cột NT | TL thu hồi TU | Thu hồi TU | TL tạm giữ | Tạm giữ | DT ròng
T1/2026 | 0 | — | 0 | 0% | 0 | 0
T2/2026 | 0 | — | 0 | 0% | 0 | 0
T3/2026 | 2.787.918.757 | 37,50% | 1.045.469.534 | 7% | 195.154.312 | 1.547.294.910
T4/2026 | 3.835.224.370 | 37,50% | 1.438.209.139 | 7% | 268.465.705 | 2.128.549.525
T5/2026 | 3.955.359.920 | 37,50% | 1.483.259.970 | 7% | 276.875.194 | 2.195.224.755
T6/2026 | 3.031.421.445 | 37,50% | 1.136.783.042 | 7% | 212.199.501 | 1.682.438.901
T7/2026 | 2.149.490.789 | 19,74% | 424.278.315 | 7% | 150.464.355 | 1.574.716.952
T8/2026 | 958.517.444 | 0,00% | 0 | 7% | 67.096.221 | 891.421.222
Cộng | 16.717.932.725 | | 5.528.000.000 | | 1.170.255.290 | 10.019.646.268
(T1-T2 chưa phát sinh thu vì chưa đạt ngưỡng lũy kế 5% GT HĐ. T7 TL thu hồi giảm vì gần hoàn ứng đủ 5.528.000.000đ.)

CÁCH VIẾT BẢNG 9 — TỪNG KHOẢN MỤC VƯỢT NGÂN SÁCH:
5.1.2 Hoàn thành nguồn điện TC | 334.000.000 | Thiếu bước lập NS; phát sinh kéo điện/đấu nối tạm. | Rà soát phạm vi đã có trong HĐ/DT; chốt PA cấp điện tiết kiệm.
5.2.2.1 CP TT Vật tư | 296.652.951 | Giá ký/nguồn cung/cự ly tại KHTK cao hơn NS. | Chốt nguồn, cự ly, đàm phán lại đơn giá VT chính.
5.2.2.2 CP TT Nhân công | 127.996.181 | Đơn giá giao khoán cao hơn NS; HDTC chưa khóa ĐMNB. | Bóc tách lại theo HDTC, khoán đầu việc/SL, kiểm soát NS.
5.2.2.3 CP TT XMTB | 271.851.859 | Đơn giá ca máy/CP máy cao hơn NS. | ĐV cung ứng tính lại KH, nhiên liệu, NC vận hành XM nội bộ.
Tổng tăng sau bù trừ (dòng H) | 1.022.120.989 | | Dùng làm cơ sở theo dõi chênh lệch so NS.

CÁCH VIẾT CHƯƠNG TRÌNH GIẢM LỖ — 7 đầu mối, lượng hóa từng đồng:
1. Tây An lập lại HDTC chi tiết đúng ĐMNB → tăng Tiết kiệm thêm 4,79% DT = 802.454.852đ.
2. Tây An cắt giảm CP gián tiếp 0,5% DT = 83.763.554đ.
3. Tây An cắt giảm CP không chính thức 2% DT = 335.054.218đ.
4. ĐV cung ứng giảm 2% PLHĐ VT+NC = 238.883.290đ.
5. ĐV cung ứng tính lại đơn giá ca máy, giảm 5% PLHĐ XMTB = 32.586.807đ.
6. Ban tài chính rà soát lãi vay; hiện ghi 0đ — cập nhật khi phát sinh.
7. TỔNG tối thiểu: 1.492.742.721đ → đưa hiệu quả về 0%.
=== HẾT MẪU ===
"""

class AppraisalRequest(BaseModel):
    system: str
    user: str
    max_tokens: Optional[int] = 8000

class ExtractRequest(BaseModel):
    filename: str
    text: str
    project_info: dict

async def call_claude_api(payload: dict) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY chưa được cấu hình")
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload,
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code,
                f"Claude API: {resp.json().get('error',{}).get('message', resp.text[:200])}")
        return resp.json()

def read_pdf_digital(data: bytes) -> str:
    """Đọc PDF điện tử bằng pdfplumber."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages[:30]):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(f"[Tr.{i+1}]\n{t}")
                for tbl in (page.extract_tables() or []):
                    for row in tbl:
                        r = " | ".join(str(c or "").strip() for c in row if c)
                        if r.strip():
                            pages.append(r)
            return "\n".join(pages)
    except Exception:
        return ""

async def read_pdf_scan_vision(data: bytes, filename: str) -> str:
    """
    PDF scan: chuyển từng trang thành base64 image rồi gọi Claude Vision.
    Chỉ xử lý tối đa 5 trang đầu để tiết kiệm chi phí.
    """
    try:
        import fitz  # PyMuPDF — nếu có
        doc = fitz.open(stream=data, filetype="pdf")
        pages_b64 = []
        for i, page in enumerate(doc):
            if i >= 5:
                break
            pix = page.get_pixmap(dpi=150)
            img_data = pix.tobytes("png")
            pages_b64.append(base64.b64encode(img_data).decode())
    except ImportError:
        # Không có PyMuPDF — dùng pdf2image nếu có, hoặc báo lỗi
        return f"(PDF scan '{filename}' — cần PyMuPDF để OCR. Vui lòng chuyển sang PDF điện tử.)"
    except Exception as e:
        return f"(Lỗi đọc PDF scan '{filename}': {str(e)[:100]})"

    if not pages_b64:
        return f"(PDF scan '{filename}' — không lấy được trang nào)"

    # Gọi Claude Vision đọc từng ảnh
    content = []
    for b64 in pages_b64:
        content.append({"type": "image", "source": {"type": "base64",
                         "media_type": "image/png", "data": b64}})
    content.append({"type": "text",
                     "text": f"Đây là trang từ file hồ sơ '{filename}'. Hãy đọc và ghi lại TOÀN BỘ nội dung văn bản, số liệu, bảng biểu. Giữ nguyên cấu trúc bảng dạng: cột1 | cột2 | cột3. Không bỏ sót bất kỳ con số nào."})

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": content}]
    }
    result = await call_claude_api(payload)
    return "".join(c.get("text", "") for c in result.get("content", []))

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {"status": "ok", "version": "3.1", "api_configured": bool(key)}

@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    """
    Đọc PDF — tự động phát hiện điện tử hay scan.
    Trả về: text, chars, method (digital/scan/empty), status
    """
    data = await file.read()
    fname = file.filename or "unknown.pdf"

    # Thử đọc điện tử trước
    text = read_pdf_digital(data)
    method = "digital"

    # Nếu ít hơn 100 ký tự → có thể là scan
    if len(text.strip()) < 100:
        method = "scan"
        text = await read_pdf_scan_vision(data, fname)

    chars = len(text.strip())
    status = "ok" if chars > 100 else "empty"

    return {
        "filename": fname,
        "text": text[:12000],
        "chars": chars,
        "method": method,   # "digital" | "scan" | "error"
        "status": status,   # "ok" | "empty"
    }

@app.post("/api/extract-structured")
async def extract_structured(req: ExtractRequest):
    """Bước 1: trích xuất số liệu cấu trúc từ 1 file."""
    SYSTEM = """Bạn là chuyên gia đọc hồ sơ xây lắp của Ban QLHS&CT.
Nhiệm vụ: đọc nội dung file và trích xuất TẤT CẢ số liệu thành JSON.
Trả về ĐÚNG JSON, không có text nào ngoài JSON. Không bịa số — nếu không có thì để null."""

    USER = f"""File: {req.filename}
Dự án: {req.project_info.get('name','')} | HĐ: {req.project_info.get('hd','')}

NỘI DUNG:
{req.text[:12000]}

Trích xuất JSON với các trường:
loai_file, so_hop_dong, ngay_ky, gia_tri_hop_dong, gia_tri_tam_ung,
dieu_kien_thanh_toan, ty_le_thu_hoi_tu, ty_le_tam_giu, nguon_von, von_giao_nam,
doanh_thu_tong, doanh_thu_nghiem_thu, doanh_thu_tiet_kiem,
phan_khai_doanh_thu_theo_thang (dict tháng→giá trị),
ngan_sach_dong_H_chi_phi, ngan_sach_dong_I, ty_le_hieu_qua_phan_tram,
ns_buoc_lap_ngan_sach, ns_buoc_lap_khtk, tang_so_voi_ns,
chi_tiet_tang_tung_khoan (list dict: khoan_muc, gia_tri, nguyen_nhan),
cp_vat_tu_plhd, cp_nhan_cong_plhd, cp_xmtb_plhd, cp_khac_plhd,
cp_vat_tu_ngan_sach, cp_nhan_cong_ngan_sach, cp_xmtb_ngan_sach,
moc_nhan_mat_bang, moc_thi_cong, moc_nghiem_thu, moc_dieu_chinh_hstk,
danh_muc_ho_so (list), cac_diem_chua_dat (list), ghi_chu_khac"""

    import json, re
    try:
        result = await call_claude_api({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": USER}],
            "system": SYSTEM
        })
        raw = "".join(c.get("text","") for c in result.get("content",[]))
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            return {"filename": req.filename, "data": json.loads(m.group()), "ok": True}
    except Exception as e:
        pass
    return {"filename": req.filename, "data": {}, "ok": False}

@app.post("/api/appraise")
async def appraise(req: AppraisalRequest):
    """Bước 2: tổng hợp báo cáo với mẫu Cầu Châu Phong nhúng sẵn."""
    SYSTEM = f"""Bạn là chuyên gia thẩm định cao cấp của Ban Quản lý Hiệu suất và Cải tiến (Ban QLHS&CT), Tập đoàn Bắc Miền Trung.

{MAU_BAO_CAO}

════ BIỂU MẪU BẮT BUỘC — 6 PHẦN, KHÔNG ĐỔI TÊN ════
I. PHẠM VI THẨM ĐỊNH VÀ NGUYÊN TẮC TRÌNH BÀY
   (3 điểm chuẩn + thông tin HĐ/NV chi tiết từng đồng từ file 1.2)
II. THÔNG TIN CHUNG (bảng 5 dòng: tên DA, địa điểm, HĐ, thời gian, nhóm đặc thù)
III. ĐÁNH GIÁ ĐIỀU KIỆN LẬP KHTK (HỢP LỆ–LOGIC–KHẢ THI)
   Bảng 1–5 (theo đúng tên/cột như mẫu Cầu Châu Phong)
IV. PHÂN TÍCH NGÂN SÁCH (ĐẦY ĐỦ–NHẤT QUÁN–BẤT THƯỜNG–BIÊN LN)
   Bảng 6–9 + Phụ biểu 01 dòng tiền từng tháng
V. ĐÁNH GIÁ SO VỚI MỤC TIÊU NĂM BSC
   Bảng 10–11
VI. KẾT LUẬN–KIẾN NGHỊ
   Kết luận (A)/(B)/(C) + Bảng 12 vấn đề trọng yếu + Bảng 13 giảm lỗ 7 đầu mối + Điều kiện ràng buộc

════ NGUYÊN TẮC ════
1. Tên: Ban Quản lý Hiệu suất và Cải tiến (Ban QLHS&CT)
2. Ngân sách vòng đời → dòng H. Dòng I chỉ so BSC (sau tách NS QLDN)
3. "Không nghiệm thu" → "Tiết kiệm"
4. "Ban Tài Chính _ Kế toán" → "Ban tài chính"
5. Bảng 1: chỉ hình thức (hồ sơ/chữ ký/ngày/BM), KHÔNG kết luận kỹ thuật
6. Không nêu đích danh đơn vị liên kết → "Đơn vị cung ứng"/"Đơn vị cung cấp dịch vụ"
7. Giảm lỗ: bắt buộc ≥7%; 7 đầu mối; lượng hóa TỪNG ĐỒNG
8. Đã ký HĐ + tỷ suất âm + không sai sót lớn → kết luận (B)
9. Thiếu số liệu → "Chưa có căn cứ trong hồ sơ để kết luận" — KHÔNG bịa
10. MỨC ĐỘ CHI TIẾT: phải đạt đúng như mẫu Cầu Châu Phong — số tiền cụ thể, tên file cụ thể, dòng cụ thể
11. KHÔNG viết chung chung kiểu "theo file 1.3" mà không có số liệu cụ thể

ĐỊNH DẠNG: HTML thuần. Dùng: <h2>,<h3>,<p>,<table>,<tr>,<th>,<td>,<ul>,<li>."""

    result = await call_claude_api({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": min(req.max_tokens or 8000, 8000),
        "system": SYSTEM,
        "messages": [{"role": "user", "content": req.user}]
    })
    text = "".join(c.get("text","") for c in result.get("content",[]))
    return {"content": [{"text": text}]}
