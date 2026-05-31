# TASK PLAN UPDATE — Perbaikan Fitur Smart/AI (A–G)

> **Tujuan utama:** Menyelaraskan fitur AI/smart SyamAdmin dengan misinya — memudahkan
> admin server walau pengetahuan sysadmin user **sangat minim**.
>
> Dokumen ini adalah rencana implementasi coding **step-by-step** untuk 7 temuan (A–G)
> hasil analisis. Setiap fase berisi: tujuan, file terdampak, langkah konkret, sketsa
> kode, cara verifikasi, dan risiko.

---

## Ringkasan Temuan

| Kode | Temuan | Severity | Fase |
|------|--------|----------|------|
| A | Action-name AI ≠ method nyata → perintah gagal diam-diam | 🔴 CRITICAL | 1 |
| B | `backup restore` diiklankan tapi tidak ada | 🔴 CRITICAL | 2 |
| C | Fallback tanpa API key memetakan ke method hantu | 🟠 HIGH | 3 |
| D | Konfirmasi "ya/ok" didokumentasikan tapi tak diterima kode | 🟠 HIGH | 4 |
| E | AI tidak punya konteks state server (LEMP/sites/SSL) | 🟠 HIGH | 5 |
| F | Error mentah tidak diterjemahkan via `analyze_logs` | 🟡 MEDIUM | 6 |
| G | Tidak ada onboarding/hardening wizard | 🟡 MEDIUM | 7 |

## Urutan Eksekusi & Dependency

```
Fase 1 (A) ──┬─> Fase 3 (C)   [C pakai action registry dari A]
             └─> Fase 2 (B)   [B mendaftarkan restore ke registry A]
Fase 4 (D)   [independen]
Fase 5 (E)   [independen, tapi idealnya setelah A agar AI bisa pakai state]
Fase 6 (F)   [independen]
Fase 7 (G)   [independen, paling akhir karena paling besar]
```

**Rekomendasi urutan kerja:** 1 → 2 → 3 → 4 → 5 → 6 → 7.
Fase 1–4 wajib selesai dulu (menyentuh janji inti produk). Fase 5–7 menyusul.

## Konvensi

- Semua perubahan disertai komentar berbahasa Indonesia yang ringkas, mengikuti gaya kode existing.
- Tidak menambah dependency baru kecuali disebut eksplisit.
- Setiap fase punya commit terpisah dengan prefix `fix:` / `feat:`.
- Verifikasi minimal: `python3 -c "import ast; ast.parse(open('<file>').read())"` lulus + uji manual jalur terkait.

---

## FASE 1 — (A) Action Registry: selaraskan kosakata AI dengan method nyata

### Tujuan
Hilangkan kegagalan diam-diam. Setiap aksi yang diiklankan ke AI **harus** terpetakan ke
method yang benar-benar dieksekusi, atau ke handler khusus.

### File terdampak
- `modules/brain.py` (sinkron system prompt)
- `modules/telegram_bot.py` (resolusi alias di `_execute_ai_action`)
- `modules/monitor.py` (tambah method tipis yang hilang)
- `modules/firewall.py`, `modules/site_manager.py`, `modules/provisioner.py` (method hilang)

### Langkah

**1.1 — Buat peta alias aksi terpusat di `telegram_bot.py`** (di atas class `SyamAdminBot`):

```python
# Peta alias: nama-aksi-yang-diajarkan-ke-AI -> nama-method-nyata di modul.
# Mencegah kegagalan diam-diam saat AI memakai nama ramah yang berbeda dari method.
ACTION_ALIASES = {
    "monitor": {
        "status": "get_status_report",
        "services": "get_services_status",
        "disk_usage": "get_disk_report",
        "top_processes": "get_top_processes",
        "connections": "get_connections",
    },
    "firewall": {
        "reset": "setup_defaults",
    },
    "site_manager": {
        "disable_site": "disable_site",   # method baru (lihat 1.3)
    },
    "provisioner": {
        "setup_composer": "setup_composer",  # method baru (lihat 1.4)
    },
    "backup": {
        "restore": "restore",  # diimplementasi di Fase 2
    },
}
```

