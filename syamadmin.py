#!/usr/bin/env python3
"""
SyamAdmin — AI-Powered Sysadmin Agent
Main daemon entry point.
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load config
CONFIG_PATH = os.environ.get("CONFIG_PATH", "/etc/syamadmin/config.env")
if Path(CONFIG_PATH).exists():
    load_dotenv(CONFIG_PATH)

# Setup logging
LOG_FILE = os.environ.get("LOG_FILE", "/var/log/syamadmin/agent.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="a") if Path(LOG_FILE).parent.exists() else logging.StreamHandler(),
    ],
)
logger = logging.getLogger("syamadmin")


def validate_config():
    """Validate required environment variables."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_ID"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.error(f"Missing required config: {', '.join(missing)}")
        logger.error(f"Edit {CONFIG_PATH} dan set variabel yang dibutuhkan.")
        sys.exit(1)


async def main():
    """Main async entry point."""
    logger.info("=" * 50)
    logger.info("🤖 SyamAdmin Agent starting...")
    logger.info("=" * 50)

    validate_config()

    # Import modules after config is loaded
    from modules.telegram_bot import SyamAdminBot
    from modules.monitor import SystemMonitor
    from modules.notifier import Notifier
    from modules.executor import CommandExecutor
    from modules.brain import AIBrain
    from modules.provisioner import Provisioner
    from modules.security import SecurityManager
    from modules.firewall import FirewallManager
    from modules.site_manager import SiteManager
    from modules.backup import BackupManager

    db_path = os.environ.get("DB_PATH", "/var/lib/syamadmin/syamadmin.db")

    # Initialize modules
    executor = CommandExecutor(db_path=db_path)
    notifier = Notifier(
        bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_id=int(os.environ["TELEGRAM_ADMIN_ID"]),
    )
    brain = AIBrain(api_key=os.environ.get("ANTHROPIC_API_KEY", ""), db_path=db_path)
    monitor = SystemMonitor(
        notifier=notifier,
        executor=executor,
        db_path=db_path,
        interval=int(os.environ.get("MONITOR_INTERVAL", 60)),
        thresholds={
            "cpu": float(os.environ.get("ALERT_THRESHOLD_CPU", 85)),
            "ram": float(os.environ.get("ALERT_THRESHOLD_RAM", 90)),
            "disk": float(os.environ.get("ALERT_THRESHOLD_DISK", 85)),
            "load": float(os.environ.get("ALERT_THRESHOLD_LOAD", 4.0)),
        },
        brain=brain,
    )
    provisioner = Provisioner(executor=executor, notifier=notifier)
    security = SecurityManager(executor=executor, notifier=notifier)
    firewall = FirewallManager(executor=executor, notifier=notifier)
    site_manager = SiteManager(
        executor=executor, notifier=notifier, db_path=db_path
    )
    backup_manager = BackupManager(
        executor=executor,
        notifier=notifier,
        backup_dir=os.environ.get("BACKUP_DIR", "/var/backups/syamadmin"),
    )

    # Module registry for the AI brain and bot
    modules = {
        "monitor": monitor,
        "provisioner": provisioner,
        "security": security,
        "firewall": firewall,
        "site_manager": site_manager,
        "backup": backup_manager,
        "brain": brain,
        "executor": executor,
        "notifier": notifier,
    }

    # Initialize Telegram bot
    bot = SyamAdminBot(
        token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_id=int(os.environ["TELEGRAM_ADMIN_ID"]),
        modules=modules,
        server_name=os.environ.get("SERVER_NAME", "VPS"),
    )

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def handle_signal(sig):
        logger.info(f"Received signal {sig.name}, shutting down...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    # Start background tasks
    monitor_task = asyncio.create_task(monitor.run_loop())
    bot_task = asyncio.create_task(bot.run())

    logger.info("🟢 SyamAdmin Agent is running!")

    # Send startup notification
    try:
        await notifier.send(
            f"🟢 *SyamAdmin Agent Started*\n"
            f"Server: `{os.environ.get('SERVER_NAME', 'VPS')}`\n"
            f"Status: Online & Ready"
        )
    except Exception as e:
        logger.warning(f"Failed to send startup notification: {e}")

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cleanup
    logger.info("Shutting down tasks...")
    monitor_task.cancel()
    bot_task.cancel()

    try:
        await asyncio.gather(monitor_task, bot_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    await notifier.send("🔴 *SyamAdmin Agent Stopped*")
    logger.info("SyamAdmin Agent stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
