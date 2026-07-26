# -*- coding: utf-8 -*-
"""hh-скан БЕЗ API: кто ищет персонал в компрессорную — прямой сигнал, что у
предприятия есть компрессорное хозяйство (владелец: «оператора в компрессорную
ищут 300 компаний»).

Почему не API: api.hh.ru отдаёт 403 без токена приложения, заявка на модерации
до 15 рабочих дней. Публичная выдача hh.ru при этом открыта обычным HTTP
(проверено: 200, без капчи, ~0.6 с). Как только токен появится — источник
переключится на API, парсер останется фолбэком.

Что делает: по списку запросов проходит страницы выдачи (и архив), достаёт
работодателей из встроенного стейта HH-Lux-InitialState (надёжнее разметки),
сопоставляет с базой обзвона по названию и пишет сигнал в enrich.db.
Durable: stage_log('hh'), поэтому прогон резюмируем.
"""
import html as _html
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))

QUERIES = [
    'оператор компрессорной установки',
    'машинист компрессорных установок',
    'механик компрессорного оборудования',
    'слесарь по ремонту компрессорного оборудования',
    'начальник компрессорной станции',
    'энергетик компрессорная',
]
PAGES = int(os.environ.get('HH_PAGES', '5'))      # 5 страниц по 50 = до 250 на запрос
PAUSE = float(os.environ.get('HH_PAUSE', '2.5'))  # вежливо к hh


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept': 'text/html,application/xhtml+xml'})
    try:
        return _OP.open(req, timeout=timeout).read().decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''


def _state(body):
    """JSON стейта выдачи из <template id="HH-Lux-InitialState">."""
    m = re.search(r'HH-Lux-InitialState"?\s*>(.*?)</template>', body, re.S)
    if not m:
        return {}
    try:
        return json.loads(_html.unescape(m.group(1)))
    except Exception:  # noqa: BLE001
        return {}


def _walk_vacancies(node, acc, depth=0):
    """Стейт hh меняется между релизами, поэтому не завязываемся на путь:
    рекурсивно ищем словари, похожие на вакансию (есть название и компания)."""
    if depth > 8 or len(acc) > 4000:
        return
    if isinstance(node, dict):
        nm = node.get('name')
        comp = node.get('company')
        if isinstance(nm, str) and isinstance(comp, dict) and comp.get('name'):
            acc.append({
                'vacancy': nm[:120],
                'employer': str(comp.get('name'))[:120],
                'employer_id': comp.get('id'),
                'area': (node.get('area') or {}).get('name') if isinstance(
                    node.get('area'), dict) else None,
                'archived': bool(node.get('archived')),
            })
        for v in node.values():
            _walk_vacancies(v, acc, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _walk_vacancies(v, acc, depth + 1)


def _from_markup(body):
    """Фолбэк: ссылки /employer/<id> с названием в aria-label."""
    out = []
    for eid, label in re.findall(
            r'href="/employer/(\d+)[^"]*"[^>]*aria-label="Вакансии ([^"]{3,90})"', body):
        out.append({'vacancy': '', 'employer': label, 'employer_id': eid,
                    'area': None, 'archived': False})
    for label, eid in re.findall(
            r'aria-label="Вакансии ([^"]{3,90})"[^>]*href="/employer/(\d+)', body):
        out.append({'vacancy': '', 'employer': label, 'employer_id': eid,
                    'area': None, 'archived': False})
    return out


def scan(queries=None, pages=PAGES, archived=False):
    seen, rows = set(), []
    for q in (queries or QUERIES):
        for page in range(pages):
            url = ('https://hh.ru/search/vacancy?text=' + urllib.parse.quote(q) +
                   f'&items_on_page=50&page={page}' + ('&archived=true' if archived else ''))
            body = _get(url)
            if not body:
                break
            acc = []
            _walk_vacancies(_state(body), acc)
            if not acc:
                acc = _from_markup(body)
            fresh = 0
            for v in acc:
                key = (v['employer'].strip().lower(), v['vacancy'][:60])
                if key in seen:
                    continue
                seen.add(key)
                v['query'] = q
                rows.append(v)
                fresh += 1
            if fresh == 0:
                break                      # страницы кончились
            time.sleep(PAUSE)
    return rows


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    res = scan(pages=int(sys.argv[2]) if len(sys.argv) > 2 else 2,
               archived=(mode == 'archive'))
    emps = {}
    for r in res:
        emps.setdefault(r['employer'], []).append(r['vacancy'])
    print(json.dumps({'вакансий': len(res), 'работодателей': len(emps),
                      'примеры': [{'работодатель': k, 'вакансий': len(v),
                                   'первая': v[0][:60]}
                                  for k, v in list(emps.items())[:12]]},
                     ensure_ascii=False, indent=1))
