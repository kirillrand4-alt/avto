# -*- coding: utf-8 -*-
"""Пробник ДО сбора: работает ли нарезка выдачи ЕИС по окну публикации.

Зачем. Потолок выдачи — 20 страниц по 50 = 1 000 записей на запрос, а «компрессор»
показывает «более 70 000». Значит общий запрос без нарезки берёт полтора процента.
3-я сессия обожглась на обратном: у неё в сборщике было зашито publishDateFrom=01.01.2025,
и она собрала 30% канала, не зная об этом. Поэтому окно проверяем ЗАМЕРОМ, а не верой:

  1. запрос без окна           -> счётчик N0
  2. тот же запрос по годам    -> счётчики N(2019..2026)
  3. сумма годовых должна быть сопоставима с N0, а каждое окно — влезать в 1 000

Если сумма годовых заметно меньше N0 — параметр не применяется (или применяется не так),
и нарезать надо по другому полю. Ничего не собираем, только считаем.
"""
import json, os, re, sys, time, urllib.parse

BAZA = r'C:\sender'
OUT = os.path.join(BAZA, 'park_okna_probnik.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
ZAPROSY = ['винтовой компрессор', 'компрессор']
GODY = list(range(2019, 2027))


def _hrom():
    for k in (r'C:\sender\pw-browsers', os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')):
        if not k or not os.path.isdir(k):
            continue
        for d in sorted(os.listdir(k), reverse=True):
            e = os.path.join(k, d, 'chrome-win64', 'chrome.exe')
            if os.path.exists(e):
                return e
    return None


def _schetchik(t):
    """ЕИС пишет «Результаты поиска 70 123 записи» и «более N записей» на больших выдачах"""
    t = re.sub(r'\s+', ' ', t or '')
    bolee = bool(re.search(r'более\s*[\d \u00a0]+\s*запис', t))
    m = (re.search(r'Результаты поиска\s*([\d \u00a0]{1,14})\s*запис', t)
         or re.search(r'([\d \u00a0]{2,14})\s*запис(?:ей|и|ь)', t)
         or re.search(r'Найдено\s*([\d \u00a0]{1,14})', t))
    if not m:
        return None, bolee
    return int(re.sub(r'\D', '', m.group(1)) or 0), bolee


def _url(q, god=None):
    u = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html'
         '?searchString=%s&morphology=on&pageNumber=1&recordsPerPage=_50'
         '&fz44=on&fz223=on&af=on&ca=on&pc=on&pa=on' % urllib.parse.quote(q))
    if god:
        u += ('&publishDateFrom=01.01.%d&publishDateTo=31.12.%d' % (god, god))
    return u


def main():
    itog = []
    from playwright.sync_api import sync_playwright
    exe = _hrom()
    with sync_playwright() as p:
        kw = {'headless': True, 'args': ['--no-sandbox',
                                         '--disable-blink-features=AutomationControlled']}
        if exe:
            kw['executable_path'] = exe
        br = p.chromium.launch(**kw)
        ctx = br.new_context(user_agent=UA, locale='ru-RU',
                             viewport={'width': 1366, 'height': 900},
                             ignore_https_errors=True)
        page = ctx.new_page()
        for q in ZAPROSY:
            for god in [None] + GODY:
                r = {'zapros': q, 'god': god}
                try:
                    page.goto(_url(q, god), timeout=90000, wait_until='domcontentloaded')
                    page.wait_for_timeout(3000)
                    t = page.inner_text('body')
                    n, bolee = _schetchik(t)
                    r['zapisey'] = n
                    r['bolee_chem'] = bolee
                    # проверяем, что фильтр реально применён: он рисуется в шапке выдачи
                    r['okno_vidno_na_stranice'] = bool(god and (
                        '01.01.%d' % god in re.sub(r'\s+', '', t.replace('\u00a0', ''))
                        or '01.01.%d' % god in t))
                except Exception as e:
                    r['oshibka'] = str(e)[:160]
                itog.append(r)
                with open(OUT, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(r, ensure_ascii=False) + '\n')
                    f.flush()
                    os.fsync(f.fileno())
        br.close()
    # сводка: сумма годовых против «без окна»
    svod = {}
    for q in ZAPROSY:
        bez = next((x.get('zapisey') for x in itog if x['zapros'] == q and x['god'] is None), None)
        gody = {x['god']: x.get('zapisey') for x in itog if x['zapros'] == q and x['god']}
        svod[q] = {'bez_okna': bez, 'summa_po_godam': sum(v for v in gody.values() if v),
                   'po_godam': gody,
                   'okon_vyshe_1000': sum(1 for v in gody.values() if v and v > 1000)}
    print(json.dumps({'svod': svod, 'syro': itog}, ensure_ascii=False)[:5500])


if __name__ == '__main__':
    main()
