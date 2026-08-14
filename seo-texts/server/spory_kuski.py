# -*- coding: utf-8 -*-
r"""Куски РАЗМЕТКИ вокруг спорных адресов — из нашего кэша страниц.

Зачем не скриншот живого сайта: из песочницы Chromium наружу не ходит (агентский
прокси рвёт CONNECT от браузера — проверено на трёх адресах, curl через тот же
прокси отвечает 200, браузер получает ERR_CONNECTION_RESET). Да и живой сайт
сегодня — уже не то, что видел судья вчера. Поэтому берём ровно ту страницу, на
которой адрес был снят: она лежит у нас в pagecache целиком.

Отдаём фрагмент РАЗМЕТКИ, а не текст: строка таблицы и карточка сотрудника несут
привязку «должность-человек-адрес» именно вёрсткой, и в плоском тексте она
теряется — на этом мы уже обожглись, когда роль ставилась по окну в 500 знаков.

    python spory_kuski.py [файл-споров.json] [имя-на-дропе.json]
"""
import gzip
import json
import os
import re
import sys
import urllib.request

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
OKNO = 1800          # знаков разметки в каждую сторону от адреса
_MUSOR = re.compile(r'<(script|style|noscript|svg|iframe)\b.*?</\1>', re.S | re.I)


def _stranicy(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return []
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    return [(x.get('url') or '', x.get('html') or '') for x in (d.get('pages') or [])]


# элементы, которые в вёрстке означают «одна карточка / одна строка человека»
_ОБЁРТКИ = ('tr', 'li', 'td', 'article', 'section', 'div', 'p', 'table')


def _celyy_element(h, i, tegi=_ОБЁРТКИ):
    """Целый элемент, ВНУТРИ которого лежит позиция i.

    Резать окном по знакам нельзя: кусок начинается с «</button>» и обрывается на
    полуслове, браузер такую разметку сворачивает и место оказывается пустым
    (поймано на первом же снимке). Ищем ближайшую открывающую обёртку и её
    настоящую пару, считая вложенность.
    """
    луч = ''
    for teg in tegi:
        otkr = re.compile(r'<%s\b[^>]*>' % teg, re.I)
        zakr = re.compile(r'</%s\s*>' % teg, re.I)
        начала = [m for m in otkr.finditer(h, 0, i)]
        for m in reversed(начала[-6:]):        # ближайшие шесть — дальше смысла нет
            глубина, поз = 1, m.end()
            while глубина and поз < len(h):
                mo, mz = otkr.search(h, поз), zakr.search(h, поз)
                if not mz:
                    break
                if mo and mo.start() < mz.start():
                    глубина += 1
                    поз = mo.end()
                else:
                    глубина -= 1
                    поз = mz.end()
            if not глубина and поз > i:
                кусок = h[m.start():поз]
                if 200 < len(кусок) < 12000 and (not луч or len(кусок) < len(луч)):
                    луч = кусок
                break
    return луч


def _kusok(html, adres):
    """Фрагмент разметки вокруг адреса — ЦЕЛЫМ элементом, а не окном по знакам."""
    h = _MUSOR.sub(' ', html or '')
    i = h.lower().find(adres.lower())
    if i < 0:
        return ''
    целый = _celyy_element(h, i)
    if целый:
        return целый
    a, b = max(0, i - OKNO), min(len(h), i + len(adres) + OKNO)
    a2 = h.find('<', a)
    b2 = h.rfind('>', a, b)
    return h[a2:b2 + 1] if 0 <= a2 < b2 else ''


def sobrat(spory):
    out = []
    for s in spory:
        inn = str(s.get('inn') or '')
        adres = s.get('email') or ''
        kusok = ''
        stranica = s.get('url') or ''
        for u, h in _stranicy(inn):
            if stranica and u != stranica:
                continue
            kusok = _kusok(h, adres)
            if kusok:
                stranica = u
                break
        if not kusok:                      # адрес мог быть снят с другой страницы
            for u, h in _stranicy(inn):
                kusok = _kusok(h, adres)
                if kusok:
                    stranica = u
                    break
        z = dict(s)
        z['kusok'] = kusok
        z['stranica'] = stranica
        out.append(z)
    return out


def main():
    vhod = sys.argv[1] if len(sys.argv) > 1 else r'C:\sender\_tmp\SPORY-SUDI.json'
    imya = sys.argv[2] if len(sys.argv) > 2 else 'SPORY-SUDI-KUSKI.json'
    spory = json.load(open(vhod, encoding='utf-8'))
    out = sobrat(spory)
    blob = json.dumps(out, ensure_ascii=False).encode('utf-8')
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.open(urllib.request.Request(DROP + '/' + imya, data=blob, method='PUT',
                                   headers={'X-Drop-Token': TOKEN}), timeout=180)
    print(json.dumps({'споров': len(out), 'с_куском': sum(1 for x in out if x['kusok']),
                      'файл': imya, 'байт': len(blob)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
