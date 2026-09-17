# -*- coding: utf-8 -*-
"""Сколько региональных фондов публикуют реестр получателей поддержки (файлом)."""
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))

РЕЕСТР = re.compile(r'получател\w*\s+(?:поддержк|микрозайм|займ)|реестр\w*\s+получател|'
                    r'сведения\s+о\s+получател|перечень\s+получател|'
                    r'профинансирован|поддержанн\w+\s+проект|реализованн\w+\s+проект|'
                    r'портфель\s+проект', re.I)
ФАЙЛ = re.compile(r'\.(xlsx|xls|csv|pdf|docx?)$', re.I)
ССЫЛКА = re.compile(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>', re.S | re.I)


def взять(url, лимит=300000, tmo=20):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        return r.getcode(), r.read(лимит).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return -1, ''


def разобрать(d):
    из_главной = []
    код, h = взять('https://' + d + '/')
    if код != 200 or not h:
        return {'домен': d, 'код': код}
    for href, текст in ССЫЛКА.findall(h):
        чист = re.sub(r'<[^>]+>|\s+', ' ', текст).strip()
        if РЕЕСТР.search(чист) or РЕЕСТР.search(urllib.parse.unquote(href)):
            полн = urllib.parse.urljoin('https://' + d + '/', href)
            из_главной.append({'подпись': чист[:60], 'url': полн[:160],
                               'файл': bool(ФАЙЛ.search(urllib.parse.unquote(полн.split('?')[0])))})
    return {'домен': d, 'код': код, 'найдено': из_главной[:6]}


код, html = взять('https://frprf.ru/zaymy-regfondy/proekty-razvitiya-s-rfrp/', 400000)
домены = sorted({m for m in re.findall(r'https?://([a-z0-9.\-]+\.(?:ru|рф))/', html)
                 if 'frprf' not in m and 'gov.ru' not in m and 'yandex' not in m})

итоги = []
with ThreadPoolExecutor(max_workers=10) as ex:
    итоги = list(ex.map(разобрать, домены))

с_реестром = [x for x in итоги if x.get('найдено')]
с_файлом = [x for x in с_реестром if any(n['файл'] for n in x['найдено'])]
сводка = {
    'доменов_проверено': len(итоги),
    'ответили_200': sum(1 for x in итоги if x.get('код') == 200),
    'есть_раздел_про_получателей_или_проекты': len(с_реестром),
    'из_них_ссылка_на_файл': len(с_файлом),
    'примеры': [{'домен': x['домен'], 'подписи': [n['подпись'] for n in x['найдено'][:2]],
                 'url': x['найдено'][0]['url']} for x in с_реестром[:10]],
}
print('===ИТОГ===')
print(json.dumps(сводка, ensure_ascii=False, indent=1))
