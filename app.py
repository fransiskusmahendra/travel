import base64
import re
from math import cos, radians
from datetime import datetime, timedelta, timezone
from html import escape
from io import BytesIO
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit_js_eval import get_geolocation
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfdoc import PDFDictionary, PDFName
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


COMPANY_NAME = ""
COMPANY_ADDRESS = [
    "Graha Jasindo, Jl. Menteng Raya No. 21",
    "Jakarta Pusat, DKI Jakarta 10340",
    "Indonesia (Kantor Pusat)",
]
WITA_TZ = timezone(timedelta(hours=8))
FIXED_COVERAGE_DAYS = 3
DEFAULT_PREMIUM = 20_000
PREMIUM_OPTIONS = (20_000, 40_000)
NTT_ORIGINS = (
    ("Kupang", -10.1772, 123.6070),
    ("Soe", -9.8607, 124.2830),
    ("Kefamenanu", -9.4467, 124.4781),
    ("Atambua", -9.1061, 124.8925),
    ("Ba'a", -10.7386, 123.1237),
    ("Kalabahi", -8.2186, 124.5186),
    ("Lewoleba", -8.3720, 123.4162),
    ("Larantuka", -8.3431, 122.9870),
    ("Maumere", -8.6199, 122.2111),
    ("Ende", -8.8432, 121.6623),
    ("Bajawa", -8.7847, 120.9672),
    ("Ruteng", -8.6136, 120.4647),
    ("Labuan Bajo", -8.4964, 119.8877),
    ("Waingapu", -9.6567, 120.2641),
    ("Waikabubak", -9.4097, 119.2445),
)
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


def benefits_for_premium(value) -> list[tuple[str, str]]:
    """Return benefits according to the selected premium tier."""
    multiplier = 2 if parse_amount(value) == 40_000 else 1
    adjusted = []
    for index, (title, amount) in enumerate(BENEFITS):
        if index < 3:
            adjusted.append((title, format_rupiah(parse_amount(amount) * multiplier)))
        else:
            adjusted.append((title, amount))
    return adjusted


