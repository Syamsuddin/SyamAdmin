"""
Notifier — Telegram notification engine.
Sends alerts, reports, and status updates to the admin.
"""

import asyncio
import logging
from datetime import datetime
import httpx

logger = logging.getLogger("syamadmin.notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class Notifier:
    """Send messages to Telegram admin."""

    def __init__(self, bot_token: str, admin_id: int):
        self.bot_token = bot_token
        self.admin_id = admin_id
        self.api_url = TELEGRAM_API.format(token=bot_token)
        self._client: httpx.AsyncClient | None = None
        self._rate_limit = asyncio.Semaphore(5)  # max 5 concurrent sends
        self._last_alert: dict[str, datetime] = {}
        self._alert_cooldown = 300  # 5 minutes between same alerts

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def send(
        self,
        text: str,
        chat_id: int | None = None,
        parse_mode: str = "Markdown",
        silent: bool = False,
    ) -> bool:
        """Send a text message via Telegram."""
        target = chat_id or self.admin_id
        async with self._rate_limit:
            try:
                client = await self._get_client()
                resp = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": target,
                        "text": text[:4096],  # Telegram limit
                        "parse_mode": parse_mode,
                        "disable_notification": silent,
                    },
                )
                if resp.status_code == 200:
                    return True
                else:
                    logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
                    return False
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                return False

    async def alert(
        self,
        severity: str,
        module: str,
        message: str,
        cooldown: bool = True,
    ) -> bool:
        """
        Send an alert with deduplication cooldown.
        severity: critical, warning, info
        """
        alert_key = f"{module}:{message[:50]}"

        if cooldown and alert_key in self._last_alert:
            elapsed = (datetime.now() - self._last_alert[alert_key]).total_seconds()
            if elapsed < self._alert_cooldown:
                logger.debug(f"Alert suppressed (cooldown): {alert_key}")
                return False

        icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        icon = icons.get(severity, "⚪")

        text = (
            f"{icon} *Alert — {severity.upper()}*\n"
            f"Module: `{module}`\n"
            f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
            f"{message}"
        )

        sent = await self.send(text)
        if sent:
            self._last_alert[alert_key] = datetime.now()
        return sent

    async def send_report(self, title: str, sections: list[dict]) -> bool:
        """
        Send a formatted report.
        sections: [{"title": "...", "content": "..."}, ...]
        """
        lines = [f"📊 *{title}*", f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"]
        for section in sections:
            lines.append(f"*{section['title']}*")
            lines.append(section["content"])
            lines.append("")

        return await self.send("\n".join(lines))

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
