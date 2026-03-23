"""
Thẩm Định KHTK — Backend v3
Kiến trúc 2 bước:
  Bước 1: /api/extract  — trích xuất & chuẩn hoá số liệu từ từng file
  Bước 2: /api/appraise — tổng hợp báo cáo theo biểu mẫu chuẩn (nhúng mẫu Cầu Châu Phong)
"""
import os, io, httpx, pdfplumber, fitz
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Thẩm Định KHTK v3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

# ══════════════════════════════════════════════════════════════════════════════
# MẪU CHUẨN — Trích từ Báo cáo KQ thẩm định CPXD Cầu Châu Phong FINAL
# Dùng làm few-shot example để AI bám đúng format, mức độ chi tiết, cách viết
# ══════════════════════════════════════════════════════════════════════════════
MAU_BAO_CAO = """
=== VÍ DỤ MẪU BÁO CÁO ĐẠT CHUẨN (CPXD Cầu Châu Phong — Trích đoạn tiêu biểu) ===

CÁCH VIẾT PHẦN I — PHẠM VI THẨM ĐỊNH VÀ NGUYÊN TẮC TRÌNH BÀY:
1. Phiếu trình này không lặp lại nội dung đã thể hiện đầy đủ trong hồ sơ chi tiết đính kèm (KHTK, Gantt chart, CDTC, KH doanh thu, ngân sách vòng đời, hồ sơ mặt bằng, hồ sơ cung ứng, hồ sơ thiết kế…).
2. Phiếu trình tập trung vào các vấn đề trọng yếu cần quyết định: tính hợp lệ – logic – khả thi; các điểm bất thường; rủi ro then chốt; kiến nghị điều chỉnh/điều kiện ràng buộc khi phê chuẩn.
3. Kết luận phải thể hiện rõ: (i) đạt/không đạt điều kiện trình Ban QLHS&CT Tập đoàn thẩm định; (ii) các điều kiện bắt buộc hoàn thiện trước khi triển khai/giải ngân/thi công.

CÁCH VIẾT PHẦN II — THÔNG TIN HỢP ĐỒNG (cụ thể từng đồng, trích từ file nguồn):
"- Giá trị HĐXD phần Công ty CP Tây An: 18.427.982.000 đồng; đã tạm ứng 5.528.000.000 đồng (tối đa 30% GT HĐ). Tiến độ HĐ: 720 ngày.
- Theo hồ sơ "1.2. Thông tin nguồn vốn": thu hồi tạm ứng qua các lần thanh toán, mỗi lần tối thiểu 1% giá trị khối lượng nghiệm thu; thu hồi hết khi giá trị giải ngân đạt 80% giá trị HĐ; điều kiện thanh toán khi lũy kế mỗi lần nghiệm thu đạt 5% giá trị HĐ. Điều khoản tạm giữ: tổng 7% (2% quyết toán + 5% bảo hành).
- Nguồn vốn: theo KHĐT công; vốn giao kỳ này (2026) phần HĐ Công ty 12,902 tỷ đồng."

CÁCH VIẾT BẢNG 1 — chỉ kiểm tra hình thức, ghi rõ file, ảnh hưởng, kiến nghị:
Nhóm hồ sơ | Tình trạng | Nhận xét hợp lệ | Ảnh hưởng đến khả thi | Kiến nghị
Hồ sơ HĐ – nguồn vốn: "1. HĐ số 238...pdf"; "1.2 Thông tin nguồn vốn...pdf" | Đủ 2/2 | Chữ ký: đủ theo bộ hồ sơ scan; ngày tháng: đủ tại file 1.2; biểu mẫu: phù hợp nhóm hồ sơ pháp lý HĐ và nguồn vốn. | Mức ảnh hưởng: rất cao – là căn cứ chốt giá trị HĐ phần Công ty, tạm ứng, điều kiện thanh toán, thời hạn HĐ và nguồn vốn. | Giữ làm căn cứ pháp lý chính cho toàn bộ phần đánh giá HĐ, nguồn vốn và dòng tiền.
Hồ sơ CDTC/HDTC chi tiết: "2.5 Hồ sơ CDTC.pdf" | Có hồ sơ đầu mục; chưa đủ hồ sơ chi tiết | Bộ nộp hiện có bìa/hồ sơ đầu mục. Theo thông tin bổ sung của đơn vị trình, HDTC đang lập/phê duyệt theo HSTK nhưng chưa lập đúng yêu cầu theo Bộ định mức nội bộ. | Mức ảnh hưởng: rất cao – ảnh hưởng trực tiếp đến giao khoán, kiểm soát KL, hao hụt, CL và nghiệm thu. | Phải lập lại, phê duyệt lại HDTC chi tiết đúng Bộ ĐM nội bộ trước giao khoán/thi công hạng mục kết cấu chính.

CÁCH VIẾT BẢNG 3 — nguồn lực, ghi số tiền cụ thể, chỉ rõ file gốc, nêu điểm nghẽn:
Vật tư chính | Theo "2.3 NL thi công": ngân sách 7.817.662.415đ; PLHĐ 8.238.613.912đ — đều chưa VAT. Sau quy đổi 8%, PLHĐ vật tư 8.238.613.912đ ≈ 8.897.703.025đ tại dòng 5.2.2.1 của 1.3. | Đã phân khai tháng 03/2026 và 04/2026; phần còn lại cập nhật theo KH tháng n, n+1. | Biến động giá vật tư chính; nguồn K95, cự ly vận chuyển và pháp lý nguồn vật liệu cần khóa. | Khả thi có điều kiện | Quy đổi về cùng cơ sở thuế trước khi so sánh; chốt nguồn cung, cự ly và đầu mối dự phòng.
Xe máy – thiết bị | Theo "2.3": ngân sách 400.024.826đ; PLHĐ 651.736.156đ chưa VAT. | Huy động theo các giai đoạn nền, cọc khoan nhồi, đúc/lắp dầm. | Đơn giá ca máy/khấu hao/nhiên liệu có nguy cơ cao hơn bước lập NS; cần phản ánh đúng lợi thế xe máy nội bộ. | Khả thi có điều kiện | Đơn vị cung ứng tính lại đơn giá ca máy, khấu hao, nhiên liệu và nhân công vận hành.

CÁCH VIẾT BẢNG 6 — ngân sách, ghi rõ so sánh 2.3 vs 1.3, quy đổi VAT:
Doanh thu theo HĐ/KH Doanh thu | Đầy đủ có điều kiện | "1.5 KH doanh thu": tổng DT 16.752.710.913đ; Tiết kiệm 34.778.191đ; Nghiệm thu 16.717.932.724đ. | "1.5"; "1.2". | Đủ căn cứ quản trị DT; cần khóa lại ghi chú thời gian trong file 1.5. | Dùng cột Nghiệm thu để phân khai dòng tiền; cột Tổng để theo dõi mục tiêu DT.
Chi phí Vật tư | Đầy đủ | "2.3" chưa VAT; "1.3" dùng cơ sở có VAT. Sau quy đổi 8%, PLHĐ vật tư 8.238.613.912đ khớp 8.897.703.025đ tại dòng 5.2.2.1 của 1.3. | "2.3"; "1.3". | CP vật tư tăng 296.652.951đ so với bước lập NS. | Tiếp tục đàm phán đơn giá và tối ưu nguồn cung/cự ly.
Ngân sách DA theo vòng đời (dòng H) | Đầy đủ | DT 16.752.710.913đ; CP bước lập NS 17.218.107.864đ; CP bước lập KHTK 18.240.228.853đ; tăng 1.022.120.989đ; tỷ lệ hiệu quả giảm từ -2,78% xuống -8,88%. Dòng I = 17.366.404.725đ chỉ dùng khi so sánh BSC sau tách NS QLDN 873.824.127đ. | "1.3"; "BSC Tây An". | Kết quả thẩm định NS phải quay về dòng H; dòng I không dùng làm kết luận thẩm định. | Phê chuẩn theo dòng H; khi báo cáo BSC nêu rõ đã tách nhóm G.

CÁCH VIẾT BẢNG 7 — bất thường doanh thu – chi phí – dòng tiền:
Tổng dự án theo dòng H | 16.752.710.913 | 18.240.228.853 | (1.487.517.940) | CP KHTK tăng 1.022.120.989đ so với bước lập NS; các khoản tăng chủ yếu nằm ở điện/nước/dịch vụ, vật tư, nhân công, xe máy. | Phê chuẩn theo dòng H; dòng I chỉ dùng để so sánh BSC.
Phần "Tiết kiệm" | 34.778.191 | — | 34.778.191 | Là phần Tiết kiệm tại file 1.5; giá trị ~0,21% DT, chưa đạt ngưỡng tối thiểu 5%. | Bắt buộc lập điều chỉnh HDTC chi tiết để bù phần thiếu.

CÁCH VIẾT PHỤ BIỂU 01 — dòng tiền thu từng tháng (QUAN TRỌNG):
Tháng | Giá trị cột Nghiệm thu | Tỷ lệ thu hồi TU | Thu hồi TU | Tỷ lệ tạm giữ (7%) | Tạm giữ | Dòng tiền thu ròng
T1/2026 | 0 | — | 0 | 0% | 0 | 0
T2/2026 | 0 | — | 0 | 0% | 0 | 0
T3/2026 | 2.787.918.757 | 37,50% | 1.045.469.534 | 7% | 195.154.312 | 1.547.294.910
T4/2026 | 3.835.224.370 | 37,50% | 1.438.209.139 | 7% | 268.465.705 | 2.128.549.525
T5/2026 | 3.955.359.920 | 37,50% | 1.483.259.970 | 7% | 276.875.194 | 2.195.224.755
T6/2026 | 3.031.421.445 | 37,50% | 1.136.783.042 | 7% | 212.199.501 | 1.682.438.901
T7/2026 | 2.149.490.789 | 19,74% | 424.278.315 | 7% | 150.464.355 | 1.574.716.952
T8/2026 | 958.517.444 | 0,00% | 0 | 7% | 67.096.221 | 891.421.222
Cộng | 16.717.932.725 | | 5.528.000.000 | | 1.170.255.290 | 10.019.646.268
Lưu ý: Tháng 1–2 chưa phát sinh thu do chưa đạt ngưỡng lũy kế 5% GT HĐ. Tháng 7 tỷ lệ thu hồi giảm xuống 19,74% vì gần hoàn ứng đủ 5.528.000.000đ.

CÁCH VIẾT BẢNG 8 — biên lợi nhuận:
Biên LN ròng (bước lập NS) | -2,78% | Mục tiêu nội bộ tối thiểu từ 0% trở lên | -2,78% | Biên âm ngay từ bước lập NS dự án. | Triển khai chương trình giảm lỗ ngay từ khi phê chuẩn KHTK.
Biên LN ròng (bước lập KHTK) | -8,88% | Mục tiêu nội bộ tối thiểu từ 0% trở lên | -8,88% | CP tăng so với bước lập NS; HDTC chi tiết chưa theo ĐMNB; một số CP chuẩn bị và cung ứng tăng. | Phê chuẩn có điều kiện, giao Tây An thực hiện chương trình giảm lỗ bắt buộc.

CÁCH VIẾT BẢNG 9 — vượt ngân sách (từng khoản mục, số tiền cụ thể):
5.1.2 Hoàn thành nguồn điện thi công | 334.000.000 | Thiếu bước lập NS; phát sinh kéo điện/đấu nối điện tạm phục vụ thi công. | Rà soát phạm vi đã có trong HĐ/DT; chốt PA cấp điện, CS sử dụng và cơ chế dùng chung.
5.2.2.1 CP Thực tế Vật tư | 296.652.951 | Giá ký/nguồn cung/cự ly tại thời điểm lập KHTK cao hơn bước lập NS. | Chốt nguồn cung, cự ly và đàm phán lại đơn giá vật tư chính.
5.2.2.2 CP Thực tế Nhân công | 127.996.181 | Đơn giá giao khoán tại thời điểm lập KHTK cao hơn bước lập NS; HDTC chưa khóa theo ĐMNB. | Bóc tách lại theo HDTC chi tiết, khoán theo đầu việc/sản lượng, tăng kiểm soát NS.
5.2.2.3 CP Thực tế Xe máy | 271.851.859 | Đơn giá ca máy/kết cấu CP máy tại thời điểm lập KHTK cao hơn bước lập NS. | Đơn vị cung ứng tính lại KH, nhiên liệu và nhân công vận hành nhóm XM nội bộ.
Tổng tăng sau bù trừ (dòng H) | 1.022.120.989 | Tổng sau bù trừ các khoản tăng và tiết giảm. | Dùng 1.022.120.989đ làm cơ sở theo dõi chênh lệch so với bước lập NS.

CÁCH VIẾT CHƯƠNG TRÌNH GIẢM LỖ (7 đầu mối, lượng hóa từng đồng):
1. Tây An lập lại HDTC chi tiết đúng yêu cầu, mục tiêu tăng mức Tiết kiệm thêm 4,79% DT, tương ứng 802.454.852đ.
2. Tây An rà soát CP gián tiếp, mục tiêu cắt giảm 0,5% DT, tương ứng 83.763.554đ.
3. Tây An rà soát CP không chính thức, mục tiêu cắt giảm 2% DT, tương ứng 335.054.218đ.
4. Đơn vị cung ứng rà soát phương án vật tư, nhân công; mục tiêu giảm 2% PLHĐ (11.944.164.546đ), tương ứng giảm 238.883.290đ.
5. Đơn vị cung ứng tính lại đơn giá ca máy, khấu hao đối với nhóm xe máy nội bộ; mục tiêu giảm 5% PLHĐ xe máy (651.736.156đ), tương ứng giảm 32.586.807đ.
6. Ban tài chính rà soát dòng tiền và KH tài chính năm 2026, phân bổ lãi vay đúng tỷ lệ sử dụng vốn; hiện hồ sơ NS đang ghi lãi vay bằng 0 nên chưa xác định giá trị giảm lỗ trực tiếp.
7. Tổng phương án tăng hiệu quả định lượng tối thiểu: 1.492.742.721đ; đưa tỷ lệ hiệu quả về 0%.

CÁCH VIẾT KẾT LUẬN PHẦN VI:
"Ban QLHS&CT lựa chọn phương án (B) – ĐỦ ĐIỀU KIỆN CÓ ĐIỀU KIỆN. Đề xuất TGĐ phê chuẩn KHTK với các mục tiêu quản trị chính:
- Ngân sách KHTK theo dòng H = [số]đ; khi so sánh BSC dùng dòng I = [số]đ do đã tách [số]đ NS QLDN.
- Kế hoạch dòng tiền thu theo Phụ biểu 01 (tạm tính theo cột Nghiệm thu và điều kiện thanh toán/thu hồi TU/tạm giữ tại hồ sơ 1.2).
- Tiến độ thi công xây dựng đến [ngày].
- Điều kiện về ngân sách/biên LN: KHTK hiện tại đang lỗ [số]đ, tương ứng [tỷ lệ]%; bắt buộc thực hiện chương trình tiết kiệm tối thiểu [số]đ."
=== HẾT MẪU ===
"""

