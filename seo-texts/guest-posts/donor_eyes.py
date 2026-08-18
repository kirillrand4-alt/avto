#!/usr/bin/env python3
"""Проверка доноров «глазами с сервера»: что на площадке НА САМОМ ДЕЛЕ.

Требование владельца (05.08.2026): «тематике особо не верь у доноров, лучше
перепроверь глазами с сервера». Тематика в выгрузке биржи проставлена вебмастером
и Miralinks её не верифицирует — на неё опираться нельзя.

Скрипт гоняет browser_probe на сервере владельца (дельфин-профили с мобильными
прокси там, где стоит антибот), снимает главную + разделы + свежие статьи и
складывает сырьё в donor-eyes-raw.json. Классификацию по этому сырью делает
отдельный шаг через провайдерский API (donor_eyes_lenses.py) — здесь только сбор.

    python3 donor_eyes.py                 # все 10 доноров приоритета
    python3 donor_eyes.py ftimes.ru       # точечно
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'server'))
import run_on_server  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'donor-eyes-raw.json')

# Профили дельфина с приватными мобильными прокси (CLAUDE.md): по кругу, чтобы не
# бить в площадку с одного IP.
DOLPHIN = ['829115353', '829115344', '829115332']

DONORS = [
    ('kineshemec.ru',       1),
    ('samaraonline24.ru',   2),
    ('operativa.ru',        3),
    ('moscow-baku.ru',      4),
    ('new-sebastopol.com',  5),
    ('oteplicah.com',       6),
    ('ftimes.ru',           7),
    ('gazetagavrilovka.ru', 8),
    ('krasnodar.bz',        9),
    ('arh112.ru',          10),
]


def job_for(url: str, i: int) -> dict:
    """Одна страница = одно задание.

    Пакетный режим (`urls`) на сервере вернул пустой список — версия browser_probe
    там его не поддерживает. Не гадаем: шлём страницы отдельными заданиями, раннер
    их и так тянет параллельно.
    """
    return {
        'task': 'browser_probe',
        'args': {
            'url': url,
            'wait_ms': 6000,
            'return_html': True,
            'html_cap': 90000,
            'solve': True,                       # решатель капч выключать нельзя
            'dolphin_profile': DOLPHIN[i % len(DOLPHIN)],
            'screenshot': False,
        },
    }


_NAV_SKIP = re.compile(r'(?i)(войти|регистр|подписк|реклам\w*\s*$|контакт|поиск|вверх|'
                       r'политик|соглашен|карта сайта|rss|vk\.com|t\.me|ok\.ru)')


def nav_links(html: str, base: str) -> list:
    """Разделы из шапки/меню: короткие анкоры с внутренним href.

    Именно они отвечают на вопрос «есть ли на площадке рубрика, куда ляжет
    промышленная статья» — заголовки материалов на это не отвечают.
    """
    out, seen = [], set()
    for href, inner in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html or ''):
        txt = _WS.sub(' ', _TAG.sub(' ', inner)).strip()
        if not (2 <= len(txt) <= 24) or _NAV_SKIP.search(txt):
            continue
        if href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        full = href if href.startswith('http') else base.rstrip('/') + '/' + href.lstrip('/')
        if base.split('//')[-1].split('/')[0] not in full:
            continue
        key = full.rstrip('/')
        if key in seen:
            continue
        seen.add(key)
        out.append({'text': txt, 'url': full})
    return out[:45]


_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'\s+')


def strip_tags(html: str) -> str:
    html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html or '')
    return _WS.sub(' ', _TAG.sub(' ', html)).strip()


def digest(page: dict) -> dict:
    """Из сырой страницы — то, по чему видно реальную тематику."""
    html = page.get('html') or ''
    text = page.get('text') or strip_tags(html)[:8000]
    title = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
    desc = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html)
    heads = [_WS.sub(' ', _TAG.sub(' ', m)).strip()
             for m in re.findall(r'(?is)<h[1-3][^>]*>(.*?)</h[1-3]>', html)]
    # тексты ссылок длиннее 25 знаков — практически всегда заголовки материалов
    anchors = [_WS.sub(' ', _TAG.sub(' ', m)).strip()
               for m in re.findall(r'(?is)<a[^>]*>(.*?)</a>', html)]
    return {
        'url': page.get('url'),
        'http_status': page.get('http_status'),
        'title': strip_tags(title.group(1)) if title else '',
        'description': (desc.group(1)[:300] if desc else ''),
        'headings': [h for h in heads if h][:40],
        'headlines': [a for a in anchors if 25 <= len(a) <= 160][:60],
        'text_head': text[:2500],
        'html_len': page.get('html_full_len') or len(html),
        'captcha': page.get('captcha_type') or page.get('captcha_solved'),
        'error': page.get('error'),
    }




# рубрики, в которые теоретически ложится промышленная статья
_B2B_RX = re.compile(r'(?i)(эконом|бизнес|промышл|производ|строит|агро|сельск|транспорт|'
                     r'авто|техн|инвест|компан|рынок|финанс|недвиж|энерг|it|наук)')


def pick_rubrics(nav: list, n: int = 3) -> list:
    """Разделы, которые стоит открыть: сначала похожие на B2B, потом любые."""
    prio = [x for x in nav if _B2B_RX.search(x['text'])]
    rest = [x for x in nav if x not in prio]
    return (prio + rest)[:n]


def main() -> int:
    # Проверка 15 доноров, отобранных фактом (18.08): список подаётся файлом,
    # а не правкой DONORS - тот список остаётся историей приоритета владельца.
    global OUT
    args = sys.argv[1:]
    if '--file' in args:
        path = args[args.index('--file') + 1]
        targets = [(l.strip(), i + 1) for i, l in enumerate(open(path, encoding='utf-8'))
                   if l.strip()]
        OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           args[args.index('--out') + 1] if '--out' in args
                           else 'donor-eyes-15.json')
    else:
        only = [a for a in args if not a.startswith('--')] or None
        targets = [(d, p) for d, p in DONORS if not only or d in only]
    print(f'снимаю {len(targets)} доноров глазами с сервера '
          f'(дельфин-профили {", ".join(DOLPHIN)})…')
    t0 = time.time()

    # ---- проход 1: главные ----
    jobs = [job_for(f'https://{d}', i) for i, (d, _) in enumerate(targets)]
    res = run_on_server.submit_many(jobs, threads=5, timeout=1500)

    out, second = {}, []
    for (dom, prio), r in zip(targets, res):
        data = (r or {}).get('data') or {}
        nav = nav_links(data.get('html') or '', f'https://{dom}')
        out[dom] = {
            'prio': prio,
            'nav': nav,
            'runner_error': (r or {}).get('error') or str((r or {}).get('stderr', ''))[:300],
            'pages': [digest(data)],
        }
        for rub in pick_rubrics(nav):
            second.append((dom, rub))
        print(f'  главная {dom:<22} HTTP {out[dom]["pages"][0]["http_status"]}, '
              f'разделов в меню: {len(nav)}')

    # ---- проход 2: по 3 раздела на донора ----
    if second:
        print(f'\nоткрываю {len(second)} разделов…')
        jobs2 = [job_for(rub['url'], i) for i, (_, rub) in enumerate(second)]
        res2 = run_on_server.submit_many(jobs2, threads=6, timeout=1500)
        for (dom, rub), r in zip(second, res2):
            data = (r or {}).get('data') or {}
            d = digest(data)
            d['nav_text'] = rub['text']
            out[dom]['pages'].append(d)

    for dom, v in out.items():
        ok = [p for p in v['pages'] if (p['http_status'] or 0) < 400 and p['html_len'] > 500]
        v['ok_pages'] = len(ok)
        mark = '✓' if ok else '✗'
        print(f'  {mark} {dom:<22} страниц с содержимым: {len(ok)}/{len(v["pages"])}'
              + (f"  [{v['runner_error'][:60]}]" if not ok else ''))

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\nсырьё -> {OUT}  ({time.time() - t0:.0f} c)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
