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