class AppraisalRequest(BaseModel):
    system: str
    user: str
    max_tokens: Optional[int] = 8000

class ExtractRequest(BaseModel):
    filename: str
    text: str      # nội dung file đã đọc
    project_info: dict   # thông tin dự án từ form

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
    return text[:10000] if text.strip() else f"(Không đọc được: {filename})"

async def call_claude(system: str, user: str, max_tokens: int = 8000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY chưa được cấu hình")
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": min(max_tokens, 8000),
                  "system": system, "messages": [{"role": "user", "content": user}]},
        )
        if resp.status_code != 200:
            raise HTTPException(resp.status_code,
                f"Claude API: {resp.json().get('error',{}).get('message', resp.text)}")
        return "".join(c.get("text","") for c in resp.json().get("content",[]))

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/health")
async def health():
    key = os.environ.get("ANTHROPIC_API_KEY","")
    return {"status":"ok","version":"3.0","api_configured":bool(key)}

@app.post("/api/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    """Bước 0: đọc nội dung PDF trên server."""
    data = await file.read()
    text = extract_pdf_text(data, file.filename or "")
    return {"filename": file.filename, "text": text, "chars": len(text)}

@app.post("/api/extract-structured")
async def extract_structured(req: ExtractRequest):
    """
    Bước 1: trích xuất & chuẩn hoá số liệu từ 1 file.
    AI đọc nội dung thô → trả về JSON cấu trúc gồm các trường số liệu quan trọng.
    """
    SYSTEM_EXTRACT = """Bạn là chuyên gia đọc hồ sơ xây lắp của Ban QLHS&CT. 
Nhiệm vụ: đọc nội dung file được cung cấp và trích xuất TẤT CẢ số liệu quan trọng thành JSON.
Trả về ĐÚNG JSON, không có text nào ngoài JSON. Không bịa số — nếu không có thì để null.
Các trường cần trích xuất (tùy loại file):
{
  "loai_file": "hop_dong|nguon_von|ngan_sach|doanh_thu|nguon_luc|mat_bang|cdtc|nhan_su|atlad|tcnb|khac",
  "so_hop_dong": null,
  "ngay_ky": null,
  "gia_tri_hop_dong": null,
  "gia_tri_tam_ung": null,
  "ty_le_tam_ung": null,
  "dieu_kien_thanh_toan": null,
  "ty_le_thu_hoi_tu": null,
  "ty_le_tam_giu": null,
  "nguon_von": null,
  "von_giao_nam": null,
  "tien_do_hop_dong_ngay": null,
  "doanh_thu_tong": null,
  "doanh_thu_nghiem_thu": null,
  "doanh_thu_tiet_kiem": null,
  "phan_khai_doanh_thu_theo_thang": {},
  "ngan_sach_dong_H_tong": null,
  "ngan_sach_dong_H_chi_phi": null,
  "ngan_sach_dong_I": null,
  "loi_nhuan_du_kien": null,
  "ty_le_hieu_qua_phan_tram": null,
  "ns_buoc_lap_ngan_sach": null,
  "ns_buoc_lap_khtk": null,
  "tang_so_voi_ns": null,
  "chi_tiet_tang_tung_khoan": [],
  "cp_vat_tu_plhd": null,
  "cp_nhan_cong_plhd": null,
  "cp_xmtb_plhd": null,
  "cp_khac_plhd": null,
  "cp_vat_tu_ngan_sach": null,
  "cp_nhan_cong_ngan_sach": null,
  "cp_xmtb_ngan_sach": null,
  "moc_nhan_mat_bang": null,
  "moc_thi_cong": null,
  "moc_nghiem_thu_ban_giao": null,
  "moc_dieu_chinh_hstk": null,
  "danh_muc_ho_so_du_thieu": [],
  "cac_diem_chua_dat": [],
  "ghi_chu_khac": null
}"""
    
    user_msg = f"""File: {req.filename}
Thông tin dự án: {req.project_info}

NỘI DUNG FILE:
{req.text[:12000]}

Hãy trích xuất tất cả số liệu quan trọng theo JSON schema trên."""

    result = await call_claude(SYSTEM_EXTRACT, user_msg, 2000)
    # Parse JSON từ kết quả
    import json, re
    try:
        # Tìm JSON trong response
        m = re.search(r'\{[\s\S]*\}', result)
        if m:
            return {"filename": req.filename, "data": json.loads(m.group())}
    except Exception:
        pass
    return {"filename": req.filename, "data": {}, "raw": result[:500]}

@app.post("/api/appraise")
async def appraise(req: AppraisalRequest):
    """
    Bước 2: tổng hợp báo cáo thẩm định.
    Nhúng mẫu Cầu Châu Phong FINAL vào system prompt.
    """
    SYSTEM_APPRAISE = f"""Bạn là chuyên gia thẩm định cao cấp của Ban Quản lý Hiệu suất và Cải tiến (Ban QLHS&CT), Tập đoàn Bắc Miền Trung.

{MAU_BAO_CAO}

════════ BIỂU MẪU BÁO CÁO BẮT BUỘC ════════
Báo cáo PHẢI theo ĐÚNG cấu trúc 6 phần sau — tên phần KHÔNG được thay đổi:

I. PHẠM VI THẨM ĐỊNH VÀ NGUYÊN TẮC TRÌNH BÀY
   (3 điểm như mẫu + thông tin HĐ/nguồn vốn chi tiết từng đồng)

II. THÔNG TIN CHUNG (tóm tắt điểm ảnh hưởng quyết định)
   Bảng thông tin: 5 dòng chuẩn

III. ĐÁNH GIÁ ĐIỀU KIỆN LẬP KHTK (HỢP LỆ – LOGIC – KHẢ THI)
   Bảng 1 – Kiểm tra hồ sơ điều kiện
   Bảng 2 – Đối chiếu mặt bằng ↔ sản lượng ↔ doanh thu
   Bảng 3 – Đối chiếu KH cung ứng ↔ tiến độ ↔ doanh thu
   Bảng 4 – Đối chiếu HSTK điều chỉnh ↔ tiến độ
   Bảng 5 – Đánh giá CDTC/HDTC

IV. PHÂN TÍCH NGÂN SÁCH (ĐẦY ĐỦ – NHẤT QUÁN – BẤT THƯỜNG – BIÊN LỢI NHUẬN)
   Bảng 6 – Kiểm tra cấu phần ngân sách
   Bảng 7 – Bất thường DT–CP–dòng tiền
   Phụ biểu 01 – Dòng tiền thu từng tháng (bắt buộc nếu có số liệu từ file 1.5)
   Bảng 8 – Biên lợi nhuận (so sánh bước lập NS vs bước lập KHTK)
   Bảng 9 – Tổng hợp các mục vượt ngân sách (từng khoản, từng đồng)

V. ĐÁNH GIÁ SO VỚI MỤC TIÊU NĂM BSC
   Bảng 10 – Đối chiếu BSC
   Bảng 11 – Đối chiếu ràng buộc HĐ ↔ KHTK

VI. KẾT LUẬN – KIẾN NGHỊ
   Kết luận: chọn đúng 1 trong 3 mức (A)/(B)/(C) — giải thích rõ căn cứ
   Bảng 12 – Vấn đề trọng yếu (TT | Vấn đề | Mức độ | Kiến nghị | Đơn vị TR | Thời hạn)
   Bảng 13 – Chương trình giảm lỗ: 7 đầu mối, lượng hóa TỪNG ĐỒNG
   Kiến nghị điều kiện ràng buộc: 5 nhóm (mặt bằng, HSTK, cung ứng, ngân sách, ATLĐ)

════════ NGUYÊN TẮC BẮT BUỘC ════════
1. Tên thống nhất: Ban Quản lý Hiệu suất và Cải tiến (Ban QLHS&CT)
2. Ngân sách vòng đời → dùng DÒ‌NG H của file 1.3. Dòng I chỉ dùng so sánh BSC (sau tách NS QLDN)
3. File 1.5: cột "Không nghiệm thu" → gọi là "Tiết kiệm"
4. "Ban Tài Chính _ Kế toán" → viết "Ban tài chính"
5. Bảng 1: chỉ kiểm tra hình thức — đủ hồ sơ/chữ ký/ngày/biểu mẫu, KHÔNG kết luận kỹ thuật
6. Bảng 3: ghi rõ số tiền từng nhóm NL (chưa VAT), chỉ rõ file gốc, nêu chênh lệch vs NS
7. Bảng 9: bám đúng khoản mục theo file 1.3, ghi số tăng/giảm cụ thể từng dòng
8. Không nêu đích danh đơn vị liên kết → dùng "Đơn vị cung ứng"/"Đơn vị cung cấp dịch vụ"
9. Chương trình giảm lỗ: bắt buộc ≥7% giá trị lỗ; 7 đầu mối; lượng hóa từng đồng
10. Kết luận 3 mức: (A) Đủ điều kiện / (B) ĐỦ ĐIỀU KIỆN CÓ ĐIỀU KIỆN / (C) Chưa đủ
11. Đã ký HĐ + tỷ suất âm + không có sai sót lớn → kết luận (B), không kết luận (C)
12. Thiếu số liệu → ghi "Chưa có căn cứ trong hồ sơ để kết luận" — KHÔNG bịa
13. Mức độ chi tiết: PHẢI đạt mức như ví dụ mẫu Cầu Châu Phong — số tiền cụ thể, tên file cụ thể, dòng cụ thể, nguyên nhân cụ thể. KHÔNG được viết chung chung.
14. KHÔNG lặp lại toàn bộ nội dung hồ sơ — chỉ nêu điểm trọng yếu, bất thường, rủi ro, kiến nghị

ĐỊNH DẠNG: HTML thuần. Dùng: <h2>, <h3>, <p>, <table>, <tr>, <th>, <td>, <ul>, <li>.
Mỗi bảng có đủ tiêu đề cột và nội dung chi tiết như mẫu."""

    result = await call_claude(SYSTEM_APPRAISE, req.user, req.max_tokens or 8000)
    return {"content": [{"text": result}]}
