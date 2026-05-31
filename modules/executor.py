"""
CommandExecutor — Safe shell execution with audit logging.
Every command executed by SyamAdmin is logged and sandboxed.
"""

import asyncio
import logging
import sqlite3
import shlex
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("syamadmin.executor")

# Commands that are NEVER allowed regardless of context
BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs.",
    "> /dev/sda",
    "dd if=/dev/zero of=/dev/sd",
    ":(){:|:&};:",  # fork bomb
    "chmod -R 777 /",
    "curl | bash",   # piped execution from internet
    "wget | bash",
]


class CommandExecutor:
    """Execute shell commands safely with audit trail."""

    def __init__(self, db_path: str = "/var/lib/syamadmin/syamadmin.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    module TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT,
                    user_id TEXT,
                    status TEXT DEFAULT 'success'
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"DB init warning: {e}")

    def _is_blocked(self, command: str) -> bool:
        cmd_lower = command.lower().strip()
        for pattern in BLOCKED_PATTERNS:
            if pattern in cmd_lower:
                return True
        return False

    async def run(
        self,
        command: str,
        module: str = "system",
        timeout: int = 120,
        user_id: str = "agent",
        check: bool = True,
    ) -> dict:
        """
        Execute a shell command asynchronously.

        Returns dict with keys: success, stdout, stderr, returncode, duration
        """
        if self._is_blocked(command):
            msg = f"BLOCKED dangerous command: {command[:100]}"
            logger.critical(msg)
            self.audit_log(module, "BLOCKED", msg, user_id, "blocked")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command blocked by safety filter: {command[:50]}...",
                "returncode": -1,
                "duration": 0,
            }

        logger.debug(f"[{module}] Executing: {command[:200]}")
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            duration = round(time.time() - start, 2)

            result = {
                "success": proc.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="replace").strip(),
                "stderr": stderr.decode("utf-8", errors="replace").strip(),
                "returncode": proc.returncode,
                "duration": duration,
            }

            status = "success" if result["success"] else "failed"
            self.audit_log(
                module,
                command[:200],
                f"rc={proc.returncode} dur={duration}s",
                user_id,
                status,
            )

            if not result["success"] and check:
                logger.warning(
                    f"[{module}] Command failed (rc={proc.returncode}): "
                    f"{command[:100]} — {result['stderr'][:200]}"
                )

            return result

        except asyncio.TimeoutError:
            duration = round(time.time() - start, 2)
            msg = f"Command timed out after {timeout}s: {command[:100]}"
            logger.error(f"[{module}] {msg}")
            self.audit_log(module, command[:200], msg, user_id, "timeout")
            return {
                "success": False,
                "stdout": "",
                "stderr": msg,
                "returncode": -2,
                "duration": duration,
            }
        except Exception as e:
            duration = round(time.time() - start, 2)
            msg = f"Execution error: {e}"
            logger.error(f"[{module}] {msg}")
            self.audit_log(module, command[:200], msg, user_id, "error")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -3,
                "duration": duration,
            }

    def audit_log(
        self,
        module: str,
        action: str,
        detail: str = "",
        user_id: str = "agent",
        status: str = "success",
    ):
        """Write to audit log database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO audit_log (module, action, detail, user_id, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (module, action[:500], detail[:1000], user_id, status),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Audit log write failed: {e}")

    async def run_script(
        self, script_path: str, module: str = "script", timeout: int = 300
    ) -> dict:
        """Execute a shell script file."""
        return await self.run(
            f"bash {shlex.quote(script_path)}", module=module, timeout=timeout
        )

    async def service_action(
        self, service: str, action: str = "status"
    ) -> dict:
        """Manage systemd service."""
        allowed_actions = ["start", "stop", "restart", "reload", "status", "enable", "disable"]
        if action not in allowed_actions:
            return {"success": False, "stderr": f"Invalid action: {action}"}
        return await self.run(
            f"systemctl {action} {shlex.quote(service)}",
            module="service",
        )

    async def get_recent_audit(self, limit: int = 20) -> list:
        """Get recent audit log entries."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                "SELECT timestamp, module, action, status FROM audit_log "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
            return [
                {"timestamp": r[0], "module": r[1], "action": r[2], "status": r[3]}
                for r in rows
            ]
        except Exception:
            return []
