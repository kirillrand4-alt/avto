# -*- coding: utf-8 -*-
"""Жив ли реестр ФРП по адресу /clientage/ и что в историях успеха. Плюс счёт по RSS."""
import io
import json
import os
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


def взять(url, лимит=None):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=45)
        тело = r.read(лимит) if лимит else r.read()
        return r.getcode(), r.geturl(), тело.decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, url, (e.read(300) or b'').decode('utf-8', 'replace')
    except Exception as e:
        return -1, url, repr(e)[:120]


проверки = {}
for u in ('https://frprf.ru/clientage/',
          'https://frprf.ru/clientage/detail.php?ID=162',
          'https://frprf.ru/content/detail.php?ID=129',
          'https://frprf.ru/klienty/42484/',
          'https://frprf.ru/istorii-uspekha/',
          'https://frprf.ru/istorii-uspekha/157538/'):
    код, финал, т = взять(u, 200000)
    текст = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', т, flags=re.S)
    чистый = re.sub(r'<[^>]+>', ' ', текст)
    чистый = re.sub(r'\s+', ' ', чистый).strip()
    проверки[u] = {
        'код': код,
        'редирект_на': финал if финал.rstrip('/') != u.rstrip('/') else '',
        'байт': len(т),
        'есть_сумма_займа': bool(re.search(r'сумма займа|заём ФРП|млн руб', чистый, re.I)),
        'есть_ИНН': bool(re.search(r'\bИНН\b', чистый)),
        'текст': чистый[:300],
    }
o['проверки'] = проверки

# Счёт по сегодняшнему прогону лент — печатаем последним, чтобы не срезалось.
ГРАНИЦА = 5224
по_колл, с_инн = {}, 0
строк = 0
with io.open(r'C:\sender\server\news_stream.jsonl', encoding='utf-8', errors='replace') as f:
    for s in f:
        строк += 1
        if строк <= ГРАНИЦА:
            continue
        try:
            d = json.loads(s)
        except Exception:
            continue
        k = d.get('collector') or '?'
        по_колл[k] = по_колл.get(k, 0) + 1
        if str(d.get('inn') or '').strip():
            с_инн += 1
o['сегодня_после_отметки'] = {'строк': строк - ГРАНИЦА, 'по_коллекторам': по_колл,
                              'с_ИНН': с_инн}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
