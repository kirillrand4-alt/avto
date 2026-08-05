# -*- coding: utf-8 -*-
"""Сверка: какой ящик через какой SMTP шлёт, есть ли DKIM у домена отправки и
покрывает ли SPF обоих провайдеров. Пароли не читаем и не печатаем."""
import json
import re
import subprocess

CFG = r'C:\sender\sender.yaml'
OUT = {}


def ns(name, typ='TXT'):
    try:
        p = subprocess.run(['nslookup', f'-type={typ}', name], capture_output=True,
                           text=True, timeout=25, encoding='cp866', errors='replace')
        txt = (p.stdout or '') + (p.stderr or '')
        return [ln.strip() for ln in txt.splitlines() if 'text =' in ln or '"' in ln][:6]
    except Exception as e:  # noqa: BLE001
        return [f'ERR {e}']


def main():
    raw = open(CFG, encoding='utf-8', errors='replace').read()
    # ящики: id + smtp_host в пределах блока
    boxes = []
    cur = None
    for ln in raw.splitlines():
        m = re.match(r'^\s*-?\s*(?:id|mailbox_id)\s*:\s*"?([\w.\-@]+@[\w.\-]+)"?', ln)
        if m:
            if cur:
                boxes.append(cur)
            cur = {'ящик': m.group(1), 'smtp': None, 'imap': None}
            continue
        if cur is not None:
            m2 = re.match(r'^\s*smtp_host\s*:\s*"?([\w.\-]+)"?', ln)
            if m2:
                cur['smtp'] = m2.group(1)
            m3 = re.match(r'^\s*imap_host\s*:\s*"?([\w.\-]+)"?', ln)
            if m3:
                cur['imap'] = m3.group(1)
    if cur:
        boxes.append(cur)
    OUT['ящики'] = boxes

    doms = sorted({b['ящик'].split('@')[1] for b in boxes if b.get('ящик')})
    OUT['домены'] = {}
    for d in doms:
        rec = {'spf': ns(d, 'TXT'), 'dmarc': ns(f'_dmarc.{d}', 'TXT'), 'dkim': {}}
        for sel in ('mailru', 'mail', 'yandex', 'default', 'dkim', 'selector1', 'selector2', 's1', 'mx'):
            r = ns(f'{sel}._domainkey.{d}', 'TXT')
            if any('DKIM1' in x or 'p=MIG' in x or 'k=rsa' in x for x in r):
                rec['dkim'][sel] = [x[:120] for x in r][:3]
        OUT['домены'][d] = rec
    print(json.dumps(OUT, ensure_ascii=False))


if __name__ == '__main__':
    main()
