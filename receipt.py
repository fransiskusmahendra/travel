import re
from datetime import datetime, timedelta
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


COMPANY_NAME = "PT ASURANSI JASA INDONESIA"
COMPANY_ADDRESS = ["Graha Jasindo, Jl. Menteng Raya No. 21", "Jakarta Pusat, DKI Jakarta 10340", "Indonesia (Kantor Pusat)"]
DEFAULT_PREMIUM = 20_000
BENEFITS = [
    ("Meninggal dunia akibat kecelakaan", "IDR 250.000.000"),
    ("Cacat tetap akibat kecelakaan", "IDR 250.000.000"),
    ("Biaya perawatan medis darurat", "IDR 25.000.000"),
    ("Kehilangan bagasi / barang pribadi", "IDR 2.000.000"),
    ("Penundaan perjalanan minimum 6 jam", "Maks. IDR 2.000.000"),
    ("Pembatalan perjalanan", "Sesuai harga tiket maksimal"),
]


def parse_amount(value) -> int:
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else 0


def format_rupiah(value) -> str:
    return "IDR {:,}".format(parse_amount(value)).replace(",", ".")


def insurance_period(start_at: datetime, duration_days: int) -> str:
    end_at = start_at + timedelta(days=max(duration_days, 1) - 1)
    return f"{start_at:%d/%m/%Y} s/d {end_at:%d/%m/%Y}"


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "nota"


def _wrap_chars(text: str, width: int) -> list[str]:
    words, lines, current = str(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _text_lines(data: dict, width: int) -> list[str]:
    divider = "-" * width
    lines = [COMPANY_NAME.center(width), "JASINDO TRAVEL".center(width), divider,
             f"No. Nota : {data['receipt_no']}", f"Tanggal  : {data['date_text']}",
             f"Petugas  : {data['cashier']}", divider]
    fields = [("Nama", data["name"]), ("Identitas", data["identity_no"]), ("No. HP", data["phone"]),
              ("Rute", data["route"]), ("Periode", data["period"]), ("Premi", format_rupiah(data["premium"]))]
    for label, value in fields:
        wrapped = _wrap_chars(value, width - 12)
        lines.append(f"{label:<9}: {wrapped[0]}")
        lines.extend(f"{'':11}{line}" for line in wrapped[1:])
    lines.extend([divider, "MANFAAT / JAMINAN".center(width), divider])
    for index, (benefit, amount) in enumerate(BENEFITS, 1):
        lines.extend(_wrap_chars(f"{index}. {benefit}", width))
        lines.extend(f"   {line}" for line in _wrap_chars(amount, width - 3))
    if data.get("notes"):
        lines.extend([divider, "CATATAN", *_wrap_chars(data["notes"], width)])
    lines.extend([divider, *[line.center(width) for address in COMPANY_ADDRESS for line in _wrap_chars(address, width)]])
    lines.extend([divider, *_wrap_chars("Bukti pembayaran sah. Pertanggungan mengikuti syarat dan ketentuan polis.", width),
                  "", "TERIMA KASIH".center(width)])
    return lines


def build_receipt_text(data: dict) -> str:
    width = 42 if int(data["paper_width_mm"]) == 80 else 30
    return "\n".join(_text_lines(data, width))


def _wrap_pdf(text: str, font: str, size: float, max_width: float) -> list[str]:
    words, lines, current = str(text).split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def generate_receipt_pdf(data: dict) -> bytes:
    paper_width_mm = int(data["paper_width_mm"])
    page_width = paper_width_mm * mm
    margin = (4 if paper_width_mm == 80 else 3) * mm
    content_width = page_width - (2 * margin)
    body_size = 7.7 if paper_width_mm == 80 else 6.7
    line_height = body_size + 3.2
    rows: list[tuple[str, str, float, float]] = []

    def add(text="", font="Helvetica", size=body_size, gap=line_height):
        rows.append((str(text), font, size, gap))

    add(COMPANY_NAME, "Helvetica-Bold", body_size + 1, line_height + 1)
    add("JASINDO TRAVEL", "Helvetica-Bold", body_size + 2, line_height + 4)
    add("rule", gap=7)
    for label, value in [("No. Nota", data["receipt_no"]), ("Tanggal", data["date_text"]), ("Petugas", data["cashier"])]:
        add(f"{label}: {value}")
    add("rule", gap=8)
    for label, value in [("Nama", data["name"]), ("Identitas", data["identity_no"]), ("No. HP", data["phone"]),
                         ("Rute", data["route"]), ("Periode", data["period"])]:
        for line in _wrap_pdf(f"{label}: {value}", "Helvetica", body_size, content_width):
            add(line)
    add(f"Premi: {format_rupiah(data['premium'])}", "Helvetica-Bold", body_size + 0.5, line_height + 2)
    add("rule", gap=8)
    add("MANFAAT / JAMINAN", "Helvetica-Bold", body_size + 0.5, line_height + 2)
    for index, (benefit, amount) in enumerate(BENEFITS, 1):
        for line in _wrap_pdf(f"{index}. {benefit}", "Helvetica", body_size, content_width):
            add(line)
        for line in _wrap_pdf(amount, "Helvetica-Bold", body_size, content_width - 7):
            add(f"   {line}", "Helvetica-Bold", body_size, line_height + 1)
    if data.get("notes"):
        add("rule", gap=8)
        add("CATATAN", "Helvetica-Bold")
        for line in _wrap_pdf(data["notes"], "Helvetica", body_size, content_width):
            add(line)
    add("rule", gap=8)
    for address in [COMPANY_NAME, *COMPANY_ADDRESS]:
        for line in _wrap_pdf(address, "Helvetica", body_size, content_width):
            add(line, "Helvetica-Bold" if address == COMPANY_NAME else "Helvetica")
    add("rule", gap=8)
    for line in _wrap_pdf("Bukti pembayaran sah. Pertanggungan mengikuti syarat dan ketentuan polis.",
                          "Helvetica", body_size - 0.4, content_width):
        add(line, "Helvetica", body_size - 0.4)
    add("TERIMA KASIH", "Helvetica-Bold", body_size + 1, line_height + 5)

    page_height = max(sum(row[3] for row in rows) + (16 * mm), 150 * mm)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(page_width, page_height), pageCompression=1)
    y = page_height - (7 * mm)
    navy, orange = HexColor("#073B68"), HexColor("#F58220")
    for text, font, size, gap in rows:
        if text == "rule":
            pdf.setStrokeColor(HexColor("#8CA0AF")); pdf.setLineWidth(0.45)
            pdf.line(margin, y, page_width - margin, y); y -= gap
            continue
        pdf.setFillColor(orange if text == "JASINDO TRAVEL" else navy if font == "Helvetica-Bold" else HexColor("#172B3A"))
        pdf.setFont(font, size)
        centered = text in {COMPANY_NAME, "JASINDO TRAVEL", "MANFAAT / JAMINAN", "TERIMA KASIH"}
        x = (page_width - stringWidth(text, font, size)) / 2 if centered else margin
        pdf.drawString(max(x, margin), y, text); y -= gap
    pdf.showPage(); pdf.save(); output.seek(0)
    return output.getvalue()
