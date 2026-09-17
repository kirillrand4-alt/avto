# -*- coding: utf-8 -*-
"""Разведка investprojects.info: что открыто без входа, что за паролем, почём.

Только чтение публичных страниц. Никакого обхода авторизации: задача — понять,
что видно снаружи и сколько стоит доступ, чтобы владелец решал по фактам.
"""
import json
import re
import ssl
import urllib.error
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}


def взять(url, лимит=400000, tmo=40):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        сырое = r.read(лимит)
        return r.getcode(), r.geturl(), сырое
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read(500) or b'')
    except Exception as e:
        return -1, url, repr(e)[:110].encode()


def плоско(html):
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))


# 1. robots.txt — что владелец сайта просит не трогать.
код, _, тело = взять('https://investprojects.info/robots.txt', 20000)
o['robots'] = {'код': код, 'текст': тело.decode('utf-8', 'replace')[:700]}

# 2. Витрина базы проектов.
код, финал, тело = взять('https://investprojects.info/project-base')
html = тело.decode('utf-8', 'replace')
ч = плоско(html)
o['витрина'] = {
    'код': код, 'финальный_url': финал, 'байт': len(html),
    'просит_войти': bool(re.search(r'войти|вход|регистрац|подписк|тариф', ч, re.I)),
    'ссылок_на_карточки': len(set(re.findall(r'/project[s]?[/\-][\w\-]{3,60}', html))),
    'примеры_ссылок': sorted(set(re.findall(r'/project[s]?[/\-][\w\-]{3,60}', html)))[:8],
    'текст': ч[:600],
}

# 3. Есть ли API за витриной (как было у ЕГРЗ).
адреса = set()
for м in re.findall(r'["\'](/api/[a-zA-Z0-9/_\-]{2,60})["\']', html):
    адреса.add(м)
for м in re.findall(r'["\'](https?://[a-z0-9.\-]*investprojects[^"\']{0,60})["\']', html):
    адреса.add(м)
o['похоже_на_api'] = sorted(адреса)[:15]

# 4. Цена доступа.
for путь in ('/tariffs', '/price', '/subscription', '/podpiska', '/tarify'):
    код, финал, тело = взять('https://investprojects.info' + путь, 200000)
    if код == 200:
        ч2 = плоско(тело.decode('utf-8', 'replace'))
        цены = re.findall(r'\d[\d\s]{2,9}\s*(?:₽|руб)', ч2)[:8]
        o.setdefault('тарифы', {})[путь] = {'код': код, 'цены': цены, 'текст': ч2[:400]}
        break
    o.setdefault('тарифы', {})[путь] = {'код': код}

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5200])
