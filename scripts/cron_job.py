#!/usr/bin/env python3
"""
SyamAdmin — Automated Cron Job Runner
Loads settings, runs requested actions asynchronously, and alerts on failure.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can load modules from workspace
sys.path.insert(0, "/opt/syamadmin")

from modules.executor import CommandExecutor
from modules.notifier import Notifier
from modules.backup import BackupManager
from modules.security import SecurityManager

async def main():
    if len(sys.argv) < 2:
        print("Usage: cron_job.py <action>")
        sys.exit(1)

    action = sys.argv[1]
    
    # Load configuration
    CONFIG_PATH = os.environ.get("CONFIG_PATH", "/etc/syamadmin/config.env")
    if Path(CONFIG_PATH).exists():
        load_dotenv(CONFIG_PATH, override=True)
    else:
        # Fallback local load for testing
        load_dotenv(Path(__file__).parent.parent / "config.env", override=True)

    db_path = os.environ.get("DB_PATH", "/var/lib/syamadmin/syamadmin.db")
    
    executor = CommandExecutor(db_path=db_path)
    notifier = Notifier(
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_id=int(os.environ["TELEGRAM_ADMIN_ID"]),
    )

    try:
        if action == "backup_all":
            bm = BackupManager(executor=executor, notifier=notifier, backup_dir=os.environ.get("BACKUP_DIR", "/var/backups/syamadmin"))
            result = await bm.backup_all()
            await notifier.send(f"📅 *Jadwal Otomatis Berhasil*\n\n{result}")
        elif action == "backup_db":
            bm = BackupManager(executor=executor, notifier=notifier, backup_dir=os.environ.get("BACKUP_DIR", "/var/backups/syamadmin"))
            result = await bm.backup_db()
            await notifier.send(f"📅 *Jadwal Otomatis Berhasil*\n\n{result}")
        elif action == "backup_files":
            bm = BackupManager(executor=executor, notifier=notifier, backup_dir=os.environ.get("BACKUP_DIR", "/var/backups/syamadmin"))
            result = await bm.backup_files()
            await notifier.send(f"📅 *Jadwal Otomatis Berhasil*\n\n{result}")
        elif action == "security_audit":
            sm = SecurityManager(executor=executor, notifier=notifier)
            result = await sm.audit()
            await notifier.send(f"📅 *Jadwal Otomatis Berhasil*\n\n{result}")
        elif action == "rkhunter_scan":
            sm = SecurityManager(executor=executor, notifier=notifier)
            result = await sm.scan_rootkit()
            await notifier.send(f"📅 *Jadwal Otomatis Berhasil*\n\n{result}")
        else:
            print(f"Unknown action: {action}")
            sys.exit(1)
    except Exception as e:
        await notifier.send(f"⚠️ *Jadwal Otomatis Gagal*: Aksi `{action}` gagal!\nError: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
