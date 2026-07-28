# -*- coding: utf-8 -*-
"""Реквизиты ЕГРЮЛ по ИНН через DaData -> durable-таблица requisites в enrich.db.

Зачем. В карточке обзвона КПП/ОГРН/ОПФ/дата регистрации/учредители пустовали у
479 компаний из 951: выгрузка обзвона (obzvon-index) и её же копия в seo.db
покрывают лишь 426 ИНН, а enrich.db хранит ОГРН всего у 31. DaData findById даёт
эти поля официально и бесплатно (10k запросов в сутки), токен уже в окружении
панели.

Durability (правило после рестарта 25.07): пишем СРАЗУ в enrich.db и в
requisites.jsonl с fsync, а не в возвращаемый JSON. Скрипт резюмируемый —
повторный запуск берёт только тех, кого ещё нет в таблице.

Запуск: python _ops_dadata_req.py [--force] [--limit N] [--budget SEC]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

CENTRO = r'C:\seostat\data\centrifugal.db'
ENR = r'C:\sender\enrich.db'
JSONL = r'C:\sender\_ops\requisites.jsonl'
API = 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party'
TOKEN = os.environ.get('DADATA_TOKEN', '')

DDL = """
create table if not exists requisites (
  inn TEXT PRIMARY KEY,
  ogrn TEXT, kpp TEXT, opf TEXT, opf_full TEXT,
  reg_date TEXT, liq_date TEXT, status TEXT,
  name_short TEXT, name_full TEXT, address TEXT,
  director TEXT, director_post TEXT, director_inn TEXT,
  founders TEXT, managers TEXT, capital TEXT, okpo TEXT,
  okved_main TEXT, okved_all TEXT, employees TEXT,
  branch_count TEXT, src TEXT, updated_at TEXT, raw TEXT
)
"""
FIELDS = ['inn', 'ogrn', 'kpp', 'opf', 'opf_full', 'reg_date', 'liq_date', 'status',
          'name_short', 'name_full', 'address', 'director', 'director_post',
          'director_inn', 'founders', 'managers', 'capital', 'okpo', 'okved_main',
          'okved_all', 'employees', 'branch_count', 'src', 'updated_at', 'raw']


def _date(ms):
    """DaData отдаёт даты миллисекундами эпохи; в карточке нужен ISO-день."""
    if not ms:
        return None
    try:
        return time.strftime('%Y-%m-%d', time.gmtime(int(ms) / 1000))
    except (TypeError, ValueError, OSError):
        return None


def _people(arr):
    """founders/managers -> «ФИО (доля/должность)» через « | »."""
    out = []
    for it in arr or []:
        if not isinstance(it, dict):
            continue
        name = it.get('name') or ((it.get('fio') or {}).get('surname') and ' '.join(
            x for x in ((it.get('fio') or {}).get('surname'),
                        (it.get('fio') or {}).get('name'),
                        (it.get('fio') or {}).get('patronymic')) if x))
        if not name:
            continue
        extra = it.get('post')
        share = it.get('share') or {}
        if not extra and isinstance(share, dict) and share.get('value') is not None:
            t = share.get('type')
            extra = (f"{share['value']}%" if t == 'PERCENT'
                     else f"{share['value']} {t or ''}".strip())
        out.append(f'{name} ({extra})' if extra else str(name))
    return ' | '.join(out) or None


def parse(d):
    name = d.get('name') or {}
    opf = d.get('opf') or {}
    state = d.get('state') or {}
    mgmt = d.get('management') or {}
    addr = d.get('address') or {}
    cap = d.get('capital') or {}
    okveds = d.get('okveds') or []
    okv_all = ' | '.join(
        f"{o.get('code')} {(o.get('name') or '')[:70]}".strip()
        for o in okveds if isinstance(o, dict) and o.get('code')) or None
    return {
        'inn': d.get('inn'),
        'ogrn': d.get('ogrn'),
        'kpp': d.get('kpp'),
        'opf': opf.get('short') or opf.get('full'),
        'opf_full': opf.get('full'),
        'reg_date': _date(state.get('registration_date')) or _date(d.get('ogrn_date')),
        'liq_date': _date(state.get('liquidation_date')),
        'status': state.get('status'),
        'name_short': name.get('short_with_opf') or name.get('short'),
        'name_full': name.get('full_with_opf') or name.get('full'),
        'address': addr.get('value') if isinstance(addr, dict) else None,
        'director': mgmt.get('name'),
        'director_post': mgmt.get('post'),
        # ИНН руководителя DaData в findById не отдаёт — колонку оставляем пустой,
        # её заполняет справочник обзвона там, где он есть
        'director_inn': None,
        'founders': _people(d.get('founders')),
        'managers': _people(d.get('managers')),
        'capital': (str(cap.get('value')) if isinstance(cap, dict)
                    and cap.get('value') is not None else None),
        'okpo': d.get('okpo'),
        'okved_main': d.get('okved'),
        'okved_all': okv_all,
        'employees': (str(d.get('employee_count'))
                      if d.get('employee_count') is not None else None),
        'branch_count': (str(d.get('branch_count'))
                         if d.get('branch_count') is not None else None),
    }


def lookup(inn):
    body = json.dumps({'query': str(inn), 'count': 1}).encode('utf-8')
    req = urllib.request.Request(API, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Authorization': f'Token {TOKEN}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    sugg = data.get('suggestions') or []
    if not sugg:
        return None
    # если по ИНН несколько записей (филиалы), берём головную — у неё нет КПП
    # с признаком филиала; DaData и так сортирует головную первой
    return sugg[0].get('data') or {}


def main():
    force = '--force' in sys.argv
    limit = 0
    budget = 700.0
    for i, a in enumerate(sys.argv):
        if a == '--limit' and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if a == '--budget' and i + 1 < len(sys.argv):
            budget = float(sys.argv[i + 1])

    if not TOKEN:
        print(json.dumps({'итог': 'ОТКАЗ: нет DADATA_TOKEN'}, ensure_ascii=False))
        return

    import sqlite3
    ce = sqlite3.connect(f'file:{CENTRO}?mode=ro', uri=True, timeout=60)
    inns = [str(r[0]) for r in ce.execute('select inn from company order by inn')]
    ce.close()

    db = sqlite3.connect(ENR, timeout=120)
    db.execute(DDL)
    # догоняем колонки, если таблица осталась от прошлой версии скрипта
    have = {r[1] for r in db.execute('pragma table_info(requisites)')}
    for col in FIELDS:
        if col not in have:
            db.execute(f'alter table requisites add column {col} TEXT')
    db.commit()
    done = {r[0] for r in db.execute(
        "select inn from requisites where coalesce(ogrn,'')<>''")}
    todo = inns if force else [i for i in inns if i not in done]
    if limit:
        todo = todo[:limit]

    os.makedirs(os.path.dirname(JSONL), exist_ok=True)
    jl = open(JSONL, 'a', encoding='utf-8')

    t0 = time.time()
    ok = miss = err = 0
    last_err = None
    for n, inn in enumerate(todo, 1):
        if time.time() - t0 > budget:
            break
        try:
            d = lookup(inn)
        except urllib.error.HTTPError as e:
            err += 1
            last_err = f'HTTP {e.code} на {inn}'
            # 429/403 — упёрлись в лимит или токен; дальше долбить бессмысленно
            if e.code in (403, 429):
                break
            time.sleep(1.0)
            continue
        except Exception as e:  # noqa: BLE001
            err += 1
            last_err = f'{type(e).__name__}: {str(e)[:80]}'
            time.sleep(1.0)
            continue

        if not d:
            miss += 1
            row = {'inn': inn, 'src': 'dadata', 'status': None}
        else:
            row = parse(d)
            row['inn'] = row.get('inn') or inn
            row['src'] = 'dadata'
            ok += 1
        row['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S')
        row['raw'] = json.dumps(d, ensure_ascii=False) if d else None

        db.execute(
            'insert or replace into requisites ({}) values ({})'.format(
                ','.join(FIELDS), ','.join('?' for _ in FIELDS)),
            [row.get(f) for f in FIELDS])
        if n % 25 == 0:
            db.commit()
        jl.write(json.dumps({k: row.get(k) for k in FIELDS if k != 'raw'},
                            ensure_ascii=False) + '\n')
        if n % 25 == 0:
            jl.flush()
            os.fsync(jl.fileno())
        # 10k/сутки бесплатно, но частить незачем: ~7 запросов в секунду
        time.sleep(0.14)

    db.commit()
    jl.flush()
    os.fsync(jl.fileno())
    total = db.execute(
        "select count(*) from requisites where coalesce(ogrn,'')<>''").fetchone()[0]
    db.close()
    jl.close()
    print(json.dumps({
        'всего_ИНН': len(inns), 'в_очереди_было': len(todo),
        'получено': ok, 'не_найдено_в_ЕГРЮЛ': miss, 'ошибок': err,
        'последняя_ошибка': last_err,
        'в_таблице_с_ОГРН': total, 'осталось': len(inns) - total,
        'секунд': round(time.time() - t0, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
