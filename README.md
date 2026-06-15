# Jasindo Travel - Cetak Nota

Webapp Streamlit untuk membuat dan mengunduh nota PDF asuransi perjalanan dalam ukuran printer thermal 58 mm atau 80 mm.

## Menjalankan di komputer

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Deploy gratis di Streamlit Community Cloud

1. Buat repository baru di GitHub, lalu unggah `app.py`, `requirements.txt`, dan folder `.streamlit` ke lokasi yang sama.
2. Buka https://share.streamlit.io dan masuk dengan akun GitHub.
3. Pilih **Create app**, repository yang baru dibuat, branch `main`, dan file `app.py`.
4. Pilih **Deploy**. Tidak diperlukan secret atau database.

`app.py` sudah mandiri dan tidak membutuhkan file modul Python lain. Jika memperbarui aplikasi lama, ganti `app.py` di repository lalu pilih **Reboot app** dari halaman pengelolaan Streamlit Cloud.

Alternatif gratis: deploy repository yang sama di Render sebagai Web Service dengan perintah:

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

## Catatan pencetakan

Browser pada hosting cloud tidak dapat mengakses printer thermal USB secara langsung. Unduh PDF nota, buka file tersebut, lalu cetak dengan skala 100% atau **Actual size** pada ukuran kertas yang sesuai.

Data transaksi tidak disimpan ke database. Data hanya digunakan selama sesi aplikasi untuk membuat PDF.
