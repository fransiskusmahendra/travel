from datetime import date, datetime
from html import escape

import streamlit as st

from receipt import BENEFITS, DEFAULT_PREMIUM, build_receipt_text, generate_receipt_pdf, insurance_period, sanitize_filename


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
    .brand { font-size:.78rem; font-weight:800; letter-spacing:.15em; color:#ffb36f; }
    .hero h1 { margin:.25rem 0 .35rem; font-size:2rem; color:white; }
    .hero p { margin:0; color:#d9ebf7; max-width:660px; }
    .panel-title { font-size:1.08rem; font-weight:800; color:var(--navy); margin-bottom:.2rem; }
    .panel-note { color:#607484; font-size:.88rem; margin-bottom:1rem; }
    div[data-testid="stForm"] { background:white; border:1px solid #e1e9ef; border-radius:18px; padding:22px;
      box-shadow:0 8px 24px rgba(18,53,79,.06); }
    .receipt-preview { background:#fff; border:1px dashed #9eb2c1; border-radius:10px; padding:20px 16px;
      font:12px/1.45 'Courier New',monospace; white-space:pre-wrap; color:#15222c; max-height:520px; overflow:auto; }
    .status-ready { background:#e9f8f1; color:#176b4b; border-radius:9px; padding:10px 12px; font-size:.88rem;
      font-weight:700; margin-bottom:12px; }
    .benefit-card { background:white; border:1px solid #e1e9ef; border-radius:14px; padding:15px 16px;
      min-height:90px; margin-bottom:12px; }
    .benefit-card strong { color:var(--navy); font-size:.93rem; display:block; margin-bottom:5px; }
    .benefit-card span { color:var(--orange); font-weight:800; font-size:.88rem; }
    .privacy { color:#687b89; text-align:center; font-size:.8rem; padding-top:24px; }
    div.stDownloadButton > button { background:var(--orange); color:white; border:0; font-weight:800; }
    div.stDownloadButton > button:hover { background:#dc6f12; color:white; border:0; }
    div.stButton > button[kind="primary"] { background:var(--blue); border-color:var(--blue); }
    @media (max-width:700px) { .hero { padding:22px 20px; } .hero h1 { font-size:1.55rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def new_receipt_number() -> str:
    return f"JTR-{datetime.now():%Y%m%d-%H%M%S}"


if "receipt_no" not in st.session_state:
    st.session_state.receipt_no = new_receipt_number()

st.markdown(
    """
    <section class="hero">
      <div class="brand">JASINDO TRAVEL</div>
      <h1>Cetak Nota Asuransi Perjalanan</h1>
      <p>Buat nota pembayaran yang rapi, unduh PDF, lalu cetak pada printer thermal ukuran 58 mm atau 80 mm.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

form_col, preview_col = st.columns([1.08, 0.92], gap="large")

with form_col:
    st.markdown('<div class="panel-title">Data Transaksi</div>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">Lengkapi data berikut untuk membuat nota.</div>', unsafe_allow_html=True)
    with st.form("receipt_form"):
        c1, c2 = st.columns(2)
        with c1:
            receipt_no = st.text_input("Nomor nota *", value=st.session_state.receipt_no)
            transaction_date = st.date_input("Tanggal transaksi *", value=date.today(), format="DD/MM/YYYY")
            customer_name = st.text_input("Nama peserta *", placeholder="Nama sesuai identitas")
            identity_no = st.text_input("NIK / No. Paspor *", placeholder="Masukkan nomor identitas")
            origin = st.text_input("Kota asal", placeholder="Contoh: Jakarta")
        with c2:
            cashier = st.text_input("Petugas *", value="Mahendra")
            transaction_time = st.time_input("Waktu transaksi *", value=datetime.now().time().replace(second=0, microsecond=0))
            phone = st.text_input("Nomor HP *", placeholder="Contoh: 081234567890")
            destination = st.text_input("Tujuan perjalanan", placeholder="Contoh: Bandung")
            premium_text = st.text_input("Premi (Rp) *", value=f"{DEFAULT_PREMIUM:,}".replace(",", "."))
        s1, s2 = st.columns(2)
        with s1:
            duration_days = st.number_input("Masa perlindungan (hari)", min_value=1, max_value=31, value=3)
        with s2:
            paper_width = st.selectbox("Ukuran kertas", [80, 58], format_func=lambda x: f"{x} mm")
        notes = st.text_area("Catatan", placeholder="Opsional", max_chars=180)
        submitted = st.form_submit_button("Buat Nota", type="primary", use_container_width=True)

    start_at = datetime.combine(transaction_date, transaction_time)
    required = {"Nomor nota": receipt_no, "Nama peserta": customer_name, "NIK / No. Paspor": identity_no,
                "Nomor HP": phone, "Petugas": cashier}
    missing = [label for label, value in required.items() if not str(value).strip()]
    data = {
        "receipt_no": receipt_no.strip() or "-", "date_text": start_at.strftime("%d/%m/%Y %H:%M"),
        "cashier": cashier.strip() or "-", "name": customer_name.strip() or "-", "phone": phone.strip() or "-",
        "identity_no": identity_no.strip() or "-",
        "route": " - ".join(part for part in [origin.strip(), destination.strip()] if part) or "-",
        "period": insurance_period(start_at, int(duration_days)), "premium": premium_text,
        "notes": notes.strip(), "paper_width_mm": paper_width,
    }
    if submitted and missing:
        st.error("Lengkapi kolom wajib: " + ", ".join(missing) + ".")
    elif submitted:
        st.session_state.receipt_data = data
        st.session_state.receipt_no = receipt_no
        st.success("Nota berhasil dibuat dan siap diunduh.")

with preview_col:
    st.markdown('<div class="panel-title">Pratinjau Nota</div>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">Pratinjau menyesuaikan ukuran kertas yang dipilih.</div>', unsafe_allow_html=True)
    active_data = st.session_state.get("receipt_data", data)
    preview = build_receipt_text(active_data)
    st.markdown('<div class="status-ready">PDF siap dicetak pada printer thermal</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="receipt-preview">{escape(preview)}</div>', unsafe_allow_html=True)
    if "receipt_data" in st.session_state:
        pdf_bytes = generate_receipt_pdf(active_data)
        st.download_button("Unduh PDF Nota", data=pdf_bytes,
                           file_name=f"nota_{sanitize_filename(active_data['receipt_no'])}.pdf",
                           mime="application/pdf", use_container_width=True)
        if st.button("Transaksi Baru", use_container_width=True):
            st.session_state.pop("receipt_data", None)
            st.session_state.receipt_no = new_receipt_number()
            st.rerun()
    else:
        st.info("Isi formulir dan pilih **Buat Nota** untuk mengaktifkan unduhan PDF.")

st.markdown("### Manfaat Perlindungan")
benefit_columns = st.columns(3)
for index, (title, amount) in enumerate(BENEFITS):
    with benefit_columns[index % 3]:
        st.markdown(f'<div class="benefit-card"><strong>{title}</strong><span>{amount}</span></div>', unsafe_allow_html=True)

st.markdown('<div class="privacy">Data hanya diproses di sesi browser dan tidak disimpan ke basis data. '
            'Untuk printer USB, unduh PDF lalu gunakan menu cetak pada perangkat Anda.</div>', unsafe_allow_html=True)
