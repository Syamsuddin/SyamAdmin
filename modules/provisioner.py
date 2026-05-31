"""
Provisioner — LEMP stack setup from clean Ubuntu 22.04 install.
Installs and configures Nginx, MySQL 8, PHP 8.3, Composer, Certbot.
"""

import logging
import os
import secrets
import string

logger = logging.getLogger("syamadmin.provisioner")


class Provisioner:
    """Provision a complete LEMP stack."""

    def __init__(self, executor, notifier):
        self.executor = executor
        self.notifier = notifier
        self.php_version = os.environ.get("PHP_VERSION", "8.3")

    def _generate_password(self, length: int = 24) -> str:
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return "".join(secrets.choice(chars) for _ in range(length))

    async def _detect_ipv6_support(self) -> bool:
        """Deteksi apakah kernel support IPv6 (tidak akan fail di VPS tanpa IPv6).

        Return: True jika IPv6 available (aman gunakan listen [::]), False jika tidak.
        """
        # Test 1: cek sysctl disable flag
        r = await self.executor.run(
            "sysctl net.ipv6.conf.all.disable_ipv6 2>/dev/null || echo 'error'",
            module="provisioner", check=False,
        )
        if "disable_ipv6 = 1" in r["stdout"]:
            logger.warning("IPv6 disabled via sysctl")
            return False
        if "error" in r["stdout"]:
            logger.warning("Could not check sysctl IPv6 — assuming not supported (VPS minimal)")
            return False

        # Test 2: cek apakah inet6 address ada (fallback jika sysctl gagal)
        r = await self.executor.run(
            "ip addr | grep inet6 | grep -v 'fe80:' | wc -l",
            module="provisioner", check=False,
        )
        ipv6_count = int(r["stdout"].strip() or 0)
        if ipv6_count > 0:
            logger.info("IPv6 support detected")
            return True

        logger.warning("No IPv6 addresses found — disabling IPv6 in Nginx")
        return False

    async def install_lemp(self) -> str:
        """Full LEMP stack installation."""
        await self.notifier.send("🚀 *Memulai instalasi LEMP stack...*")
        results = []

        # Step 1: System update
        await self.notifier.send("📦 [1/7] Updating system packages...")
        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get update -qq && "
            "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq",
            module="provisioner", timeout=300,
        )
        results.append(("System Update", r["success"]))

        # Step 2: Install Nginx
        await self.notifier.send("🌐 [2/7] Installing Nginx...")
        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx",
            module="provisioner", timeout=120,
        )
        if r["success"]:
            # Optimize Nginx config
            await self._configure_nginx()
        results.append(("Nginx", r["success"]))

        # Step 3: Install MySQL 8
        await self.notifier.send("🗄 [3/7] Installing MySQL 8...")
        mysql_pass = self._generate_password()
        r = await self._install_mysql(mysql_pass)
        results.append(("MySQL 8", r))

        # Step 4: Install PHP
        await self.notifier.send(f"🐘 [4/7] Installing PHP {self.php_version}...")
        r = await self._install_php()
        results.append((f"PHP {self.php_version}", r))

        # Step 5: Install Composer
        await self.notifier.send("🎼 [5/7] Installing Composer...")
        composer_result = await self.setup_composer()
        results.append(("Composer", "✅" in composer_result))

        # Step 6: Install Certbot
        await self.notifier.send("🔒 [6/7] Installing Certbot...")
        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx",
            module="provisioner", timeout=120,
        )
        results.append(("Certbot", r["success"]))

        # Step 7: Setup swap if needed
        await self.notifier.send("💾 [7/7] Configuring swap...")
        r = await self._setup_swap()
        results.append(("Swap", r))

        # Enable services
        await self.executor.run("systemctl enable --now nginx", module="provisioner")
        await self.executor.run("systemctl enable --now mysql", module="provisioner")
        await self.executor.run(f"systemctl enable --now php{self.php_version}-fpm", module="provisioner")

        # Report
        report = self._format_report(results, mysql_pass)
        await self.notifier.send(report)
        return report

    async def _configure_nginx(self):
        """Apply optimized Nginx configuration."""
        nginx_conf = """
# SyamAdmin Nginx Optimization
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 30;
    types_hash_max_size 2048;
    server_tokens off;
    client_max_body_size 64M;

    # Gzip
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 4;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript image/svg+xml;

    # Security headers (default, overridden per vhost)
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log warn;

    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
"""
        await self.executor.run(
            f"cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak",
            module="provisioner",
        )
        # Write config
        escaped = nginx_conf.replace("'", "'\\''")
        await self.executor.run(
            f"echo '{escaped}' > /etc/nginx/nginx.conf",
            module="provisioner",
        )
        await self.executor.run("nginx -t", module="provisioner")
        await self.executor.run("systemctl reload nginx", module="provisioner")

    async def _install_mysql(self, password: str) -> bool:
        """Install and secure MySQL 8."""
        r = await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server",
            module="provisioner", timeout=180,
        )
        if not r["success"]:
            return False

        # Secure installation
        secure_cmds = f"""
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '{password}';"
mysql -u root -p'{password}' -e "DELETE FROM mysql.user WHERE User='';"
mysql -u root -p'{password}' -e "DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');"
mysql -u root -p'{password}' -e "DROP DATABASE IF EXISTS test;"
mysql -u root -p'{password}' -e "FLUSH PRIVILEGES;"
"""
        r = await self.executor.run(secure_cmds, module="provisioner", timeout=60)

        # Store password securely
        await self.executor.run(
            f"echo 'MYSQL_ROOT_PASSWORD={password}' >> /etc/syamadmin/config.env && "
            f"chmod 600 /etc/syamadmin/config.env",
            module="provisioner",
        )

        # Create .my.cnf for root
        await self.executor.run(
            f"printf '[client]\\nuser=root\\npassword={password}\\n' > /root/.my.cnf && "
            f"chmod 600 /root/.my.cnf",
            module="provisioner",
        )

        return True

    async def _install_php(self) -> bool:
        """Install PHP with common extensions."""
        v = self.php_version

        # Add ondrej/php PPA if needed
        await self.executor.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq software-properties-common && "
            "add-apt-repository -y ppa:ondrej/php && "
            "apt-get update -qq",
            module="provisioner", timeout=120,
        )

        extensions = [
            f"php{v}-fpm", f"php{v}-mysql", f"php{v}-mbstring",
            f"php{v}-xml", f"php{v}-curl", f"php{v}-gd",
            f"php{v}-zip", f"php{v}-intl", f"php{v}-bcmath",
            f"php{v}-redis", f"php{v}-opcache", f"php{v}-cli",
            f"php{v}-common", f"php{v}-tokenizer",
        ]

        r = await self.executor.run(
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {' '.join(extensions)}",
            module="provisioner", timeout=180,
        )

        if r["success"]:
            # Optimize PHP-FPM
            await self.executor.run(
                f"sed -i 's/upload_max_filesize = .*/upload_max_filesize = 64M/' /etc/php/{v}/fpm/php.ini && "
                f"sed -i 's/post_max_size = .*/post_max_size = 64M/' /etc/php/{v}/fpm/php.ini && "
                f"sed -i 's/memory_limit = .*/memory_limit = 256M/' /etc/php/{v}/fpm/php.ini && "
                f"sed -i 's/max_execution_time = .*/max_execution_time = 60/' /etc/php/{v}/fpm/php.ini && "
                f"systemctl restart php{v}-fpm",
                module="provisioner",
            )

        return r["success"]

    async def _setup_swap(self) -> bool:
        """Setup swap file if not exists."""
        check = await self.executor.run("swapon --show | wc -l", module="provisioner")
        if check["stdout"].strip() != "0":
            logger.info("Swap already exists, skipping.")
            return True

        # Create 2GB swap
        r = await self.executor.run(
            "fallocate -l 2G /swapfile && "
            "chmod 600 /swapfile && "
            "mkswap /swapfile && "
            "swapon /swapfile && "
            "echo '/swapfile none swap sw 0 0' >> /etc/fstab && "
            "sysctl vm.swappiness=10 && "
            "echo 'vm.swappiness=10' >> /etc/sysctl.conf",
            module="provisioner", timeout=60,
        )
        return r["success"]

    async def install_package(self, package: str) -> str:
        """Install a specific apt package."""
        r = await self.executor.run(
            f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {package}",
            module="provisioner", timeout=120,
        )
        if r["success"]:
            return f"✅ Package `{package}` berhasil diinstall."
        return f"❌ Gagal install `{package}`:\n```\n{r['stderr'][:500]}\n```"

    async def setup_composer(self) -> str:
        """Install Composer terpisah (bisa dipanggil mandiri via AI)."""
        r = await self.executor.run(
            "curl -sS https://getcomposer.org/installer | php -- "
            "--install-dir=/usr/local/bin --filename=composer",
            module="provisioner", timeout=60,
        )
        if r["success"]:
            return "✅ Composer berhasil diinstall."
        return f"❌ Gagal install Composer:\n```\n{r['stderr'][:300]}\n```"

    def _format_report(self, results: list, mysql_pass: str) -> str:
        """Format installation report."""
        lines = ["✅ *LEMP Stack Installation Complete*\n"]
        all_ok = True
        for name, success in results:
            icon = "✅" if success else "❌"
            lines.append(f"{icon} {name}")
            if not success:
                all_ok = False

        lines.append(f"\n🔑 *MySQL root password:*")
        lines.append(f"`{mysql_pass}`")
        lines.append(f"_(disimpan di /etc/syamadmin/config.env)_")

        if all_ok:
            lines.append(f"\n🎉 Server siap untuk hosting!")
            lines.append(f"Gunakan `/site add domain.com` untuk menambah site.")
        else:
            lines.append(f"\n⚠️ Beberapa komponen gagal. Cek log untuk detail.")

        return "\n".join(lines)