**1.2 — Resolusi alias di `_execute_ai_action`** ([telegram_bot.py:446](modules/telegram_bot.py#L446)).
Sebelum `getattr(module, action)`, terjemahkan via alias; jika tetap tidak ketemu, beri
pesan jelas + saran perintah valid (bukan "belum diimplementasi" yang membingungkan):

```python
async def _execute_ai_action(self, parsed: dict) -> str:
    module_name = parsed.get("module", "")
    action = parsed.get("action", "")
    params = parsed.get("params", {})

    # Resolusi alias: terjemahkan nama-aksi-AI -> method nyata
    action = ACTION_ALIASES.get(module_name, {}).get(action, action)

    try:
        module = self.modules.get(module_name)
        if not module:
            return f"❌ Modul `{module_name}` tidak ditemukan."

        method = getattr(module, action, None)
        if method and callable(method):
            result = await method(**params) if params else await method()
            return result if isinstance(result, str) else str(result)

        # Special cases (executor) — TETAP seperti sebelumnya
        if module_name == "executor" and action == "service_restart":
            ...
        if module_name == "executor" and action == "run_command":
            ...

        # Tidak ditemukan: jangan diam-diam — beri tahu user + saran
        logger.warning(f"AI action tak terpetakan: {module_name}.{action}")
        return (
            f"⚠️ Maaf, aksi `{module_name}.{action}` belum tersedia.\n"
            f"Coba `/help` untuk daftar perintah yang didukung."
        )
    except Exception as e:
        logger.error(f"AI action execution error: {e}", exc_info=True)
        return f"❌ Error executing action: {e}"
```

**1.3 — Tambah method tipis yang hilang di `monitor.py`:**

```python
async def get_disk_report(self) -> str:
    """Laporan penggunaan disk ramah-pemula (untuk /ai cek disk)."""
    r = await self.executor.run("df -h / /var /home 2>/dev/null", module="monitor", check=False)
    m = await self.collect_metrics()
    return (
        f"💽 *Penggunaan Disk*\n"
        f"{self._progress_bar(m['disk_percent'])} `{m['disk_percent']}%` "
        f"(`{m['disk_used_gb']}/{m['disk_total_gb']} GB`)\n\n"
        f"```\n{r['stdout'][:2000]}\n```"
    )

async def get_top_processes(self) -> str:
    """Top 8 proses berdasarkan CPU & RAM."""
    r = await self.executor.run(
        "ps aux --sort=-%cpu | head -9 | awk '{print $11, $3\"%cpu\", $4\"%mem\"}'",
        module="monitor", check=False,
    )
    return f"🔝 *Top Proses*\n```\n{r['stdout'][:2000]}\n```"

async def get_connections(self) -> str:
    """Ringkasan koneksi jaringan aktif."""
    r = await self.executor.run(
        "ss -tunp 2>/dev/null | head -20", module="monitor", check=False,
    )
    return f"🌐 *Koneksi Aktif*\n```\n{r['stdout'][:2500]}\n```"
```

**1.4 — Tambah method hilang di `site_manager.py` & `provisioner.py`:**

```python
# site_manager.py — nonaktifkan site tanpa menghapus config
async def disable_site(self, domain: str) -> str:
    await self.executor.run(
        f"rm -f /etc/nginx/sites-enabled/{domain}", module="site_manager",
    )
    test = await self.executor.run("nginx -t", module="site_manager", check=False)
    if test["success"]:
        await self.executor.run("systemctl reload nginx", module="site_manager")
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE sites SET status='disabled' WHERE domain=?", (domain,))
            conn.commit(); conn.close()
        except Exception:
            pass
        return f"⏸️ Site `{domain}` dinonaktifkan (config tetap tersimpan)."
    return f"❌ Gagal menonaktifkan `{domain}`:\n```\n{test['stderr'][:300]}\n```"
```

```python
# provisioner.py — install composer terpisah (ekstrak dari install_lemp Step 5)
async def setup_composer(self) -> str:
    r = await self.executor.run(
        "curl -sS https://getcomposer.org/installer | php -- "
        "--install-dir=/usr/local/bin --filename=composer",
        module="provisioner", timeout=60,
    )
    if r["success"]:
        return "✅ Composer berhasil diinstall."
    return f"❌ Gagal install Composer:\n```\n{r['stderr'][:300]}\n```"
```

> Catatan: di `install_lemp` Step 5, ganti blok inline composer menjadi
> `r = await self.setup_composer()` agar tidak ada duplikasi logika.

**1.5 — Sinkronkan SYSTEM_PROMPT di `brain.py`** ([brain.py:39-46](modules/brain.py#L39-L46)).
Pertahankan nama ramah (karena alias map sudah menanganinya), tapi **hapus aksi yang
tidak akan pernah didukung** dan tambahkan yang baru. Pastikan daftar aksi = union dari
method nyata + alias yang valid. Verifikasi silang manual dengan `ACTION_ALIASES`.

### Verifikasi Fase 1
- [ ] `/ai cek status server` → benar-benar menjalankan `get_status_report` (bukan teks kosong).
- [ ] `/ai berapa pemakaian disk` → `get_disk_report`.
- [ ] `/ai matikan site contoh.com` → `disable_site`.
- [ ] Aksi tak dikenal → pesan jelas + saran `/help`, bukan "belum diimplementasi".
- [ ] Buat test mapping: loop semua entri `ACTION_ALIASES`, pastikan `getattr(module, target)` callable.

### Risiko
- Sedang. Mengubah jalur eksekusi inti. Mitigasi: test mapping otomatis (lihat checklist).

---

## FASE 2 — (B) Implementasi `backup.restore` (disaster recovery)

### Tujuan
Lengkapi fitur paling kritis untuk user awam: memulihkan dari backup. **Restore bersifat
destruktif → wajib lewat OTP confirmation flow.**

### File terdampak
- `modules/backup.py` (method `restore`, `restore_db`, `restore_files`, `_safe_backup_path`)
- `modules/telegram_bot.py` (command `/restore`, handler konfirmasi `restore`)
- `modules/brain.py` (SYSTEM_PROMPT: jelaskan `restore` perlu nama file & confirmation)

### Langkah

**2.1 — Validasi path aman di `backup.py`** (cegah path traversal):

```python
def _safe_backup_path(self, filename: str) -> str | None:
    """Pastikan filename berada di dalam backup_dir, tanpa traversal."""
    candidate = os.path.realpath(os.path.join(self.backup_dir, filename))
    base = os.path.realpath(self.backup_dir)
    if not candidate.startswith(base + os.sep):
        return None
    if not os.path.exists(candidate):
        return None
    return candidate
```

**2.2 — Method restore di `backup.py`:**

```python
async def restore_db(self, filename: str) -> str:
    """Restore database dari file backup .sql.gz. DESTRUKTIF."""
    path = self._safe_backup_path(f"db/{filename}") or self._safe_backup_path(filename)
    if not path:
        return f"❌ File backup tidak ditemukan / tidak valid: `{filename}`"
    r = await self.executor.run(
        f"gunzip -c {path} | mysql", module="backup", timeout=600,
    )
    if r["success"]:
        return f"✅ *Database berhasil dipulihkan* dari `{filename}`."
    return f"❌ Restore DB gagal:\n```\n{r['stderr'][:500]}\n```"

async def restore_files(self, filename: str) -> str:
    """Restore file situs dari tar.gz. Ekstrak ke / (path absolut di arsip)."""
    path = self._safe_backup_path(f"files/{filename}") or self._safe_backup_path(filename)
    if not path:
        return f"❌ File backup tidak ditemukan / tidak valid: `{filename}`"
    r = await self.executor.run(
        f"tar xzf {path} -C / 2>/dev/null", module="backup", timeout=600,
    )
    if r["success"]:
        return f"✅ *File situs berhasil dipulihkan* dari `{filename}`."
    return f"❌ Restore file gagal:\n```\n{r['stderr'][:500]}\n```"

async def restore(self, filename: str = "") -> str:
    """Entry-point restore untuk AI. Auto-detect tipe dari nama file."""
    if not filename:
        return ("ℹ️ Sebutkan file backup. Lihat daftar via `/backup list`, lalu:\n"
                "`/restore <nama_file>`")
    if filename.endswith(".sql.gz"):
        return await self.restore_db(filename)
    if filename.endswith(".tar.gz"):
        return await self.restore_files(filename)
    return "❌ Format backup tidak dikenal (harus `.sql.gz` atau `.tar.gz`)."
```

**2.3 — Command `/restore` di `telegram_bot.py`** dengan OTP:

```python
async def cmd_restore(self, update, context):
    if not await self._guard(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Penggunaan: `/restore <nama_file>`\nLihat daftar: `/backup list`",
            parse_mode="Markdown")
        return
    filename = args[0]
    otp = self._generate_otp()
    await update.message.reply_text(
        f"⚠️ *Konfirmasi Restore* (DESTRUKTIF!)\n\n"
        f"File: `{filename}`\n"
        f"Data saat ini akan ditimpa oleh isi backup.\n\n"
        f"Kirim `/confirm {otp}` atau balas `{otp}` untuk melanjutkan.",
        parse_mode="Markdown")
    self._pending_confirmations[self.admin_id] = {
        "action": "restore", "filename": filename, "otp": otp,
        "expires": datetime.now().timestamp() + 120,
    }
```

**2.4 — Handler di `_execute_confirmed_action`:**

```python
elif action == "restore":
    filename = pending["filename"]
    await update.message.reply_text(f"♻️ Memulihkan dari `{filename}`...", parse_mode="Markdown")
    result = await self.modules["backup"].restore(filename)
    await update.message.reply_text(result, parse_mode="Markdown")
```

**2.5** — Daftarkan `CommandHandler("restore", self.cmd_restore)` di `run()` + tambah ke
`set_my_commands` + `HELP_TEXT`.

**2.6** — Karena restore via `/ai` berbahaya, di SYSTEM_PROMPT set
`confirmation_needed=true` untuk intent restore, agar lewat OTP flow `action == "ai"`.

### Verifikasi Fase 2
- [ ] `/backup db` lalu `/restore <file.sql.gz>` → OTP → restore sukses (uji di VPS staging).
- [ ] `/restore ../../etc/passwd` → ditolak `_safe_backup_path`.
- [ ] `/ai pulihkan database` → `confirmation_needed` → OTP.

### Risiko
- Tinggi (destruktif). Mitigasi: WAJIB OTP, validasi path, uji hanya di staging dulu.

---

## FASE 3 — (C) Perbaiki fallback parser tanpa API key

### Tujuan
User tanpa `ANTHROPIC_API_KEY` (mayoritas target audiens) tetap mendapat bot fungsional.

### File terdampak
- `modules/brain.py` (`_fallback_parse`, [brain.py:209](modules/brain.py#L209))

### Langkah

**3.1** — Perbarui tabel `mappings` agar memakai action yang valid (sudah dijamin oleh
alias map Fase 1). Ganti action hantu:

```python
mappings = [
    (["status", "kesehatan", "health"], "monitor", "status", {}),        # -> get_status_report (alias)
    (["service", "layanan", "servis"], "monitor", "services", {}),       # -> get_services_status (alias)
    (["disk", "storage", "penyimpanan"], "monitor", "disk_usage", {}),   # -> get_disk_report (alias)
    (["proses", "process", "cpu tinggi"], "monitor", "top_processes", {}),
    (["koneksi", "connection", "network"], "monitor", "connections", {}),
    (["provision", "install lemp", "setup server"], "provisioner", "install_lemp", {}),
    (["firewall", "ufw"], "firewall", "status", {}),
    (["security", "keamanan", "audit"], "security", "audit", {}),
    (["site", "domain", "vhost"], "site_manager", "list_sites", {}),
    (["backup"], "backup", "backup_all", {}),
    (["restart nginx"], "executor", "service_restart", {"service": "nginx"}),
    (["restart mysql"], "executor", "service_restart", {"service": "mysql"}),
    (["restart php"], "executor", "service_restart", {"service": "php8.3-fpm"}),
    (["update", "upgrade"], "security", "check_updates", {}),
    (["log", "logs"], "monitor", "services", {}),  # fallback aman; /logs punya command sendiri
]
```

**3.2** — Pastikan keyword `log` tidak lagi ke `recent_logs` (hantu). Arahkan user ke
`/logs <service>` di pesan default `clarify`.

### Verifikasi Fase 3
- [ ] Jalankan dengan `ANTHROPIC_API_KEY` kosong.
- [ ] Ketik "cek disk", "status", "proses berat" → semua mengeksekusi method nyata.

### Risiko
- Rendah. Hanya mengubah pemetaan keyword.

---

## FASE 4 — (D) Terima konfirmasi "ya/ok" selain OTP

### Tujuan
User awam yang refleks membalas "ya" tidak gagal konfirmasi.

### File terdampak
- `modules/telegram_bot.py` (`handle_text` langkah 2, [telegram_bot.py:581-587](modules/telegram_bot.py#L581-L587))
- `CLAUDE.md` (samakan dokumentasi dengan perilaku)

### Keputusan Desain & Tradeoff Keamanan
Admin sudah terautentikasi (`_guard`). OTP berfungsi mencegah eksekusi **tak sengaja**, bukan
mencegah pihak tak berwenang. Balasan "ya" yang eksplisit = niat sengaja. Maka:
- **Aksi non-destruktif** (`ai` tanpa destruktif, `add_cron`, `optimize_system`): terima `ya/ok/yes/oke/lanjut/setuju` **atau** OTP.
- **Aksi destruktif** (`provision`, `remove_site`, `deny_ssh`, `change_ssh_port`, `restore`, `repair_service`): **tetap wajib OTP** (kata afirmatif tidak cukup).

### Langkah

**4.1** — Definisikan konstanta di atas class:

```python
AFFIRMATIVE_WORDS = {"ya", "iya", "ok", "oke", "yes", "y", "lanjut", "setuju", "gas"}
DESTRUCTIVE_ACTIONS = {"provision", "remove_site", "deny_ssh", "change_ssh_port",
                       "restore", "repair_service", "wizard_provision"}
```

**4.2** — Perbarui `handle_text` langkah 2:

```python
pending = self._pending_confirmations.get(self.admin_id)
if pending and pending["expires"] > datetime.now().timestamp():
    user_text = update.message.text.strip().lower()
    is_otp = user_text == pending.get("otp")
    is_affirmative = (
        user_text in AFFIRMATIVE_WORDS
        and pending["action"] not in DESTRUCTIVE_ACTIONS
    )
    if is_otp or is_affirmative:
        del self._pending_confirmations[self.admin_id]
        await self._execute_confirmed_action(update, pending)
        return
    # Jika aksi destruktif & user balas "ya": ingatkan butuh OTP
    if user_text in AFFIRMATIVE_WORDS:
        await update.message.reply_text(
            "🔐 Aksi ini berisiko. Mohon kirim *kode OTP* yang tertera untuk konfirmasi.",
            parse_mode="Markdown")
        return
```

**4.3** — Update `CLAUDE.md` bagian "Confirmation flow" agar akurat: ya/ok hanya untuk
aksi non-destruktif; destruktif tetap OTP.

### Verifikasi Fase 4
- [ ] `/optimize` → balas "ya" → tereksekusi.
- [ ] `/restore x` → balas "ya" → ditolak, diminta OTP.
- [ ] `/restore x` → kirim OTP → tereksekusi.

### Risiko
- Rendah–sedang. Mitigasi: destruktif tetap OTP-only.

---

## FASE 5 — (E) Suntik konteks STATE server ke AI

### Tujuan
AI memberi panduan benar ("provision dulu") alih-alih merutekan ke aksi yang pasti gagal.

### File terdampak
- `modules/monitor.py` (method `get_state_context` + cache)
- `modules/telegram_bot.py` (`cmd_ai` perkaya context, [telegram_bot.py:409-418](modules/telegram_bot.py#L409-L418))

### Langkah

**5.1** — Method state di `monitor.py` (dengan cache 60 dtk agar tak menambah latency):

```python
import time

async def get_state_context(self) -> str:
    """Ringkas state server untuk konteks AI (di-cache 60 detik)."""
    now = time.time()
    if getattr(self, "_state_cache", None) and now - self._state_cache_ts < 60:
        return self._state_cache

    async def installed(pkg):
        r = await self.executor.run(f"command -v {pkg} >/dev/null && echo yes || echo no",
                                    module="monitor", check=False)
        return r["stdout"].strip() == "yes"

    nginx = await installed("nginx")
    mysql = await installed("mysql")
    php = await installed("php")
    lemp = "TERPASANG" if (nginx and mysql and php) else "BELUM terpasang"

    # Daftar site dari DB
    sites = []
    try:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT domain, ssl_enabled FROM sites WHERE status='active'")
        sites = cur.fetchall(); conn.close()
    except Exception:
        pass
    site_str = ", ".join(f"{d}{'(SSL)' if s else ''}" for d, s in sites) or "belum ada"

    ctx = (
        f"LEMP stack: {lemp} (nginx={nginx}, mysql={mysql}, php={php}). "
        f"Site terkelola: {site_str}."
    )
    self._state_cache = ctx
    self._state_cache_ts = now
    return ctx
```

> Inisialisasi `self._state_cache = None; self._state_cache_ts = 0` di `__init__`.

**5.2** — Di `cmd_ai`, gabungkan metrics + state:

```python
metrics = await self.modules["monitor"].collect_metrics()
state = await self.modules["monitor"].get_state_context()
context_str = (
    f"CPU: {metrics['cpu_percent']}%, RAM: {metrics['ram_percent']}%, "
    f"Disk: {metrics['disk_percent']}%, Load: {metrics['load_1']}, "
    f"Uptime: {metrics['uptime_str']}\n{state}"
)
```

**5.3** — Tambah instruksi di SYSTEM_PROMPT: "Jika user minta tambah site tapi LEMP BELUM
terpasang, JANGAN rutekan ke add_site; set action=clarify dan sarankan `/provision` dulu."

### Verifikasi Fase 5
- [ ] Di server tanpa LEMP, `/ai tambah site x.com` → AI menyarankan provision dulu (action=clarify).
- [ ] Cache: dua `/ai` berturut < 60 dtk tidak menjalankan ulang `command -v`.

### Risiko
- Rendah. Tambahan read-only + cache.

---

## FASE 6 — (F) Terjemahkan error mentah jadi bahasa manusia

### Tujuan
Saat gagal, user awam dapat penjelasan & langkah, bukan dump stderr.

### File terdampak
- `modules/brain.py` (method baru `explain_error`)
- `modules/site_manager.py`, `modules/provisioner.py` (jalur kegagalan kunci)
- `modules/telegram_bot.py` (helper `_humanize` opsional)

### Langkah

**6.1** — Method baru di `brain.py`:

```python
async def explain_error(self, operation: str, stderr: str) -> str:
    """Ubah pesan error teknis jadi penjelasan ramah-pemula + langkah perbaikan."""
    if not self.enabled:
        return ""  # fallback: pemanggil tetap tampilkan stderr mentah
    try:
        client = self._get_client()
        response = await client.messages.create(
            model=_AI_MODEL, max_tokens=512,
            system=("Kamu SyamAdmin. Jelaskan error sysadmin berikut dalam bahasa "
                    "Indonesia sederhana untuk pemula: apa artinya & 1-2 langkah perbaikan. "
                    "Singkat, tanpa jargon."),
            messages=[{"role": "user",
                       "content": f"Operasi: {operation}\nError:\n```\n{stderr[:1500]}\n```"}],
        )
        self.last_error = None
        self._log_usage(f"explain_error: {operation}", response)
        return response.content[0].text.strip()
    except Exception as e:
        self.last_error = str(e)
        return ""
```

**6.2** — Pola pemakaian di jalur gagal (contoh `enable_ssl` [site_manager.py:228](modules/site_manager.py#L228)).
Karena `SiteManager` belum punya `brain`, dua opsi:
- **Opsi A (disarankan):** lakukan humanize di layer bot. Method modul tetap kembalikan
  raw; di `cmd_*`/`_execute_confirmed_action`, jika hasil mengandung "❌ ... gagal", panggil
  `brain.explain_error` lalu lampirkan.
- **Opsi B:** inject `brain` ke konstruktor modul terkait.

Implementasi Opsi A — helper di `telegram_bot.py`:

```python
async def _augment_failure(self, operation: str, text: str) -> str:
    """Jika `text` indikasi kegagalan, tambahkan penjelasan AI ramah-pemula."""
    if "❌" not in text and "gagal" not in text.lower():
        return text
    brain = self.modules.get("brain")
    if not (brain and brain.enabled):
        return text
    explanation = await brain.explain_error(operation, text)
    if explanation:
        return f"{text}\n\n🧠 *Penjelasan:*\n{explanation}"
    return text
```

Lalu bungkus pemanggilan kunci, mis. di `cmd_site` (ssl) & `wizard_provision`:

```python
result = await sm.enable_ssl(domain)
result = await self._augment_failure("aktivasi SSL", result)
await update.message.reply_text(result, parse_mode="Markdown")
```

**6.3** — Terapkan pada minimal: `enable_ssl`, `add_site`, `install_package`,
`repair_service` (jika gagal), `install_lemp` (ringkasan gagal).

### Verifikasi Fase 6
- [ ] Picu SSL gagal (domain belum diarahkan) → muncul blok "🧠 Penjelasan" berbahasa awam.
- [ ] Tanpa API key → tetap tampilkan error mentah (tidak crash).

### Risiko
- Rendah. Menambah biaya token kecil hanya saat gagal.

---

## FASE 7 — (G) Onboarding & Hardening Wizard

### Tujuan
Beri "jalur bahagia" terpandu untuk langkah pertama (provision → harden → firewall → site),
meniru pola `cmd_site_wizard` yang sudah baik.

### File terdampak
- `modules/telegram_bot.py` (command `/setup`, state machine onboarding)
- `modules/monitor.py` (pakai `get_state_context` dari Fase 5 untuk deteksi langkah)
- `HELP_TEXT`, `cmd_start` (arahkan ke `/setup`)

### Langkah

**7.1** — `cmd_start` tawarkan onboarding bila server "kosong":

```python
state = await self.modules["monitor"].get_state_context()
if "BELUM terpasang" in state:
    # tambahkan ajakan: "Server baru? Ketik /setup untuk panduan langkah demi langkah."
```

**7.2** — Command `/setup` — wizard berbasis deteksi state (idempoten, aman diulang):

```python
async def cmd_setup(self, update, context):
    if not await self._guard(update):
        return
    self._wizard_states[self.admin_id] = {
        "state": "SETUP_MENU",
        "expires": datetime.now().timestamp() + 600,
    }
    await update.message.reply_text(
        "🧭 *Panduan Setup Server (Pemula)*\n\n"
        "Saya akan bantu langkah demi langkah:\n"
        "1️⃣ Pasang LEMP (web server)\n"
        "2️⃣ Amankan server (hardening + firewall)\n"
        "3️⃣ Buat website pertama\n\n"
        "Ketik nomor langkah (`1`/`2`/`3`) atau `selesai`.",
        parse_mode="Markdown")
```

**7.3** — Tangani state `SETUP_MENU` di `handle_text` (tambahkan cabang baru sebelum
blok wizard situs, atau gabung dalam mesin state yang sama):

```python
if state == "SETUP_MENU":
    choice = user_text.strip()
    if choice == "1":
        # arahkan ke flow provision existing (pakai OTP)
        del self._wizard_states[self.admin_id]
        await self.cmd_provision(update, context); return
    elif choice == "2":
        del self._wizard_states[self.admin_id]
        otp = self._generate_otp()
        self._pending_confirmations[self.admin_id] = {
            "action": "harden_all", "otp": otp,
            "expires": datetime.now().timestamp() + 120}
        await update.message.reply_text(
            f"🔐 Akan menjalankan hardening SSH + Fail2Ban + Firewall + Auto-update.\n"
            f"Kirim `/confirm {otp}` atau balas `{otp}`.", parse_mode="Markdown")
        return
    elif choice == "3":
        self._wizard_states[self.admin_id] = {
            "state": "DOMAIN", "expires": datetime.now().timestamp() + 600}
        await update.message.reply_text("👉 Masukkan nama domain (mis. `contoh.com`):")
        return
    elif choice in ("selesai", "done"):
        del self._wizard_states[self.admin_id]
        await update.message.reply_text("✅ Panduan ditutup. Ketik `/help` kapan saja.")
        return
```

**7.4** — Tambah handler `harden_all` di `_execute_confirmed_action` (gabungkan langkah
yang sudah ada di `cmd_harden`):

```python
elif action == "harden_all":
    await update.message.reply_text("🔐 Menjalankan hardening menyeluruh...")
    r1 = await self.modules["security"].harden_ssh()
    r2 = await self.modules["security"].setup_fail2ban()
    r3 = await self.modules["firewall"].setup_defaults()
    r4 = await self.modules["security"].setup_auto_updates()
    summary = f"🔐 *Hardening Selesai*\n\n{r1}\n\n{r2}\n\n{r3}\n\n{r4}"
    await update.message.reply_text(summary[:4000], parse_mode="Markdown")
```

**7.5** — Daftarkan `CommandHandler("setup", self.cmd_setup)` + masukkan ke
`set_my_commands` & `HELP_TEXT`.

### Verifikasi Fase 7
- [ ] `/setup` → pilih `1` → masuk flow provision (OTP).
- [ ] `/setup` → pilih `2` → hardening menyeluruh (OTP).
- [ ] `/setup` → pilih `3` → lanjut ke wizard domain existing.
- [ ] Timeout 10 menit (reuse mekanisme Fase 4 sebelumnya / wizard timeout).

### Risiko
- Sedang (banyak menyentuh `handle_text`). Mitigasi: reuse flow & handler yang sudah ada,
  jangan duplikasi logika provision/harden.

---

## Strategi Testing Menyeluruh

1. **Static check** tiap file yang diubah:
   `python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" <file>`
2. **Test mapping aksi (Fase 1)** — script kecil: untuk setiap `(modul, alias)` di
   `ACTION_ALIASES`, assert method target ada & callable.
3. **Uji lokal (macOS)** — modul yang tak butuh root (brain fallback, alias resolution,
   konfirmasi ya/ok, state context dengan command -v) bisa diuji tanpa VPS.
4. **Uji staging VPS** — WAJIB untuk Fase 2 (restore) & Fase 7 (provision/harden) karena
   destruktif/butuh systemd. Gunakan snapshot VPS sebelum tes restore.
5. **Regression** — pastikan command lama (`/status`, `/site add`, `/backup`) tetap jalan.

## Rencana Rollback

- Tiap fase = commit terpisah → `git revert <commit>` aman per fase.
- Fase 2 & 7 (destruktif): uji hanya di VPS staging bersnapshot sebelum merge ke `main`.
- Simpan `config.env` & DB di-backup sebelum uji restore.

## Checklist Eksekusi

- [ ] **Fase 1 (A)** — Action registry + method tipis + sync prompt
- [ ] **Fase 2 (B)** — backup.restore + `/restore` + OTP
- [ ] **Fase 3 (C)** — fallback parser pakai action valid
- [ ] **Fase 4 (D)** — terima ya/ok (non-destruktif) + update CLAUDE.md
- [ ] **Fase 5 (E)** — get_state_context + inject ke cmd_ai + prompt
- [ ] **Fase 6 (F)** — brain.explain_error + _augment_failure di jalur gagal
- [ ] **Fase 7 (G)** — /setup onboarding + harden_all
- [ ] Test mapping aksi lulus
- [ ] Regression command lama lulus
- [ ] Uji restore & provision di staging
- [ ] Update README.md & USER_GUIDE.md (perintah `/restore`, `/setup`)

---

_Dokumen rencana — belum ada kode yang diubah. Implementasi mengikuti urutan fase di atas._
