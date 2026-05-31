"""
SiteManager — Nginx vhost and SSL certificate management.
"""

import logging
import os
import sqlite3

logger = logging.getLogger("syamadmin.site_manager")

VHOST_TEMPLATE_IPV4_ONLY = """server {{
    listen 80;
    server_name {domain} www.{domain};
    root {root_path};
    index index.php index.html;

    # Logging
    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # PHP-FPM
    location ~ \\.php$ {{
        fastcgi_pass unix:/run/php/php{php_version}-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
    }}

    # Static assets caching
    location ~* \\.(jpg|jpeg|png|gif|ico|css|js|svg|woff2?)$ {{
        expires 30d;
        add_header Cache-Control "public, immutable";
    }}

    # Deny hidden files
    location ~ /\\. {{
        deny all;
    }}

    # Laravel / general PHP framework support
    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}
}}
"""

VHOST_TEMPLATE_WITH_IPV6 = """server {{
    listen 80;
    listen [::]:80;
    server_name {domain} www.{domain};
    root {root_path};
    index index.php index.html;

    # Logging
    access_log /var/log/nginx/{domain}.access.log;
    error_log /var/log/nginx/{domain}.error.log;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # PHP-FPM
    location ~ \\.php$ {{
        fastcgi_pass unix:/run/php/php{php_version}-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
    }}

    # Static assets caching
    location ~* \\.(jpg|jpeg|png|gif|ico|css|js|svg|woff2?)$ {{
        expires 30d;
        add_header Cache-Control "public, immutable";
    }}

    # Deny hidden files
    location ~ /\\. {{
        deny all;
    }}

    # Laravel / general PHP framework support
    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}
}}
"""


