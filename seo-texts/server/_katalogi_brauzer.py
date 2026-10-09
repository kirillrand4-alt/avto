# -*- coding: utf-8 -*-
r"""Каталоги разбора: отказывают ли они и обычному браузеру (владелец 09.10: «не скачивать домены, которые стабильно
отказывают, если отказы даже через браузер идут»).

1. По <набор>-razbor.jsonl — статистика страниц каталогов по доменам: ok / отказ (HTTP 4xx, 5xx, URLError) / ИНН найдено.
2. Проблемные домены (>= 5 страниц, и либо ok < 50%, либо ИНН не найден ни на одной) — до 3 их страниц открываются
   обычным Chromium (headless, БЕЗ прокси, без антидетекта и капч), по одной, с паузой 4 с: код ответа, заголовок,
   капча/челлендж, есть ли ИНН в отрендеренном тексте.
Итог: C:\seostat\drop\drop-storage\<набор>-katalogi-brauzer.json + печать после ===ИТОГ===.
"""
import collections
import json
import os
import re
import time

DIR = r'C:\sender\server'
НАБОР = os.environ.get('POISK_NABOR', 'meyer7t')
ИНН_RX = re.compile(r'ИНН\D{0,20}(\d{10}|\d{12})(?!\d)')
КАПЧА = re.compile(r'captcha|smartcaptcha|cf-challenge|challenge-platform|Подтвердите, что вы не робот|'
                   r'Проверка браузера|Access denied|Доступ ограничен|Too Many Requests', re.I)
CHROME = [r'C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe',
          r'C:\Program Files\Google\Chrome\Application\chrome.exe']


def статистика():
    дом = collections.defaultdict(lambda: {'страниц': 0, 'ok': 0, 'отказ': collections.Counter(), 'с_ИНН': 0,
                                           'не_скачивались': 0, 'примеры': []})
    for s in open(os.path.join(DIR, НАБОР + '-razbor.jsonl'), encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('тип') != 'каталог':
            continue
        д = дом[з.get('домен', '')]
        д['страниц'] += 1
        ст = str(з.get('страница') or '')
        if ст.startswith('не скачивалась'):
            д['не_скачивались'] += 1
            continue
        if ст == 'ok':
            д['ok'] += 1
            if з.get('инн'):
                д['с_ИНН'] += 1
            elif len(д['примеры']) < 3:
                д['примеры'].append(з['url'])
        else:
            д['отказ'][ст[:40]] += 1
            if len(д['примеры']) < 3:
                д['примеры'].append(з['url'])
    return дом


def проблемные(дом):
    out = []
    for h, д in дом.items():
        скач = д['страниц'] - д['не_скачивались']
        if скач < 5:
            continue
        if д['ok'] / скач < 0.5 or д['с_ИНН'] == 0:
            out.append(h)
    return sorted(out, key=lambda h: -(дом[h]['страниц']))


def браузер(урлы):
    from playwright.sync_api import sync_playwright
    exe = next((p for p in CHROME if os.path.exists(p)), None)
    рез = {}
    with sync_playwright() as pw:
        б = pw.chromium.launch(headless=True, executable_path=exe)
        к = б.new_context(locale='ru-RU', viewport={'width': 1366, 'height': 900})
        стр = к.new_page()
        for u in урлы:
            r = {'url': u}
            try:
                отв = стр.goto(u, timeout=30000, wait_until='domcontentloaded')
                стр.wait_for_timeout(3000)
                т = стр.inner_text('body')[:200000]
                r.update({'код': отв.status if отв else None, 'заголовок': (стр.title() or '')[:80],
                          'капча': bool(КАПЧА.search(т[:5000]) or КАПЧА.search(стр.content()[:20000])),
                          'ИНН_в_тексте': len(set(ИНН_RX.findall(т))), 'символов': len(т)})
            except Exception as e:  # noqa: BLE001
                r['ошибка'] = repr(e)[:120]
            рез[u] = r
            time.sleep(4)
        б.close()
    return рез


def main():
    дом = статистика()
    пр = проблемные(дом)[:18]
    урлы = [u for h in пр for u in дом[h]['примеры'][:3]]
    бр = браузер(урлы)
    итог = []
    for h in пр:
        д = дом[h]
        пробы = [бр[u] for u in д['примеры'][:3] if u in бр]
        итог.append({'домен': h, 'страниц': д['страниц'], 'не_скачивались (ИНН в адресе)': д['не_скачивались'],
                     'ok': д['ok'], 'с_ИНН': д['с_ИНН'], 'отказы': dict(д['отказ']),
                     'браузер': [{k: v for k, v in p.items() if k != 'url'} for p in пробы]})
    всего = {h: {'страниц': д['страниц'], 'ok': д['ok'], 'с_ИНН': д['с_ИНН'], 'отказов': sum(д['отказ'].values()),
                 'не_скачивались': д['не_скачивались']} for h, д in дом.items()}
    with open(r'C:\seostat\drop\drop-storage\%s-katalogi-brauzer.json' % НАБОР, 'w', encoding='utf-8') as f:
        json.dump({'проблемные': итог, 'все_домены': всего}, f, ensure_ascii=False, indent=1)
    print('===ИТОГ===')
    for x in итог:
        б = x['браузер']
        print('%-26s стр %4d ok %3d сИНН %3d отказы %-34s | браузер: %s' % (
            x['домен'][:26], x['страниц'], x['ok'], x['с_ИНН'], json.dumps(x['отказы'], ensure_ascii=False)[:34],
            '; '.join('%s%s ИНН%s' % (p.get('код', p.get('ошибка', '?'))[:30] if isinstance(p.get('код', p.get('ошибка')), str)
                                       else p.get('код'), ' КАПЧА' if p.get('капча') else '', p.get('ИНН_в_тексте', '-'))
                      for p in б)))


if __name__ == '__main__':
    main()
