# -*- coding: utf-8 -*-
"""ЗАМЕР ГРУПП ВК: воронка охвата + живые люди с должностями.

Без дельфина: VK_TOKEN — СЕРВИСНЫЙ ключ приложения, к IP не привязан
(проверено шагом 0: groups.getById отдал contacts с подписями ролей).

Воронка: компания -> слаг со своего сайта (EC.vk_slug_from_site) -> группа
существует -> в группе непустой блок «Контакты» -> у контакта есть ЖИВОЙ
человек (users.get по user_id) и ДОЛЖНОСТЬ (поле desc).
Дополнительно смотрим описание группы на ФИО+должность.
Ничего не пишем в базу.
"""
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import urllib.parse
import urllib.request

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

БАЗА = r'C:\sender\_ops\sales_base.json'
БЮДЖЕТ = float(os.environ.get('VK_БЮДЖЕТ', '170'))   # секунд на скан слагов


def P(*a):
    print(*a)
    sys.stdout.flush()


def вк(method, **prm):
    tok = EC._read_secret('VK_TOKEN') or os.environ.get('VK_TOKEN', '')
    if not tok:
        return None, 'нет VK_TOKEN'
    prm.update(access_token=tok, v='5.199')
    u = f'https://api.vk.com/method/{method}?' + urllib.parse.urlencode(prm)
    try:
        raw = EC._DIRECT.open(urllib.request.Request(
            u, headers={'User-Agent': getattr(EC.VC, 'UA', 'Mozilla/5.0')}),
            timeout=20).read()
        d = json.loads(EC._раскодировать(raw, 'charset=utf-8'))
    except Exception as ex:  # noqa: BLE001
        return None, f'{type(ex).__name__}: {str(ex)[:60]}'
    if d.get('error'):
        return None, 'vk:' + str((d['error'] or {}).get('error_msg'))[:70]
    return d.get('response'), ''


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    старт = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    d = json.load(open(БАЗА, encoding='utf-8'))
    строки = []
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, list):
                строки += v
    else:
        строки = d
    по_инн = {}
    for x in строки:
        i = str(x.get('inn') or '').strip()
        if i and i not in по_инн:
            по_инн[i] = x
    con = sqlite3.connect(EDB.DB_PATH)
    cur = con.cursor()
    пул = []
    for inn, x in по_инн.items():
        r = cur.execute('SELECT name, site FROM companies WHERE inn=?', (inn,)).fetchone()
        if not r or not (r[1] or ''):
            continue
        пул.append({'inn': inn, 'name': r[0] or str(x.get('name') or ''), 'site': r[1]})
    пул = пул[старт:]

    кэш = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
    P('pagecache:', кэш, 'существует:', os.path.isdir(кэш),
      'файлов:', len(os.listdir(кэш)) if os.path.isdir(кэш) else 0)
    P('пул с сайтом:', len(пул), '| сканируем до', n, 'или', БЮДЖЕТ, 'сек')

    ст = {'просмотрено': 0, 'слаг_есть': 0, 'группа_есть': 0, 'блок_контактов': 0,
          'контактов_всего': 0, 'с_должностью': 0, 'людей_с_фио': 0,
          'email_в_контактах': 0, 'тел_в_контактах': 0, 'из_кэша': 0}
    слаги = []
    t0 = time.time()
    for c in пул:
        if ст['просмотрено'] >= n or (time.time() - t0) > БЮДЖЕТ:
            break
        ст['просмотрено'] += 1
        есть_кэш = os.path.exists(os.path.join(кэш, f'{c["inn"]}.json.gz'))
        ст['из_кэша'] += 1 if есть_кэш else 0
        try:
            слаг = EC.vk_slug_from_site(c)
        except Exception as ex:  # noqa: BLE001
            слаг = ''
            P('   слаг упал', c['inn'], type(ex).__name__)
        if слаг:
            ст['слаг_есть'] += 1
            слаги.append((c, слаг, есть_кэш))
            P(f'   слаг: {c["inn"]} {c["site"][:28]} -> vk.com/{слаг} (кэш={есть_кэш})')

    P('--- слагов найдено:', len(слаги), 'за', round(time.time() - t0), 'сек')

    примеры = []
    for c, слаг, _ in слаги:
        resp, err = вк('groups.getById', group_ids=слаг,
                       fields='contacts,site,description,members_count,status')
        груп = (resp.get('groups') if isinstance(resp, dict) else resp) or []
        if not груп:
            P(f'   [гр-] {слаг}: {err[:70]}')
            continue
        g = груп[0]
        ст['группа_есть'] += 1
        конт = [x for x in (g.get('contacts') or []) if isinstance(x, dict)]
        if конт:
            ст['блок_контактов'] += 1
        ст['контактов_всего'] += len(конт)
        uids = [str(x.get('user_id')) for x in конт if x.get('user_id')]
        имена = {}
        if uids:
            u, uerr = вк('users.get', user_ids=','.join(uids[:20]))
            for p in (u or []):
                имена[str(p.get('id'))] = (
                    f"{p.get('first_name', '')} {p.get('last_name', '')}".strip())
        for x in конт:
            должн = (x.get('desc') or '').strip()
            фио = имена.get(str(x.get('user_id')), '')
            if должн:
                ст['с_должностью'] += 1
            if фио:
                ст['людей_с_фио'] += 1
            if x.get('email'):
                ст['email_в_контактах'] += 1
            if x.get('phone'):
                ст['тел_в_контактах'] += 1
            if (должн or фио) and len(примеры) < 20:
                примеры.append({'компания': c['name'][:34], 'слаг': слаг,
                                'фио': фио, 'должность': должн,
                                'тел': x.get('phone') or '', 'email': x.get('email') or ''})
        оп = str(g.get('description') or '')
        P(f'   [гр+] {слаг} «{str(g.get("name"))[:30]}» участников='
          f'{g.get("members_count")} контактов={len(конт)} описание={len(оп)}симв')
        # люди в ОПИСАНИИ группы
        if оп:
            for m in list(EC._POST_RE.finditer(оп))[:2]:
                окно = оп[max(0, m.start() - 100):m.start() + 120].replace('\n', ' ')
                P(f'        описание[должность]: …{окно}…')

    P('')
    for e in примеры:
        P('  ЧЕЛОВЕК:', json.dumps(e, ensure_ascii=False))
    P('ИТОГ ВК: ' + json.dumps(ст, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001
        P('!! упало:', traceback.format_exc()[-700:].replace('\n', ' | '))
