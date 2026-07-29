# -*- coding: utf-8 -*-
r"""ПЕРЕМЕР №1: тендерные агрегаторы после починки декодера кодировок.

Прежний замер (109 компаний → 0 контактов, вывод «мираж») недействителен:
_fetch_site декодировал ЛЮБУЮ страницу как utf-8, а tenderguru.ru и часть
других агрегаторов отдают windows-1251 — кириллица гибла ДО разбора, и
регулярка «Контактное лицо» физически не могла сработать.

Считаем честно: зовём БОЕВУЮ EC.find_tender_aggregator_contacts, а рядом
подглядываем в тот же самый скачанный HTML (обёртка вокруг _fetch_site), чтобы
отличить «страницы не нашлись» от «нашлись, но пусты».

ДОЛГОВЕЧНОСТЬ (урок рестарта 25.07): каждая компания дописывается СРАЗУ в
серверный jsonl с fsync. Песочница при рестарте откатится, сервер — нет.
Резюмируемость по тому же файлу: уже посчитанные ИНН пропускаем.

usage: _ops_re_agg.py <start> <count> [threads] [budget_s]
       _ops_re_agg.py sum            — только свод по накопленному потоку
"""
import io
import json
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

ПОТОК = r'C:\seostat\drop\re_agg_stream.jsonl'
_злок = threading.Lock()
_TL = threading.local()
_страницы = {}


def p(*a):
    print(*a)
    sys.stdout.flush()


def _кир(t):
    return len(re.findall(r'[а-яёА-ЯЁ]', t or ''))


def _обёртка(orig):
    def _f(url):
        r = orig(url)
        inn = getattr(_TL, 'inn', '')
        html, mode, meta = (r + ('', '', {}))[:3] if isinstance(r, tuple) else ('', '', {})
        with _злок:
            _страницы.setdefault(inn, []).append(
                {'url': url, 'режим': mode, 'байт': len(html or ''),
                 'кириллицы': _кир(html or ''),
                 'замен': (html or '').count('\ufffd'),
                 'капча': (meta or {}).get('captcha_type') or '',
                 'html': html or ''})
        return r
    return _f


def окна(html):
    """Те же окна, что режет боевая функция: 260 символов после подписи."""
    txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ',
                 re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html or '',
                        flags=re.S | re.I)))
    return [m.group(1) for m in
            re.finditer(r'Контактн\w+\s+лиц\w+\s*[:\-]?\s*(.{0,260})', txt, re.I)]


def цели():
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    из, было = [], set()
    for строки in (БАЗА.values() if isinstance(БАЗА, dict) else [БАЗА]):
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append((i, str(x.get('name') or '')))
    return из


def сделано():
    д = {}
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            д[j.get('inn')] = j
    return д


def дописать(зап):
    with _злок:
        with io.open(ПОТОК, 'a', encoding='utf-8') as f:
            f.write(json.dumps(зап, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def один(inn, name):
    _TL.inn = inn
    t0 = time.time()
    ош = ''
    try:
        рез = EC.find_tender_aggregator_contacts(inn, name) or []
    except Exception as ex:  # noqa: BLE001
        рез, ош = [], f'{type(ex).__name__}: {str(ex)[:90]}'
    with _злок:
        стр = _страницы.pop(inn, [])
    все_окна = []
    листы = []
    for s in стр:
        w = окна(s.pop('html', ''))
        листы.append(dict(s, окон=len(w)))
        все_окна += w[:8]
    дописать({'inn': inn, 'name': name[:70], 'сек': round(time.time() - t0, 1),
              'ошибка': ош, 'контакты': рез, 'листы': листы,
              'окна': [x[:260] for x in все_окна[:12]]})
    return inn


def свод(д):
    """Свод по накопленному потоку. Считаем ДВАЖДЫ: как есть (боевой _фио) и
    пересчётом ФИО по сохранённым окнам — так видно вклад починки _фио."""
    вс = {'компаний': 0, 'с_контактом': 0, 'контактов': 0, 'с_фио': 0,
          'с_почтой': 0, 'с_телефоном': 0, 'листов': 0, 'листов_ок': 0,
          'листов_с_окнами': 0, 'окон': 0, 'листов_битая_кириллица': 0,
          'компаний_без_листов': 0, 'ошибок': 0}
    пофио = {'фио_из_окон': 0, 'окон_с_фио': 0}
    примеры, домены = [], {}
    for j in д.values():
        вс['компаний'] += 1
        if j.get('ошибка'):
            вс['ошибок'] += 1
        к = j.get('контакты') or []
        if к:
            вс['с_контактом'] += 1
        вс['контактов'] += len(к)
        for c in к:
            if c.get('person'):
                вс['с_фио'] += 1
            if c.get('email'):
                вс['с_почтой'] += 1
            if c.get('phone'):
                вс['с_телефоном'] += 1
            if len(примеры) < 24:
                примеры.append(dict(c, inn=j.get('inn'), name=j.get('name')))
        листы = j.get('листы') or []
        if not листы:
            вс['компаний_без_листов'] += 1
        for s in листы:
            вс['листов'] += 1
            d = re.sub(r'^www\.', '', (re.findall(r'//([^/]+)', s.get('url') or '')
                                       or [''])[0])
            домены[d] = домены.get(d, 0) + 1
            if s.get('байт'):
                вс['листов_ок'] += 1
            if s.get('окон'):
                вс['листов_с_окнами'] += 1
                вс['окон'] += s['окон']
            if s.get('замен', 0) > 50 and s.get('кириллицы', 0) < 200:
                вс['листов_битая_кириллица'] += 1
        # пересчёт ФИО по сохранённым окнам ТЕКУЩИМ кодом _фио
        for w in (j.get('окна') or []):
            ф = EC._фио(w)
            if ф:
                пофио['окон_с_фио'] += 1
    p('ДОМЕНЫ ' + json.dumps(sorted(домены.items(), key=lambda x: -x[1])[:10],
                             ensure_ascii=False))
    for x in примеры[:12]:
        p('ПРИМЕР ' + json.dumps(x, ensure_ascii=False)[:300])
    p('ФИО_ПО_ОКНАМ ' + json.dumps(пофио, ensure_ascii=False))
    p('ИТОГ ' + json.dumps(вс, ensure_ascii=False))


def main():
    if sys.argv[1:2] == ['sum']:
        свод(сделано())
        return
    start = int(sys.argv[1])
    count = int(sys.argv[2])
    thr = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    бюджет = float(sys.argv[4]) if len(sys.argv) > 4 else 195.0
    EC._fetch_site = _обёртка(EC._fetch_site)
    все = цели()
    уже = сделано()
    очередь = [(i, n) for i, n in все[start:start + count] if i not in уже]
    p('ЦЕЛЕЙ_ВСЕГО=%d СРЕЗ=%d..%d К_РАБОТЕ=%d УЖЕ=%d'
      % (len(все), start, start + count, len(очередь), len(уже)))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=thr) as ex:
        фьючи = []
        for i, n in очередь:
            if time.time() - t0 > бюджет:
                p('БЮДЖЕТ исчерпан, остаток не запускали')
                break
            фьючи.append(ex.submit(один, i, n))
        for f in фьючи:
            try:
                f.result(timeout=max(10, бюджет + 90 - (time.time() - t0)))
            except Exception as ex2:  # noqa: BLE001
                p('поток упал: %s' % str(ex2)[:80])
    свод(сделано())


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        p('ФАТАЛЬНО:', traceback.format_exc()[-1200:])
