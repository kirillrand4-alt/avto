# -*- coding: utf-8 -*-
"""Смотреть карточки панели обзвона глазами — под обоими пользователями.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Владелец просит «зайти в админку и посмотреть 15 разных карточек».
Первая попытка дала ложный вывод «15 из 15 нет в панели»: я забирал HTML целиком и резал его
своим потолком в 45 000 знаков, а карточка идёт ПОСЛЕ длинной шапки фильтров. То есть
инструмент отвечал не на тот вопрос, что я задавал. Здесь вырезка делается НА СТРАНИЦЕ,
вокруг самого ИНН, и потолок больше не участвует в ответе.

ВТОРАЯ ЛОВУШКА, ради которой модуль умеет обоих пользователей. Панель отдаёт
`{"detail":"Компания не найдена или не назначена пользователю"}` — одна и та же строка на два
РАЗНЫХ факта: «предприятия в панели нет» и «оно есть, но закреплено за другим менеджером».
Под одним пользователем их не различить. Различает только повтор того же ИНН под вторым.

Использование:
    python3 panel_kartochki.py --inn 7601001107,6623000680 --kto oba
    python3 panel_kartochki.py --sluchayno 15 --kto user2
"""
import json
import os
import random
import re
import subprocess
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
KORNI = 'https://parsercompressor.online'
LYUDI = {
    'user1': 'U1--f2cgVrBq5Xt2FtgjGGLstRMUGM',
    'user2': 'U2-O8Daq7nOp8ziyk2D_FyLcQy8u78',
}


def dovod(imya, po_umolchaniyu):
    return type(po_umolchaniyu)(sys.argv[sys.argv.index(imya) + 1]) \
        if imya in sys.argv else po_umolchaniyu


# Скрипт идёт в `return` целиком, а не в `script`: патч выполняет `script` СИНХРОННО
# (`evaluate('() => { ... }')`), и любой `await fetch` внутри него просто не дождётся. А
# значение из `return` Playwright дожидается, если это промис. Отсюда async-IIFE.
JS = r"""(async () => {
  // Вход делается ЗАПРОСОМ, а не отправкой формы. Отправка формы уводит страницу, и в двух
  // прогонах из трёх Playwright падал с «Execution context was destroyed, most likely because
  // of a navigation»: скрипт стартовал, пока браузер уходил на новый адрес. Запросом
  // навигации нет вовсе — кука ставится ответом, а страница остаётся той же.
  const vhod = await fetch('/obzvon/centro/login', {
      method: 'POST', credentials: 'same-origin', redirect: 'follow',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: new URLSearchParams({username: %s, password: %s}).toString()});
  const inns = %s;
  const out = [{vhod: vhod.status}];
  for (const inn of inns) {
    try {
      const r = await fetch('/obzvon/centro?inn=' + inn, {credentials: 'same-origin'});
      const t = await r.text();
      let i = t.indexOf('ИНН ' + inn);
      if (i < 0) i = t.indexOf(inn);
      out.push({inn: inn, code: r.status, len: t.length, est: i >= 0,
                telo: i >= 0 ? t.slice(Math.max(0, i - 3000), i + 22000) : t.slice(0, 400)});
    } catch (e) { out.push({inn: inn, oshibka: String(e).slice(0, 200)}); }
  }
  return JSON.stringify(out);
})()"""


def zahod(kto, inns, tayminaut=900):
    """Один заход: вход формой под `kto`, затем выборка карточек со страницы."""
    zad = {
        'url': f'{KORNI}/obzvon/centro/login',
        'screenshot': False, 'proxy': '', 'wait_ms': 5000, 'html_cap': 2000,
        'eval_js': {'return': JS % (json.dumps(kto), json.dumps(LYUDI[kto]),
                                    json.dumps(inns)), 'after_ms': 500},
    }
    try:
        p = subprocess.run([sys.executable, KLIENT, 'browser_probe',
                            json.dumps(zad, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=tayminaut)
    except subprocess.TimeoutExpired:
        return None, f'раннер не ответил за {tayminaut} с'
    try:
        d = json.loads(p.stdout[p.stdout.index('{'):]).get('data') or {}
    except (ValueError, json.JSONDecodeError):
        return None, (p.stdout or p.stderr or 'пустой ответ')[-300:]
    res = d.get('eval_js_value')
    if res is None:
        return None, ('eval_js не вернулся. ключи: ' + ','.join(sorted(d.keys())) +
                      f" | http_status={d.get('http_status')} | err={str(d.get('eval_js_err'))[:200]}"
                      f" | error={str(d.get('error'))[:200]}")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except json.JSONDecodeError:
            return None, 'eval_js вернул не JSON'
    return res, ''


def ochered_inn():
    import csv
    csv.field_size_limit(10 ** 7)
    put = os.path.join(BAZA, 'engineers-lens', 'OCHERED-centrobezhnye.csv')
    return [r['inn'] for r in csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';')
            if (r.get('inn') or '').strip()]


def main():
    kto = dovod('--kto', 'user2')
    vyhod = dovod('--vyhod', '')
    if '--inn' in sys.argv:
        inns = [s.strip() for s in dovod('--inn', '').split(',') if s.strip()]
    else:
        n = dovod('--sluchayno', 15)
        vse = ochered_inn()
        random.seed(dovod('--seed', 0) or None)
        inns = random.sample(vse, min(n, len(vse)))
    kogo = list(LYUDI) if kto == 'oba' else [kto]
    itog = {}
    for k in kogo:
        res, err = zahod(k, inns)
        if err:
            print(f'[{k}] сбой: {err}', file=sys.stderr)
            continue
        itog[k] = res
        est = sum(1 for x in res if x.get('est'))
        print(f'[{k}] снято {len(res)}, карточка открылась у {est}', file=sys.stderr)
    if vyhod:
        json.dump(itog, open(vyhod, 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'→ {vyhod}', file=sys.stderr)
    else:
        for k, res in itog.items():
            for x in res:
                print(k, x.get('inn'), x.get('est'), (x.get('telo') or '')[:100].replace('\n', ' '))


if __name__ == '__main__':
    main()