def origin_from_location(location) -> tuple[str, bool]:
    """Return the nearest supported NTT city, defaulting safely to Kupang."""
    if not isinstance(location, dict) or location.get("error"):
        return "Kupang", False
    try:
        coords = location["coords"]
        latitude = float(coords["latitude"])
        longitude = float(coords["longitude"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("invalid coordinates")
    except (KeyError, TypeError, ValueError):
        return "Kupang", False

    longitude_scale = cos(radians(latitude))
    nearest = min(
        NTT_ORIGINS,
        key=lambda city: (
            (latitude - city[1]) ** 2
            + ((longitude - city[2]) * longitude_scale) ** 2
        ),
    )
    return nearest[0], True


def insurance_period(start_at: datetime, duration_days: int) -> str:
    end_at = start_at + timedelta(days=max(duration_days, 1) - 1)
    return f"{start_at:%d/%m/%Y} s/d {end_at:%d/%m/%Y}"


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    return cleaned.strip("-") or "nota"


def wrap_chars(text: str, width: int) -> list[str]:
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


def build_receipt_text(data: dict) -> str:
    width = 42 if int(data["paper_width_mm"]) == 80 else 30
    divider = "-" * width
    lines = [
        "JASINDO TRAVEL".center(width),
        divider,
        f"No. Nota : {data['receipt_no']}",
        f"Tanggal  : {data['date_text']}",
        f"Petugas Primkopau : {data['cashier']}",
        divider,
    ]
    fields = [
        ("Nama", data["name"]),
        ("Identitas", data["identity_no"]),
        ("No. HP", data["phone"]),
        ("Rute", data["route"]),
        ("Periode", data["period"]),
        ("Premi", format_rupiah(data["premium"])),
    ]
    for label, value in fields:
        wrapped = wrap_chars(value, width - 12)
        lines.append(f"{label:<9}: {wrapped[0]}")
        lines.extend(f"{'':11}{line}" for line in wrapped[1:])
    lines.extend([divider, "MANFAAT / JAMINAN".center(width), divider])
    for index, (benefit, amount) in enumerate(benefits_for_premium(data["premium"]), 1):
        lines.extend(wrap_chars(f"{index}. {benefit}", width))
        lines.extend(f"   {line}" for line in wrap_chars(amount, width - 3))
    if data.get("notes"):
        lines.extend([divider, "CATATAN", *wrap_chars(data["notes"], width)])
    lines.extend([divider, *[line.center(width) for address in COMPANY_ADDRESS for line in wrap_chars(address, width)]])
    lines.extend([
        divider,
        *wrap_chars("Bukti pembayaran sah. Pertanggungan mengikuti syarat dan ketentuan polis.", width),
    ])
    return "\n".join(lines)


def wrap_pdf(text: str, font: str, size: float, max_width: float) -> list[str]:
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
    """Generate a true-size receipt for an 80 mm, 203-DPI thermal printer.

    Most 80 mm printers can only print about 72--74 mm across.  The PDF page
    remains exactly 80 mm wide, while the small side margins keep every glyph
    inside that printable area.  A 14 pt body is intentionally used here
    because the Android print path observed in production reduces the visual
    scale.  PDF viewer preferences also request true-size printing.
    """
    paper_width_mm = int(data["paper_width_mm"])
    page_width = paper_width_mm * mm
    margin = (1 if paper_width_mm == 80 else 2.5) * mm
    content_width = page_width - (2 * margin)
    body_size = 14.0 if paper_width_mm == 80 else 8.2
    line_height = body_size + 4.8
    rows: list[tuple[str, str, float, float]] = []

    def add(text="", font="Helvetica", size=body_size, gap=line_height):
        rows.append((str(text), font, size, gap))

    add("JASINDO TRAVEL", "Helvetica-Bold", body_size + 4.5, line_height + 7)
    add("rule", gap=8)
    for label, value in [("No. Nota", data["receipt_no"]), ("Tanggal", data["date_text"]), ("Petugas Primkopau", data["cashier"])]:
        for line in wrap_pdf(f"{label}: {value}", "Helvetica", body_size, content_width):
            add(line)
    add("rule", gap=9)
    for label, value in [
        ("Nama", data["name"]),
        ("Identitas", data["identity_no"]),
        ("No. HP", data["phone"]),
        ("Rute", data["route"]),
        ("Periode", data["period"]),
    ]:
        for line in wrap_pdf(f"{label}: {value}", "Helvetica", body_size, content_width):
            add(line)
    add(f"Premi: {format_rupiah(data['premium'])}", "Helvetica-Bold", body_size + 0.4, line_height + 3)
    add("rule", gap=9)
    add("MANFAAT / JAMINAN", "Helvetica-Bold", body_size + 0.7, line_height + 3)
    for index, (benefit, amount) in enumerate(benefits_for_premium(data["premium"]), 1):
        for line in wrap_pdf(f"{index}. {benefit}", "Helvetica", body_size, content_width):
            add(line)
        for line in wrap_pdf(amount, "Helvetica-Bold", body_size, content_width - 7):
            add(f"   {line}", "Helvetica-Bold", body_size, line_height + 1.5)
    if data.get("notes"):
        add("rule", gap=9)
        add("CATATAN", "Helvetica-Bold")
        for line in wrap_pdf(data["notes"], "Helvetica", body_size, content_width):
            add(line)
    add("rule", gap=9)
    for address in [COMPANY_NAME, *COMPANY_ADDRESS]:
        for line in wrap_pdf(address, "Helvetica", body_size, content_width):
            add(line, "Helvetica-Bold" if address == COMPANY_NAME else "Helvetica")
    add("rule", gap=9)
    for line in wrap_pdf(
        "Bukti pembayaran sah. Pertanggungan mengikuti syarat dan ketentuan polis.",
        "Helvetica",
        body_size - 0.6,
        content_width,
    ):
        add(line, "Helvetica", body_size - 0.6)

    page_height = max(sum(row[3] for row in rows) + (12 * mm), 150 * mm)
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(page_width, page_height), pageCompression=1)
    # Ask compatible Android PDF viewers/printer services to keep the true
    # 80 mm page size instead of silently shrinking it to a generic page.
    pdf._doc.Catalog.ViewerPreferences = PDFDictionary(
        {"PrintScaling": PDFName("None")}
    )
    y = page_height - (4 * mm)
    print_black = HexColor("#000000")
    centered_texts = {COMPANY_NAME, "JASINDO TRAVEL", "MANFAAT / JAMINAN",}
    for address in COMPANY_ADDRESS:
        centered_texts.update(wrap_pdf(address, "Helvetica", body_size, content_width))
    for text, font, size, gap in rows:
        if text == "rule":
            pdf.setStrokeColor(print_black)
            pdf.setLineWidth(0.8)
            pdf.line(margin, y, page_width - margin, y)
            y -= gap
            continue
        pdf.setFillColor(print_black)
        pdf.setFont(font, size)
        centered = text in centered_texts
        x = (page_width - stringWidth(text, font, size)) / 2 if centered else margin
        pdf.drawString(max(x, margin), y, text)
        y -= gap
    pdf.showPage()
    pdf.save()
    output.seek(0)
    return output.getvalue()


def render_android_print_button(pdf_bytes: bytes, receipt_no: str) -> None:
    """Open the generated PDF from a user gesture for Android print/share apps."""
    encoded_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    safe_filename = f"nota_{sanitize_filename(receipt_no)}.pdf"
    components.html(
        f"""
        <style>
          * {{ box-sizing: border-box; }}
          body {{ margin: 0; font-family: Arial, sans-serif; }}
          button {{
            width: 100%; min-height: 42px; border: 0; border-radius: 8px;
            background: #0075bd; color: white; font-size: 16px;
            font-weight: 800; cursor: pointer;
          }}
          button:active {{ background: #07588d; }}
          #status {{ margin: 8px 2px 0; color: #526775; font-size: 12px; }}
        </style>
        <button id="print-button" type="button">🖨️ Cetak Nota</button>
        <div id="status"></div>
        <script>
          const pdfBase64 = "{encoded_pdf}";
          const filename = "{safe_filename}";

          document.getElementById("print-button").addEventListener("click", () => {{
            const binary = atob(pdfBase64);
            const bytes = new Uint8Array(binary.length);
            for (let index = 0; index < binary.length; index++) {{
              bytes[index] = binary.charCodeAt(index);
            }}

            const pdfBlob = new Blob([bytes], {{ type: "application/pdf" }});
            const pdfUrl = URL.createObjectURL(pdfBlob);
            const opened = window.open(pdfUrl, "_blank");

            if (opened) {{
              document.getElementById("status").textContent =
                "Nota dibuka. Pilih menu Cetak atau Bagikan ke aplikasi printer Bluetooth.";
              setTimeout(() => URL.revokeObjectURL(pdfUrl), 120000);
              return;
            }}

            const fallback = document.createElement("a");
            fallback.href = pdfUrl;
            fallback.download = filename;
            fallback.click();
            document.getElementById("status").textContent =
              "Popup diblokir. Nota telah diunduh; buka PDF lalu pilih Cetak.";
            setTimeout(() => URL.revokeObjectURL(pdfUrl), 120000);
          }});
        </script>
        """,
        height=72,
    )


st.set_page_config(page_title="Cetak Nota | Jasindo Travel", page_icon="J", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
    :root { --navy:#073b68; --blue:#0075bd; --orange:#f58220; --ink:#172b3a; }
    .stApp { background:#f4f7fa; color:var(--ink); }
    .block-container { max-width:1180px; padding-top:1.5rem; padding-bottom:3rem; }
    .hero { background:linear-gradient(135deg,#06375f 0%,#07588d 68%,#0877b5 100%); border-radius:20px;
      padding:26px 30px; color:white; margin-bottom:22px; box-shadow:0 14px 34px rgba(7,59,104,.18);
      position:relative; overflow:hidden; }
    .hero:after { content:""; position:absolute; width:210px; height:210px; border-radius:50%; right:-70px;
      top:-105px; border:34px solid rgba(245,130,32,.9); }
    .brand { font-size:2.35rem; line-height:1.1; font-weight:900; letter-spacing:.055em; color:#ffb36f; }
    .hero-subtitle { margin:.55rem 0 0; font-size:1.15rem; line-height:1.35; font-weight:700; color:white; }
    .panel-title { font-size:1.08rem; font-weight:800; color:var(--navy); margin-bottom:.2rem; }
    .panel-note { color:#607484; font-size:.88rem; margin-bottom:1rem; }
    div[data-testid="stForm"] { background:white; border:1px solid #e1e9ef; border-radius:18px; padding:22px;
      box-shadow:0 8px 24px rgba(18,53,79,.06); }
    div[data-testid="stWidgetLabel"] p,
    label[data-testid="stWidgetLabel"] p,
    .stTextInput label p,
    .stTextArea label p,
    .stDateInput label p,
    .stTimeInput label p,
    .stNumberInput label p,
    .stSelectbox label p { color:#111111 !important; opacity:1 !important; font-weight:700 !important; }
    .receipt-preview { background:#fff; border:1px dashed #9eb2c1; border-radius:10px; padding:20px 16px;
      font:12px/1.45 'Courier New',monospace; white-space:pre-wrap; color:#15222c; max-height:520px; overflow:auto; }
    .status-ready { background:#e9f8f1; color:#176b4b; border-radius:9px; padding:10px 12px; font-size:.88rem;
      font-weight:700; margin-bottom:12px; }
    .benefit-card { background:white; border:1px solid #e1e9ef; border-radius:14px; padding:15px 16px;
      min-height:90px; margin-bottom:12px; }
    .benefit-card strong { color:var(--navy); font-size:.93rem; display:block; margin-bottom:5px; }
    .benefit-card span { color:var(--orange); font-weight:800; font-size:.88rem; }
    .privacy { color:#687b89; text-align:center; font-size:.8rem; padding-top:24px; }
    .qira-footer { margin-top:18px; padding:22px 18px 8px; border-top:1px solid #dce5eb; text-align:center; }
    .qira-footer-logo { display:block; width:170px; max-width:55%; height:auto; margin:0 auto 8px; }
    .qira-tagline { color:#526775; font-size:.78rem; font-style:italic; font-weight:700; margin-bottom:12px; }
    .qira-managed { color:#263d4d; font-size:.86rem; font-weight:800; margin-bottom:6px; }
    .copyright { color:#687b89; text-align:center; font-size:.76rem; }
    div.stDownloadButton > button { background:var(--orange); color:white; border:0; font-weight:800; }
    div.stDownloadButton > button:hover { background:#dc6f12; color:white; border:0; }
    div.stButton > button[kind="primary"] { background:var(--blue); border-color:var(--blue); }
    @media (max-width:700px) { .hero { padding:22px 20px; } .brand { font-size:1.8rem; }
      .hero-subtitle { font-size:1rem; }
      .qira-footer-logo { width:145px; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def new_receipt_number() -> str:
    return f"JTR-{datetime.now(WITA_TZ):%Y%m%d-%H%M%S}"


def reset_transaction() -> None:
    """Clear every transaction field and prepare a fresh receipt number."""
    st.session_state.pop("receipt_data", None)
    st.session_state.update(
        {
            "receipt_no_input": new_receipt_number(),
            "customer_name_input": "",
            "identity_no_input": "",
            "cashier_input": "",
            "phone_input": "",
            "destination_input": "",
            "premium_input": DEFAULT_PREMIUM,
            "notes_input": "",
        }
    )


if "receipt_no_input" not in st.session_state:
    reset_transaction()
if st.session_state.get("premium_input") not in PREMIUM_OPTIONS:
    st.session_state["premium_input"] = DEFAULT_PREMIUM

logo_path = Path(__file__).parent / "assets" / "qira-logo.png"
logo_base64 = base64.b64encode(logo_path.read_bytes()).decode("ascii") if logo_path.exists() else ""

st.markdown(
    """
    <section class="hero">
      <div class="brand">JASINDO TRAVEL</div>
      <div class="hero-subtitle">Cetak Nota Asuransi Perjalanan</div>
    </section>
    """,
    unsafe_allow_html=True,
)

form_col, preview_col = st.columns([1.08, 0.92], gap="large")

with form_col:
    st.markdown('<div class="panel-title">Data Transaksi</div>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">Lengkapi data berikut untuk membuat nota.</div>', unsafe_allow_html=True)
    premium_value = st.selectbox(
        "Pilihan premi *",
        options=PREMIUM_OPTIONS,
        format_func=format_rupiah,
        key="premium_input",
    )
    st.caption(
        "Premi Rp20.000 menggunakan jaminan standar. Pada premi Rp40.000, "
        "jaminan meninggal dunia, cacat tetap, dan perawatan medis menjadi 2x."
    )
    location_data = get_geolocation()
    origin, location_detected = origin_from_location(location_data)
    with st.form("receipt_form"):
        c1, c2 = st.columns(2)
        with c1:
            receipt_no = st.text_input("Nomor nota *", key="receipt_no_input")
            customer_name = st.text_input(
                "Nama peserta *", placeholder="Nama sesuai identitas", key="customer_name_input"
            )
            identity_no = st.text_input(
                "NIK / No. Paspor *", placeholder="Masukkan nomor identitas", key="identity_no_input"
            )
        with c2:
            cashier = st.text_input("Petugas Primkopau *", key="cashier_input")
            phone = st.text_input(
                "Nomor HP *", placeholder="Contoh: 081234567890", key="phone_input"
            )
            destination = st.text_input(
                "Tujuan perjalanan", placeholder="Contoh: Bandung", key="destination_input"
            )
        paper_width = 80
        notes = st.text_area("Catatan", placeholder="Opsional", max_chars=180, key="notes_input")
        submitted = st.form_submit_button("Buat Nota", type="primary", use_container_width=True)

    start_at = datetime.now(WITA_TZ)
    required = {"Nomor nota": receipt_no, "Nama peserta": customer_name, "NIK / No. Paspor": identity_no,
                "Nomor HP": phone, "Petugas Primkopau": cashier}
    missing = [label for label, value in required.items() if not str(value).strip()]
    data = {
        "receipt_no": receipt_no.strip() or "-", "date_text": start_at.strftime("%d/%m/%Y %H:%M WITA"),
        "cashier": cashier.strip() or "-", "name": customer_name.strip() or "-", "phone": phone.strip() or "-",
        "identity_no": identity_no.strip() or "-",
        "route": " - ".join(part for part in [origin.strip(), destination.strip()] if part) or "-",
        "period": insurance_period(start_at, FIXED_COVERAGE_DAYS), "premium": premium_value,
        "notes": notes.strip(), "paper_width_mm": paper_width,
    }
    if submitted and missing:
        st.error("Lengkapi kolom wajib: " + ", ".join(missing) + ".")
    elif submitted:
        st.session_state.receipt_data = data
        st.success("Nota berhasil dibuat dan siap dicetak atau diunduh.")

with preview_col:
    st.markdown('<div class="panel-title">Pratinjau Nota</div>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">Pratinjau menyesuaikan ukuran kertas yang dipilih.</div>', unsafe_allow_html=True)
    active_data = st.session_state.get("receipt_data", data)
    if active_data["premium"] != premium_value:
        st.info("Pilihan premi berubah. Tekan **Buat Nota** untuk memperbarui pratinjau dan PDF.")
    preview = build_receipt_text(active_data)
    st.markdown('<div class="status-ready">PDF siap dicetak pada printer thermal</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="receipt-preview">{escape(preview)}</div>', unsafe_allow_html=True)
    if "receipt_data" in st.session_state:
        pdf_bytes = generate_receipt_pdf(active_data)
        render_android_print_button(pdf_bytes, active_data["receipt_no"])
        st.caption(
            "Pada Android, pilih **Cetak** atau bagikan PDF ke aplikasi printer Bluetooth. "
            "Gunakan kertas **80 mm**, skala **100% / Actual size** (bukan Fit to page), margin **None**, "
            "dan nonaktifkan header/footer."
        )
        st.download_button("Download Nota", data=pdf_bytes,
                           file_name=f"nota_{sanitize_filename(active_data['receipt_no'])}.pdf",
                           mime="application/pdf", use_container_width=True)
        st.button(
            "Transaksi Baru",
            on_click=reset_transaction,
            use_container_width=True,
            help="Kosongkan seluruh field dan buat nomor nota baru.",
        )
        st.caption("Tombol **Cetak Nota** dapat digunakan kembali untuk mencetak ulang transaksi terakhir.")
    else:
        st.info("Isi formulir dan pilih **Buat Nota** untuk mengaktifkan unduhan PDF.")

st.markdown(f"### Manfaat Perlindungan — {format_rupiah(premium_value)}")
benefit_columns = st.columns(3)
for index, (title, amount) in enumerate(benefits_for_premium(premium_value)):
    with benefit_columns[index % 3]:
        st.markdown(f'<div class="benefit-card"><strong>{title}</strong><span>{amount}</span></div>', unsafe_allow_html=True)

st.markdown('<div class="privacy">Data hanya diproses di sesi browser dan tidak disimpan ke basis data. '
            'Pada Android, pencetakan diteruskan melalui layanan atau aplikasi printer Bluetooth yang terpasang.</div>',
            unsafe_allow_html=True)
logo_html = (
    f'<img class="qira-footer-logo" src="data:image/png;base64,{logo_base64}" alt="Logo QIRA">'
    if logo_base64
    else '<div class="qira-managed">QIRA</div>'
)
st.markdown(
    f'''<footer class="qira-footer">
      {logo_html}
      <div class="qira-tagline">Your Business, Understood</div>
      <div class="qira-managed">Build and Managed by Qira Automation &amp; System Solution</div>
      <div class="copyright">&copy; 2026 QIRA. Hak cipta dilindungi.</div>
    </footer>''',
    unsafe_allow_html=True,
)
