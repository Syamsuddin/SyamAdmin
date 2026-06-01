"""
Updater — self-update SyamAdmin dari GitHub.

Mesin: tarball (tanpa git di VPS). Eksekusi: detached self-healing script
(`scripts/update.sh`) yang melakukan backup → unduh tarball → ganti file →
restart service → health-check → auto-rollback bila gagal.

Bot hanya: (1) cek versi remote vs lokal, (2) memicu skrip terlepas. Penggantian
file dirinya sendiri TIDAK boleh dilakukan in-process (service di-restart di
tengah jalan) — karena itu logika berat didelegasikan ke skrip detached.
"""

import logging
import os
import re
import shlex
from pathlib import Path

logger = logging.getLogger("syamadmin.updater")


class Updater:
    def __init__(self, executor, config: dict = None, install_dir: str = "/opt/syamadmin"):
        self.executor = executor
        self.config = config or {}
        self.install_dir = self.config.get("INSTALL_DIR", install_dir)
        self.repo = self.config.get("GITHUB_REPO", "Syamsuddin/SyamAdmin")
        self.branch = self.config.get("UPDATE_BRANCH", "main")
        self.service = self.config.get("SERVICE_NAME", "syamadmin")
        self.log_file = self.config.get("UPDATE_LOG", "/var/log/syamadmin/update.log")

    # ------------------------------------------------------------------
    # VERSI
    # ------------------------------------------------------------------

    def get_local_version(self) -> str:
        """Baca VERSION dari install_dir, fallback ke root paket (mode dev)."""
        candidates = [
            self.install_dir,
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ]
        for base in candidates:
            try:
                p = Path(base) / "VERSION"
                if p.is_file():
                    v = p.read_text(encoding="utf-8").strip()
                    if v:
                        return v
            except Exception:
                continue
        return "0.0.0"

    async def get_remote_version(self) -> str:
        """Ambil VERSION dari branch GitHub via raw.githubusercontent (tanpa git)."""
        url = f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/VERSION"
        r = await self.executor.run(
            f"curl -fsSL --max-time 10 {shlex.quote(url)}",
            module="updater", check=False, timeout=20,
        )
        return (r.get("stdout") or "").strip().splitlines()[0].strip() if r.get("stdout") else ""

    @staticmethod
    def _parse(v: str) -> tuple:
        nums = re.findall(r"\d+", v or "")
        return tuple(int(n) for n in nums[:3]) if nums else (0,)

    def is_newer(self, remote: str, local: str) -> bool:
        return self._parse(remote) > self._parse(local)

    async def check(self) -> dict:
        """Bandingkan versi lokal vs remote."""
        local = self.get_local_version()
        remote = await self.get_remote_version()
        if not remote:
            return {"ok": False, "local": local, "remote": "",
                    "update_available": False,
                    "error": "tidak bisa mengambil versi remote (cek koneksi/repo)"}
        return {
            "ok": True, "local": local, "remote": remote,
            "update_available": self.is_newer(remote, local),
        }

    # ------------------------------------------------------------------
    # EKSEKUSI (detached)
    # ------------------------------------------------------------------

    def _script_path(self) -> str:
        for base in (self.install_dir,
                     os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
            p = os.path.join(base, "scripts", "update.sh")
            if os.path.isfile(p):
                return p
        return os.path.join(self.install_dir, "scripts", "update.sh")

    async def trigger_update(self) -> dict:
        """
        Picu update.sh secara TERLEPAS (setsid+nohup) agar tetap berjalan
        meski service syamadmin di-restart di tengah proses.
        """
        script = self._script_path()
        if not os.path.isfile(script):
            return {"ok": False, "error": f"script update tidak ditemukan: {script}"}

        cmd = (
            f"setsid nohup bash {shlex.quote(script)} "
            f"--repo {shlex.quote(self.repo)} "
            f"--branch {shlex.quote(self.branch)} "
            f"--dir {shlex.quote(self.install_dir)} "
            f"--service {shlex.quote(self.service)} "
            f">> {shlex.quote(self.log_file)} 2>&1 &"
        )
        r = await self.executor.run(cmd, module="updater", check=False, timeout=15)
        return {"ok": bool(r.get("success")), "log": self.log_file,
                "error": "" if r.get("success") else (r.get("stderr") or "gagal memicu updater")}
