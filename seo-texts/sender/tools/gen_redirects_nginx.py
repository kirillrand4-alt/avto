#!/usr/bin/env python3
"""Генератор nginx-конфига 301-редиректов доменов-двойников из config/domains.json.

Вариант «свой редиректор»: A-записи всех доменов из реестра → IP своего сервера,
на сервере nginx отдаёт 301 на целевой сайт (https, с сохранением пути) и ACME
webroot для выпуска Let's Encrypt. MX/SPF/DKIM это не трогает — почта живёт своей
жизнью, редирект касается только веба (A-записей).

Запуск: python3 sender/tools/gen_redirects_nginx.py > sender/deploy/redirects-nginx.conf
Печатает конфиг в stdout; certbot-команда — в шапке конфига.
"""

import json
import os
import sys

REGISTRY = os.path.join(os.path.dirname(__file__), "..", "config", "domains.json")
ACME_ROOT = "/var/www/acme"


def main() -> int:
    with open(REGISTRY, encoding="utf-8") as f:
        entries = json.load(f)["domains"]

    domains = [e["domain"] for e in entries]
    all_names = []
    for d in domains:
        all_names += [d, f"www.{d}"]
    certbot = ("certbot certonly --webroot -w " + ACME_ROOT + " \\\n#   "
               + " \\\n#   ".join(f"-d {n}" for n in all_names))
    first = domains[0]

    out = sys.stdout
    out.write(f"""# Сгенерировано tools/gen_redirects_nginx.py из config/domains.json — руками не править.
# 301-редиректы доменов-двойников на основные сайты (КЦ/Meyer).
#
# Порядок ввода:
# 1. A-записи всех доменов (и www) из реестра → IP этого сервера. MX не трогать!
# 2. mkdir -p {ACME_ROOT} && положить этот файл в /etc/nginx/conf.d/redirects.conf
#    (секцию server 443 ниже СНАЧАЛА закомментировать), nginx -t && systemctl reload nginx
# 3. Выпустить один мультидоменный сертификат:
# {certbot}
# 4. Раскомментировать server 443, nginx -t && systemctl reload nginx.
# 5. Продление: certbot renew --deploy-hook "systemctl reload nginx" (таймер ставится сам).
# 6. Проверка: python3 sender/tools/check_domains.py — колонка редиректов должна позеленеть.

map $host $redirect_target {{
    default prokompressor.ru;
""")
    for e in entries:
        d = e["domain"].replace(".", "\\.")
        out.write(f"    ~^(www\\.)?{d}$ {e['redirect']};\n")
    out.write(f"""}}

server {{
    listen 80;
    listen [::]:80;
    server_name {" ".join(all_names)};

    location /.well-known/acme-challenge/ {{
        root {ACME_ROOT};
    }}
    location / {{
        return 301 https://$redirect_target$request_uri;
    }}
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {" ".join(all_names)};

    ssl_certificate     /etc/letsencrypt/live/{first}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{first}/privkey.pem;

    return 301 https://$redirect_target$request_uri;
}}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
