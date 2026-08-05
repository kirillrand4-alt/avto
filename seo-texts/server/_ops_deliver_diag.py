# -*- coding: utf-8 -*-
"""Диагностика доставляемости: DNS отправляющего домена, репутация IP, живые
HTTP-эндпоинты трекинга/отписки. Только чтение, пароли не печатаем."""
import json
import re
import socket
import subprocess

OUT = {}
CFG = r'C:\sender\sender.yaml'


def ns(name, typ='TXT'):
    try:
        p = subprocess.run(['nslookup', f'-type={typ}', name], capture_output=True,
                           text=True, timeout=25, encoding='cp866', errors='replace')
        txt = (p.stdout or '') + (p.stderr or '')
        return [ln.strip() for ln in txt.splitlines()
                if ln.strip() and not ln.strip().startswith(('Server', 'Address:', 'Сервер', 'Address'))][:12]
    except Exception as e:  # noqa: BLE001
        return [f'ERR {e}']


def main():
    raw = open(CFG, encoding='utf-8', errors='replace').read()
    # конфиг: только безопасные ключи
    safe = []
    for ln in raw.splitlines():
        if re.search(r'^\s*(host|port|smtp_host|smtp_port|selector|dkim|username|user)\s*:', ln):
            if 'pass' in ln.lower() or 'secret' in ln.lower():
                continue
            safe.append(ln.strip()[:90])
    OUT['конфиг_smtp'] = safe[:20]

    hosts = sorted({m.group(1) for m in re.finditer(r'^\s*(?:smtp_)?host\s*:\s*"?([\w.\-]+)"?', raw, re.M)})
    OUT['smtp_хосты'] = hosts
    OUT['ip_хостов'] = {}
    for h in hosts:
        try:
            OUT['ip_хостов'][h] = sorted({a[4][0] for a in socket.getaddrinfo(h, None)})
        except Exception as e:  # noqa: BLE001
            OUT['ип_хостов'] = OUT.get('ип_хостов', {})
            OUT['ip_хостов'][h] = [f'ERR {e}']

    dom = 'compressor-store.ru'
    OUT['spf'] = ns(dom, 'TXT')
    OUT['dmarc'] = ns(f'_dmarc.{dom}', 'TXT')
    OUT['mx'] = ns(dom, 'MX')
    for sel in ('mail', 'default', 'selector1', 'dkim', 's1'):
        r = ns(f'{sel}._domainkey.{dom}', 'TXT')
        if any('v=DKIM1' in x or 'p=' in x for x in r):
            OUT.setdefault('dkim_селекторы', {})[sel] = r[:4]

    # трекинг/отписка: жив ли домен и эндпоинты
    for h in ('parsercompressor.online', 'mail.parsercompressor.online'):
        try:
            OUT.setdefault('трекинг_dns', {})[h] = socket.gethostbyname(h)
        except Exception as e:  # noqa: BLE001
            OUT.setdefault('трекинг_dns', {})[h] = f'нет A ({e})'

    # DNSBL по внешнему IP отправки
    ips = sorted({ip for lst in OUT['ip_хостов'].values() for ip in lst if re.match(r'^\d+\.', str(ip))})
    OUT['dnsbl'] = {}
    for ip in ips[:3]:
        rev = '.'.join(reversed(ip.split('.')))
        for bl in ('zen.spamhaus.org', 'bl.spamcop.net', 'b.barracudacentral.org', 'dnsbl.sorbs.net'):
            try:
                res = socket.gethostbyname(f'{rev}.{bl}')
                OUT['dnsbl'][f'{ip}@{bl}'] = f'В СПИСКЕ → {res}'
            except Exception:  # noqa: BLE001
                OUT['dnsbl'][f'{ip}@{bl}'] = 'чисто'
    print(json.dumps(OUT, ensure_ascii=False))


if __name__ == '__main__':
    main()
