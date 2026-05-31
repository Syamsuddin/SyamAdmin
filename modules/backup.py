"""
BackupManager — Automated backup for databases and files.
"""

import logging
import os
from datetime import datetime

logger = logging.getLogger("syamadmin.backup")


class BackupManager:
    """Database and file backup management."""

    def __init__(self, executor, notifier, backup_dir: str = "/var/backups/syamadmin"):
        self.executor = executor
        self.notifier = notifier
        self.backup_dir = backup_dir
        self.retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", 7))

    async def _ensure_dir(self):
        await self.executor.run(f"mkdir -p {self.backup_dir}/db {self.backup_dir}/files", module="backup")

    async def backup_db(self) -> str:
        """Backup all MySQL databases."""
        await self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.backup_dir}/db/all_databases_{ts}.sql.gz"

        await self.notifier.send("💾 *Backing up databases...*")

        r = await self.executor.run(
            f"mysqldump --all-databases --single-transaction --routines --triggers "
            f"--default-character-set=utf8mb4 2>/dev/null | gzip > {filename}",
            module="backup", timeout=300,
        )

        if r["success"]:
            size = await self.executor.run(f"du -h {filename} | cut -f1", module="backup")
            msg = f"✅ *Database backup selesai*\n📁 `{filename}`\n📦 Size: `{size['stdout'].strip()}`"
        else:
            msg = f"❌ Database backup gagal:\n```\n{r['stderr'][:500]}\n```"

        await self.notifier.send(msg)
        return msg

    async def backup_files(self, paths: list[str] | None = None) -> str:
        """Backup web files."""
        await self._ensure_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not paths:
            paths = ["/var/www", "/etc/nginx", f"/etc/php"]

        filename = f"{self.backup_dir}/files/webfiles_{ts}.tar.gz"
        path_str = " ".join(paths)

        await self.notifier.send("📦 *Backing up files...*")

        r = await self.executor.run(
            f"tar czf {filename} {path_str} 2>/dev/null",
            module="backup", timeout=600,
        )

        if r["success"]:
            size = await self.executor.run(f"du -h {filename} | cut -f1", module="backup")
            msg = f"✅ *File backup selesai*\n📁 `{filename}`\n📦 Size: `{size['stdout'].strip()}`"
        else:
            msg = f"❌ File backup gagal:\n```\n{r['stderr'][:500]}\n```"

        await self.notifier.send(msg)
        return msg

    async def backup_all(self) -> str:
        """Full backup: databases + files."""
        await self.notifier.send("🔄 *Starting full backup...*")
        db_result = await self.backup_db()
        file_result = await self.backup_files()
        await self._cleanup_old()
        return f"{db_result}\n\n{file_result}"

    async def list_backups(self) -> str:
        """List all available backups."""
        r = await self.executor.run(
            f"find {self.backup_dir} -type f \\( -name '*.gz' -o -name '*.tar.gz' \\) "
            f"-printf '%T@ %s %p\\n' 2>/dev/null | sort -rn | head -20 | "
            f"awk '{{cmd=\"date -d @\"int($1)\" +\\\"%Y-%m-%d %H:%M\\\"\"; cmd | getline d; close(cmd); "
            f"printf \"%s  %6.1fMB  %s\\n\", d, $2/1048576, $3}}'",
            module="backup", check=False,
        )

        if r["stdout"]:
            return f"📋 *Available Backups*\n```\n{r['stdout'][:3000]}\n```"
        return "📭 Belum ada backup."

    async def _cleanup_old(self):
        """Remove backups older than retention period."""
        r = await self.executor.run(
            f"find {self.backup_dir} -type f -mtime +{self.retention_days} -delete -print",
            module="backup",
        )
        if r["stdout"]:
            count = len(r["stdout"].strip().split("\n"))
            logger.info(f"Cleaned up {count} old backup files.")

    def _safe_backup_path(self, filename: str):
        """Pastikan filename berada di dalam backup_dir, tanpa traversal."""
        candidate = os.path.realpath(os.path.join(self.backup_dir, filename))
        base = os.path.realpath(self.backup_dir)
        if not candidate.startswith(base + os.sep):
            return None
        if not os.path.exists(candidate):
            return None
        return candidate

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
