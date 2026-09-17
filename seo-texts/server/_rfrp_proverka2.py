# -*- coding: utf-8 -*-
"""Разделы про проекты у региональных фондов — ищем по ТЕКСТУ ссылок, а не по адресу."""
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
СЛОВА = re.compile(r'проект|заемщик|заёмщик|портфел|профинансир|реализован|'
                   r'поддержан|получател|истори|результат', re.I)
ССЫЛКА = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.{0,80}?)</a>', re.S | re.I)


def взять(url, лимит=300000, tmo=25):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        return r.getcode(), r.read(лимит).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return -1, ''


домены = ['frp-10.ru', 'frp-33.ru', 'fondugra.ru', 'fond73.ru', 'formap.ru', 'crp65.ru']
итог = []
for d in домены:
    зап = {'домен': d}
    код, h = взять('https://' + d + '/')
    зап['код'] = код
    if код == 200 and h:
        кандидаты = []
        for href, текст in ССЫЛКА.findall(h):
            чист = re.sub(r'<[^>]+>|\s+', ' ', текст).strip()
            if СЛОВА.search(чист) or СЛОВА.search(href):
                кандидаты.append((urllib.parse.urljoin('https://' + d + '/', href), чист[:40]))
        видано = []
        for url, подпись in кандидаты[:4]:
            к2, h2 = взять(url)
            if к2 != 200 or not h2:
                видано.append({'раздел': подпись, 'url': url, 'код': к2})
                continue
            т = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h2, flags=re.S)
            т = re.sub(r'<[^>]+>', ' ', т)
            т = re.sub(r'\s+', ' ', т)
            компании = sorted({m for m in re.findall(
                r'(?:ООО|АО|ПАО|ЗАО)\s*[«"][^»"]{3,45}[»"]', т)})
            суммы = re.findall(r'\d{1,4}[,.]?\d*\s*(?:млн|млрд)', т)
            видано.append({'раздел': подпись, 'url': url, 'код': к2,
                           'компаний': len(компании), 'сумм': len(суммы),
                           'примеры': компании[:3]})
        зап['кандидатов'] = len(кандидаты)
        зап['проверено'] = видано
    итог.append(зап)

print('===ИТОГ===')
print(json.dumps(итог, ensure_ascii=False, indent=1))