class SiteManager:
    """Manage Nginx virtual hosts and SSL."""

    def __init__(self, executor, notifier, db_path: str):
        self.executor = executor
        self.notifier = notifier
        self.db_path = db_path
        self.php_version = os.environ.get("PHP_VERSION", "8.3")
        self.web_root_base = "/var/www"
        self._ensure_db()

    def _ensure_db(self):
        """Pastikan tabel sites ada — mandiri, tak bergantung pada install.sh."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT UNIQUE NOT NULL,
                    root_path TEXT NOT NULL,
                    php_version TEXT DEFAULT '8.3',
                    ssl_enabled INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"SiteManager DB init warning: {e}")

    async def _check_ipv6_support(self) -> bool:
        """Cek apakah kernel support IPv6 (aman di VPS minimal/container).

        Return: True jika safe gunakan listen [::], False jika IPv4-only.
        """
        # Cek sysctl disable flag
        r = await self.executor.run(
            "sysctl net.ipv6.conf.all.disable_ipv6 2>/dev/null || echo 'error'",
            module="site_manager", check=False,
        )
        if "disable_ipv6 = 1" in r["stdout"]:
            logger.warning(f"IPv6 disabled (sysctl) — gunakan IPv4-only untuk {self.db_path}")
            return False
        if "error" in r["stdout"]:
            logger.warning("Cannot determine IPv6 status — fallback IPv4-only (safest untuk clean VPS)")
            return False

        # Cek ada inet6 address (non-loopback)
        r = await self.executor.run(
            "ip addr | grep inet6 | grep -v 'fe80:' | wc -l",
            module="site_manager", check=False,
        )
        count = int(r["stdout"].strip() or 0)
        if count > 0:
            logger.info("IPv6 support OK")
            return True

        logger.warning("No IPv6 addresses detected — IPv4-only Nginx config")
        return False

    async def add_site(self, domain: str, root_path: str = "", framework: str = "default") -> str:
        """Add a new Nginx vhost for a domain."""
        if not root_path:
            if framework == "laravel":
                root_path = f"{self.web_root_base}/{domain}/public"
            else:
                root_path = f"{self.web_root_base}/{domain}/public_html"

        actual_dir = root_path if framework != "laravel" else f"{self.web_root_base}/{domain}"

        await self.notifier.send(f"🌐 *Adding site:* `{domain}`...")

        # Create web directory
        r = await self.executor.run(
            f"mkdir -p {root_path} && "
            f"chown -R www-data:www-data {actual_dir} && "
            f"chmod -R 755 {actual_dir}",
            module="site_manager",
        )
        if not r["success"]:
            return f"❌ Gagal membuat direktori: {r['stderr'][:300]}"

        # Create default index
        await self.executor.run(
            f"echo '<h1>Welcome to {domain}</h1><p>Managed by SyamAdmin</p>' > {root_path}/index.html",
            module="site_manager",
        )

        # Deteksi IPv6 support untuk memilih template yang tepat
        ipv6_ok = await self._check_ipv6_support()
        template = VHOST_TEMPLATE_WITH_IPV6 if ipv6_ok else VHOST_TEMPLATE_IPV4_ONLY

        # Generate vhost config
        vhost = template.format(
            domain=domain,
            root_path=root_path,
            php_version=self.php_version,
        )

        config_path = f"/etc/nginx/sites-available/{domain}"
        escaped = vhost.replace("'", "'\\''")
        await self.executor.run(
            f"echo '{escaped}' > {config_path}",
            module="site_manager",
        )

        # Enable site
        await self.executor.run(
            f"ln -sf {config_path} /etc/nginx/sites-enabled/{domain}",
            module="site_manager",
        )

        # Test and reload
        test = await self.executor.run("nginx -t", module="site_manager")
        if not test["success"]:
            # Rollback
            await self.executor.run(
                f"rm -f /etc/nginx/sites-enabled/{domain} {config_path}",
                module="site_manager",
            )
            return f"❌ Nginx config invalid, rollback dilakukan:\n```\n{test['stderr'][:500]}\n```"

        await self.executor.run("systemctl reload nginx", module="site_manager")

        # Save to database
        self._save_site(domain, root_path)

        # Create PHP-FPM pool (optional per-site pool)
        await self._create_php_pool(domain)

        msg = (
            f"✅ *Site `{domain}` berhasil ditambahkan!*\n\n"
            f"📁 Root: `{root_path}`\n"
            f"🐘 PHP: `{self.php_version}`\n"
            f"📝 Config: `{config_path}`\n\n"
            f"Selanjutnya:\n"
            f"• `/site ssl {domain}` — aktifkan SSL\n"
            f"• Upload file ke `{root_path}`"
        )
        await self.notifier.send(msg)
        return msg

    async def remove_site(self, domain: str) -> str:
        """Remove a site's Nginx configuration."""
        await self.executor.run(
            f"rm -f /etc/nginx/sites-enabled/{domain} && "
            f"rm -f /etc/nginx/sites-available/{domain}",
            module="site_manager",
        )
        await self.executor.run("systemctl reload nginx", module="site_manager")

        # Update database
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE sites SET status='removed' WHERE domain=?", (domain,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return f"✅ Site `{domain}` dihapus dari Nginx.\n_(Direktori web tidak dihapus untuk keamanan)_"

    async def list_sites(self) -> str:
        """List all managed sites."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                "SELECT domain, root_path, ssl_enabled, status, created_at "
                "FROM sites ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []

        if not rows:
            # Fallback: check nginx configs
            r = await self.executor.run(
                "ls -1 /etc/nginx/sites-enabled/ 2>/dev/null | grep -v default",
                module="site_manager", check=False,
            )
            if r["stdout"]:
                return f"🌐 *Active Sites (dari Nginx):*\n```\n{r['stdout']}\n```"
            return "📭 Belum ada site yang dikelola."

        lines = ["🌐 *Managed Sites*\n"]
        for domain, root, ssl, status, created in rows:
            ssl_icon = "🔒" if ssl else "🔓"
            status_icon = "🟢" if status == "active" else "⚫"
            lines.append(f"{status_icon} {ssl_icon} `{domain}`")
            lines.append(f"   📁 {root}")

        return "\n".join(lines)

    async def enable_ssl(self, domain: str) -> str:
        """Enable SSL via Let's Encrypt Certbot."""
        await self.notifier.send(f"🔒 *Enabling SSL for `{domain}`...*")

        r = await self.executor.run(
            f"certbot --nginx -d {domain} -d www.{domain} "
            f"--non-interactive --agree-tos --redirect "
            f"--email admin@{domain} 2>&1",
            module="site_manager", timeout=120,
        )

        if r["success"] or "congratulations" in r["stdout"].lower():
            # Update database
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("UPDATE sites SET ssl_enabled=1 WHERE domain=?", (domain,))
                conn.commit()
                conn.close()
            except Exception:
                pass

            # Setup auto-renewal cron
            await self.executor.run(
                "systemctl enable --now certbot.timer 2>/dev/null || "
                "(crontab -l 2>/dev/null; echo '0 3 * * * certbot renew --quiet') | sort -u | crontab -",
                module="site_manager",
            )

            msg = (
                f"✅ *SSL aktif untuk `{domain}`!*\n"
                f"• Certificate: Let's Encrypt\n"
                f"• Auto-renewal: enabled\n"
                f"• HTTP → HTTPS redirect: active"
            )
        else:
            msg = f"❌ SSL setup gagal:\n```\n{r['stderr'][:500]}\n```\n\n_Pastikan domain sudah mengarah ke IP server ini._"

        await self.notifier.send(msg)
        return msg

    async def _create_php_pool(self, domain: str):
        """Create a per-site PHP-FPM pool for isolation."""
        pool_name = domain.replace(".", "_")
        pool_config = f"""[{pool_name}]
user = www-data
group = www-data
listen = /run/php/php{self.php_version}-fpm-{pool_name}.sock
listen.owner = www-data
listen.group = www-data
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 4
pm.max_requests = 500
"""
        escaped = pool_config.replace("'", "'\\''")
        await self.executor.run(
            f"echo '{escaped}' > /etc/php/{self.php_version}/fpm/pool.d/{pool_name}.conf",
            module="site_manager",
        )

    def _save_site(self, domain: str, root_path: str):
        """Save site info to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO sites (domain, root_path, php_version) VALUES (?, ?, ?)",
                (domain, root_path, self.php_version),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to save site to DB: {e}")

    async def disable_site(self, domain: str) -> str:
        """Nonaktifkan site tanpa menghapus config (bisa diaktifkan kembali)."""
        await self.executor.run(
            f"rm -f /etc/nginx/sites-enabled/{domain}",
            module="site_manager",
        )
        test = await self.executor.run("nginx -t", module="site_manager", check=False)
        if test["success"]:
            await self.executor.run("systemctl reload nginx", module="site_manager")
            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    "UPDATE sites SET status='disabled' WHERE domain=?", (domain,)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return f"⏸️ Site `{domain}` dinonaktifkan (config tetap tersimpan)."
        return f"❌ Gagal menonaktifkan `{domain}`:\n```\n{test['stderr'][:300]}\n```"
