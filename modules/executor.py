"""
CommandExecutor — Safe shell execution with audit logging.
Every command executed by SyamAdmin is logged and sandboxed.
"""

import asyncio
import logging
import os
import sqlite3
import shlex
import re
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("syamadmin.executor")

# Regex pattern-based blacklist for dangerous shell commands
BLOCKED_PATTERNS_REGEX = [
    # rm -rf / or sensitive system directories (handling multiple spaces, optional quotes, and slashes/quotes at boundaries)
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[^\s]*\s+(?:/|/etc|/var|/opt|/boot|/root|/usr|/bin|/sbin|/sys|/proc|/dev)(?:\s|['\"/]|$)",
    # Disk formatting
    r"\bmkfs(?:\.[a-zA-Z0-9]+)?\b",
    # Raw overwrite/redirection to disks
    r"\bdd\s+.*\bof=/dev/sd",
    r">\s*/dev/sd",
    # Large scale permissions reset on root/system folders
    r"\bchmod\s+-[a-z]*r[a-z]*\s+777\s+(?:/|/etc|/var|/usr|/opt|/boot|/root)(?:\s|['\"/]|$)",
    # Piped curl/wget download-and-execute shell triggers
    r"(?:curl|wget)\s+.*\|\s*(?:bash|sh)\b",
    # Any general execution redirection using pipes
    r"\|\s*(?:bash|sh)\b",
    # Base64 or general decoding piped directly to a shell execution
    r"\bbase64\s+-(?:d|-decode)\b.*\b(?:sh|bash)\b",
    r"\bopenssl\s+.*\b(?:sh|bash)\b",
    # Classic Fork Bomb
    r":\(\)\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
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
        cmd_clean = command.strip()
        cmd_lower = cmd_clean.lower()

        # 1. Check regex-based blacklist patterns (handles spacing, quotes, and decoding bypasses)
        for pattern in BLOCKED_PATTERNS_REGEX:
            if re.search(pattern, cmd_lower):
                logger.warning(f"Safety filter: command blocked by regex rule '{pattern}'")
                return True

        # 2. Check shlex-tokenized command structure to capture command injection / malicious sequences
        try:
            tokens = shlex.split(cmd_clean)
            if tokens:
                # Check for direct dangerous commands inside any command sequences
                for i, token in enumerate(tokens):
                    # Strict check on destructive rm calls
                    if token == "rm":
                        # Traverse forward to check if a recursive force flag is used on critical paths
                        has_rf = False
                        targets_root = False
                        for t in tokens[i+1:]:
                            if t.startswith("-") and "r" in t and "f" in t:
                                has_rf = True
                            if t in ("/", "/etc", "/var", "/opt", "/boot", "/root", "/usr"):
                                targets_root = True
                        if has_rf and targets_root:
                            logger.warning("Safety filter: tokenized block on recursive forced removal on system root paths")
                            return True

                    # Block direct execution of shells or raw interpreters
                    if token in ("/bin/sh", "/bin/bash", "sh", "bash") and i > 0:
                        # Piped/linked execution is dangerous
                        if tokens[i-1] in ("|", "&&", ";", "||"):
                            logger.warning("Safety filter: tokenized block on chained shell interpreter execution")
                            return True

                    # Inspect nested interpreter commands (e.g., bash -c "rm -rf /") recursively
                    if token in ("sh", "bash") and len(tokens) > i + 1:
                        for j in range(i + 1, len(tokens)):
                            if tokens[j] != "-c" and not tokens[j].startswith("-"):
                                # Check if nested argument matches a block
                                if self._is_blocked(tokens[j]):
                                    logger.warning(f"Safety filter: tokenized block on nested execution argument: {tokens[j]}")
                                    return True
        except ValueError as e:
            # shlex parsing error (e.g. unclosed quote), could be a shell injection attempt
            logger.warning(f"Safety filter: blocking due to shlex parse error (potential injection): {e}")
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

    async def run_exec(
        self,
        program: str,
        args: list,
        module: str = "system",
        timeout: int = 120,
        user_id: str = "agent",
        check: bool = True,
    ) -> dict:
        """
        Execute a shell command via raw arguments asynchronously (no shell processing).
        This method is immune to command injection.
        """
        # Block check on reconstructed command string representation for auditing
        full_command_repr = f"{program} " + " ".join(shlex.quote(a) for a in args)
        if self._is_blocked(full_command_repr):
            msg = f"BLOCKED dangerous exec command: {full_command_repr[:100]}"
            logger.critical(msg)
            self.audit_log(module, "BLOCKED_EXEC", msg, user_id, "blocked")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command blocked by safety filter: {program}...",
                "returncode": -1,
                "duration": 0,
            }

        logger.debug(f"[{module}] Executing Program: {program} with args: {args}")
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_exec(
                program,
                *args,
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
                full_command_repr[:200],
                f"rc={proc.returncode} dur={duration}s",
                user_id,
                status,
            )

            if not result["success"] and check:
                logger.warning(
                    f"[{module}] Exec failed (rc={proc.returncode}): "
                    f"{program} — {result['stderr'][:200]}"
                )

            return result

        except asyncio.TimeoutError:
            duration = round(time.time() - start, 2)
            msg = f"Exec command timed out after {timeout}s: {program}"
            logger.error(f"[{module}] {msg}")
            self.audit_log(module, full_command_repr[:200], msg, user_id, "timeout")
            return {
                "success": False,
                "stdout": "",
                "stderr": msg,
                "returncode": -2,
                "duration": duration,
            }
        except Exception as e:
            duration = round(time.time() - start, 2)
            msg = f"Exec execution error: {e}"
            logger.error(f"[{module}] {msg}")
            self.audit_log(module, full_command_repr[:200], msg, user_id, "error")
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
        """Execute a shell script file safely via run_exec."""
        return await self.run_exec(
            "bash", [script_path], module=module, timeout=timeout
        )

    async def service_action(
        self, service: str, action: str = "status"
    ) -> dict:
        """Manage systemd service safely via run_exec."""
        allowed_actions = ["start", "stop", "restart", "reload", "status", "enable", "disable"]
        if action not in allowed_actions:
            return {"success": False, "stderr": f"Invalid action: {action}"}
        return await self.run_exec(
            "systemctl",
            [action, service],
            module="service",
        )

    async def add_cron_job(self, cron_expr: str, action_cmd: str) -> dict:
        """Securely write a dynamic cron job to crontab."""
        py_path = "/opt/syamadmin/venv/bin/python3"
        if not os.path.exists(py_path):
            py_path = "python3"
            
        script_path = "/opt/syamadmin/scripts/cron_job.py"
        cron_entry = f"{cron_expr} {py_path} {script_path} {action_cmd} >/dev/null 2>&1"
        
        # Read current crontab
        res_read = await self.run("crontab -l", module="cron", check=False)
        current_cron = res_read["stdout"].strip()
        
        # Handle 'no crontab' fallback
        if "no crontab for" in res_read["stderr"].lower() or res_read["returncode"] != 0:
            current_cron = ""
            
        lines = current_cron.splitlines() if current_cron else []
        
        # Deduplicate
        new_lines = []
        for line in lines:
            if f"cron_job.py {action_cmd}" not in line and line.strip():
                new_lines.append(line)
                
        new_lines.append(cron_entry)
        new_cron_str = "\n".join(new_lines) + "\n"
        
        # Write safely via temp file
        import tempfile
        fd, temp_path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, 'w') as tmp:
                tmp.write(new_cron_str)
                
            res_write = await self.run(f"crontab {temp_path}", module="cron")
            return res_write
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

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
