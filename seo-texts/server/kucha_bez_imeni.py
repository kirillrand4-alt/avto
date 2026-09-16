# -*- coding: utf-8 -*-
"""«Отдельная куча» безымянных событий: таблица `signals_bez_imeni` + повторный проход.

Решение владельца 16.09 (TZ-RANNEE-SOBYTIE.md, задача 4): событие, у которого ни один
из шести путей `doopredelenie.py` не дал юрлица, УХОДИТ В КУЧУ, А НЕ В УДАЛЕНИЕ —
имя может появиться через месяц (вышла вторая новость, компания стала резидентом ОЭЗ,
в ЕГРЗ легло заключение). Куча живёт в enrich.db, рядом с `signals`: по правилу
durability из CLAUDE.md результат серверной работы обязан лежать в серверном
хранилище, а не в возвращаемом JSON.

Что умеет:
  * `migraciya(...)`   — идемпотентно создать таблицу и индексы; `--dry-run` только
                         печатает план и НИЧЕГО не пишет (базу открывает на чтение);
  * `polozhit(...)`    — положить событие в кучу (повтор того же события не плодит
                         строк, а увеличивает счётчик попыток);
  * `povtornyy_prohod(...)` — переспросить кучу: берём те события, чья прошлая попытка
                         была достаточно давно (7 → 30 → 90 → 180 дней), и гоняем по
                         ним `doopredelit`. Успех → строка закрывается, событие можно
                         отдать в `signals` обычным путём;
  * `statistika(...)`  — что в куче лежит и что с ней происходит.

Чего НЕ умеет: сама решать, что имя найдено. Это `doopredelenie.doopredelit()`, со
своей защитой от тёзок. Куча только хранит, отмеряет паузы и считает попытки.

ЗАПУСК НА СЕРВЕРЕ — за главной сессией. Здесь ничего не запускается автоматически,
а любая запись требует явного `--primenit` (по умолчанию все команды сухие).

CLI:
    python kucha_bez_imeni.py migraciya --dry-run
    python kucha_bez_imeni.py migraciya --primenit
    python kucha_bez_imeni.py statistika
    python kucha_bez_imeni.py prohod --limit 100 --dry-run
    python kucha_bez_imeni.py prohod --limit 100 --primenit [--v-signals]
"""
import json
import os
import re
import sqlite3
import sys
import time

DB_PATH = os.environ.get('ENRICH_DB', os.path.join(
    os.environ.get('SENDER_DIR', r'C:\sender'), 'enrich.db'))
# durable-дубль: кучу дублируем построчно в jsonl с fsync (урок рестарта 2026-07-25 —
# результат серверного op должен пережить и падение базы, и откат песочницы)
JSONL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kucha_bez_imeni.jsonl')

TABLE = 'signals_bez_imeni'

# Схема кучи. Порядок колонок = порядок разговора о событии: что это, откуда,
# когда, что уже пробовали, чем кончилось.
_SCHEMA = [
    ('CREATE TABLE IF NOT EXISTS %s(\n'
     '  kluch TEXT PRIMARY KEY,        -- канон-URL события (или хэш текста, если ссылки нет)\n'
     '  title TEXT,                    -- заголовок новости как пришёл\n'
     '  what TEXT,                     -- суть события от классификатора\n'
     '  source TEXT,                   -- имя источника (издание/паблик)\n'
     '  source_url TEXT,               -- ссылка-доказательство\n'
     '  collector TEXT,                -- каким коллектором поймано\n'
     '  region TEXT,                   -- регион события\n'
     '  otrasl TEXT,                   -- отрасль/класс объекта (завод, фабрика, рудник...)\n'
     '  event_type TEXT,               -- тип события от классификатора\n'
     '  sum TEXT,                      -- сумма инвестиций, если названа\n'
     '  hotness INTEGER,               -- 1-5 от классификатора\n'
     '  event_date TEXT,               -- дата события, ISO YYYY-MM-DD (нормализованная)\n'
     '  ts_pervyy TEXT,                -- когда впервые положили в кучу\n'
     '  ts_popytki TEXT,               -- когда в последний раз пробовали доопределить\n'
     '  popytok INTEGER DEFAULT 0,     -- сколько раз пробовали\n'
     '  puti_probovali TEXT,           -- какие пути прогоняли (json-список)\n'
     '  uliki TEXT,                    -- что именно мешало (json-список последней попытки)\n'
     '  status TEXT,                   -- ждёт | доопределено | спит\n'
     '  company TEXT,                  -- имя, если в итоге доопределилось\n'
     '  inn TEXT,                      -- ИНН, если доопределился\n'
     '  uverennost TEXT,               -- high | low у доопределения\n'
     '  put TEXT,                      -- каким путём доопределилось\n'
     '  v_signals INTEGER DEFAULT 0,   -- перенесено ли уже в signals\n'
     '  updated_at TEXT)' % TABLE),
    'CREATE INDEX IF NOT EXISTS ix_kbi_status ON %s(status)' % TABLE,
    'CREATE INDEX IF NOT EXISTS ix_kbi_popytka ON %s(ts_popytki)' % TABLE,
    'CREATE INDEX IF NOT EXISTS ix_kbi_region ON %s(region)' % TABLE,
    'CREATE INDEX IF NOT EXISTS ix_kbi_data ON %s(event_date)' % TABLE,
]

# Ожидаемые колонки (для миграции старой таблицы: добавляем недостающие по одной).
_KOLONKI = [
    ('title', 'TEXT'), ('what', 'TEXT'), ('source', 'TEXT'), ('source_url', 'TEXT'),
    ('collector', 'TEXT'), ('region', 'TEXT'), ('otrasl', 'TEXT'), ('event_type', 'TEXT'),
    ('sum', 'TEXT'), ('hotness', 'INTEGER'), ('event_date', 'TEXT'), ('ts_pervyy', 'TEXT'),
    ('ts_popytki', 'TEXT'), ('popytok', 'INTEGER'), ('puti_probovali', 'TEXT'),
    ('uliki', 'TEXT'), ('status', 'TEXT'), ('company', 'TEXT'), ('inn', 'TEXT'),
    ('uverennost', 'TEXT'), ('put', 'TEXT'), ('v_signals', 'INTEGER'), ('updated_at', 'TEXT'),
]

# Пауза до следующей попытки по номеру попытки. Смысл: имя всплывает не мгновенно,
# а с выходом второй новости/заключения ЕГРЗ; чаще раза в неделю дёргать нечего,
# реже полугода — событие протухнет. Последнее значение повторяется бесконечно:
# из кучи НИЧЕГО НЕ УДАЛЯЕТСЯ.
PAUZY_DNEY = [7, 30, 90, 180]


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def _kanon_url(u):
    """Канон-URL для ключа. Переиспользуем боевой `news_scan._norm_url`, если он
    импортируется; иначе — своя усечённая нормализация (без utm/www/якоря)."""
    try:
        import news_scan as NS
        return NS._norm_url(u)
    except Exception:  # noqa: BLE001
        v = (u or '').strip().lower().split('#')[0]
        v = re.sub(r'[?&](utm_[^=]+|yclid|gclid|from|_openstat)=[^&]*', '', v)
        return re.sub(r'^https?://(www\.)?', '', v).rstrip('/?&')


def kluch_sobytiya(sob):
    """Ключ строки кучи: канон-URL, а без ссылки — хэш заголовка и сути."""
    u = _kanon_url(sob.get('source_url') or sob.get('link') or '')
    if u:
        return u[:300]
    import hashlib
    h = hashlib.sha1((((sob.get('title') or '') + '|' + (sob.get('what') or ''))
                      ).encode('utf-8', 'replace')).hexdigest()
    return 'hash:' + h


def _dney_nazad(ts):
    """Сколько дней прошло с отметки 'YYYY-MM-DDTHH:MM:SS' (или None)."""
    if not ts:
        return None
    try:
        import datetime as _dt
        d = _dt.datetime.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')
        return (_dt.datetime.now() - d).days
    except Exception:  # noqa: BLE001
        return None


def pora_probovat(popytok, ts_popytki):
    """Пора ли повторить попытку: пауза берётся по номеру попытки из PAUZY_DNEY."""
    d = _dney_nazad(ts_popytki)
    if d is None:
        return True
    i = min(max(int(popytok or 1), 1), len(PAUZY_DNEY)) - 1
    return d >= PAUZY_DNEY[i]


# ----------------------------------------------------------------- миграция
def migraciya(db_path=None, dry_run=True, out=print):
    """Идемпотентно завести кучу. `dry_run=True` — только план, база открывается на ЧТЕНИЕ.

    Идемпотентность: CREATE TABLE/INDEX IF NOT EXISTS + ALTER TABLE только для
    недостающих колонок (сверяется по PRAGMA table_info). Повторный запуск на уже
    мигрированной базе не делает ничего и это видно в ответе (`plan` пуст).
    """
    db_path = db_path or DB_PATH
    plan, est = [], {}
    if not os.path.isfile(db_path):
        # базы ещё нет: в сухом прогоне не создаём её ради проверки — печатаем полный план
        out('базы %s нет' % db_path)
        for s in _SCHEMA:
            out('  ВЫПОЛНИЛОСЬ БЫ: %s' % s.split('\n')[0][:110])
        if dry_run:
            return {'db': db_path, 'dry_run': True, 'plan': list(_SCHEMA), 'bylo': {'net_bazy': True}}
    if dry_run:
        cx = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    else:
        cx = sqlite3.connect(db_path, timeout=30)
    try:
        est_tablica = bool(cx.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone())
        if not est_tablica:
            plan += _SCHEMA
        else:
            imeyushchiesya = {r[1] for r in cx.execute('PRAGMA table_info(%s)' % TABLE)}
            for name, typ in _KOLONKI:
                if name not in imeyushchiesya:
                    plan.append('ALTER TABLE %s ADD COLUMN %s %s' % (TABLE, name, typ))
            indeksy = {r[0] for r in cx.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?", (TABLE,))}
            for sql in _SCHEMA[1:]:
                nm = re.search(r'INDEX IF NOT EXISTS (\w+)', sql).group(1)
                if nm not in indeksy:
                    plan.append(sql)
            est['strok_v_kuche'] = cx.execute('SELECT COUNT(*) FROM %s' % TABLE).fetchone()[0]
        if dry_run:
            out('МИГРАЦИЯ (сухой прогон), база %s' % db_path)
            out('таблица %s существует: %s' % (TABLE, est_tablica))
            for s in plan:
                out('  ВЫПОЛНИЛОСЬ БЫ: %s' % s.split('\n')[0][:110])
            if not plan:
                out('  менять нечего — база уже в нужном виде')
        else:
            for s in plan:
                cx.execute(s)
            cx.commit()
            out('МИГРАЦИЯ применена: %d операций' % len(plan))
    finally:
        cx.close()
    return {'db': db_path, 'dry_run': dry_run, 'plan': plan, 'bylo': est}


# ----------------------------------------------------------------- запись в кучу
def polozhit(sob, rezultat=None, db_path=None, dry_run=True, out=None):
    """Положить безымянное событие в кучу (или отметить ещё одну неудачную попытку).

    sob      — событие как в news_scan (`title/what/region/source_url/...`);
    rezultat — что вернул `doopredelenie.doopredelit()` (чтобы сохранить улики и
               список пройденных путей). Можно не передавать.
    Идемпотентно по ключу: второй заход по тому же URL не плодит строку, а
    увеличивает `popytok`, обновляет `ts_popytki` и улики.
    """
    db_path = db_path or DB_PATH
    rez = rezultat or {}
    zapis = {
        'kluch': kluch_sobytiya(sob),
        'title': (sob.get('title') or '')[:500],
        'what': sob.get('what') or '',
        'source': sob.get('source_name') or sob.get('source') or '',
        'source_url': sob.get('source_url') or sob.get('link') or '',
        'collector': sob.get('collector') or '',
        'region': sob.get('region') or '',
        'otrasl': sob.get('otrasl') or _otrasl(sob),
        'event_type': sob.get('event_type') or '',
        'sum': str(sob.get('sum') or ''),
        'hotness': int(sob.get('hotness') or 0),
        'event_date': _event_date(sob),
        'puti_probovali': json.dumps(rez.get('probovali') or [], ensure_ascii=False),
        'uliki': json.dumps((rez.get('uliki') or [])[:20], ensure_ascii=False),
        'status': 'ждёт',
    }
    if dry_run:
        (out or print)('СУХО: в кучу легло бы %s | %s' % (zapis['kluch'][:60], zapis['title'][:60]))
        return zapis
    cx = sqlite3.connect(db_path, timeout=30)
    try:
        cx.execute(
            'INSERT INTO %s(kluch,title,what,source,source_url,collector,region,otrasl,'
            'event_type,sum,hotness,event_date,ts_pervyy,ts_popytki,popytok,puti_probovali,'
            'uliki,status,v_signals,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,0,?) '
            'ON CONFLICT(kluch) DO UPDATE SET popytok=popytok+1, ts_popytki=excluded.ts_popytki, '
            'uliki=excluded.uliki, puti_probovali=excluded.puti_probovali, '
            'updated_at=excluded.updated_at' % TABLE,
            (zapis['kluch'], zapis['title'], zapis['what'], zapis['source'], zapis['source_url'],
             zapis['collector'], zapis['region'], zapis['otrasl'], zapis['event_type'],
             zapis['sum'], zapis['hotness'], zapis['event_date'], _now(), _now(),
             zapis['puti_probovali'], zapis['uliki'], zapis['status'], _now()))
        cx.commit()
    finally:
        cx.close()
    _v_jsonl(dict(zapis, ts=_now(), op='polozhit'))
    return zapis


def _otrasl(sob):
    """Класс объекта из текста события (тот же словарь, что у доопределения)."""
    try:
        import doopredelenie as DP
        return ','.join(sorted(DP._klass_obekta(
            ' '.join([sob.get('title') or '', sob.get('what') or '']))))
    except Exception:  # noqa: BLE001
        return ''


def _event_date(sob):
    try:
        import doopredelenie as DP
        return DP._data_iso(sob.get('published') or sob.get('event_date') or sob.get('ts'))
    except Exception:  # noqa: BLE001
        return ''


def _v_jsonl(zap):
    """Durable-дубль строки кучи: append + fsync (переживает падение базы и рестарт)."""
    try:
        with open(JSONL, 'a', encoding='utf-8') as f:
            f.write(json.dumps(zap, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------- повторный проход
def povtornyy_prohod(db_path=None, limit=100, ctx=None, dry_run=True, v_signals=False,
                     min_dney=None, out=print):
    """Переспросить кучу: события, чья пауза вышла, снова прогнать через доопределение.

    limit     — сколько строк взять за раз (проход резюмируемый: следующая порция
                возьмётся по той же выборке, отметки попыток durable в базе);
    ctx       — `doopredelenie.Kontekst` (корпус, разрешение на платные пути и т.д.);
                по умолчанию собирается корпус из наших же событий и БЕЗ платных путей;
    dry_run   — считаем и печатаем, в базу не пишем;
    v_signals — успешно доопределённые сразу отдать в `signals` через `enrich_db`
                (только вместе с `--primenit` и только при `uverennost='high'` и ИНН);
    min_dney  — принудительная пауза вместо расписания PAUZY_DNEY (для ручного прогона).

    Возвращает сводку: сколько взяли, скольким нашли имя, каким путём.
    """
    import doopredelenie as DP
    db_path = db_path or DB_PATH
    if ctx is None:
        korpus = DP.Korpus.iz_bd(db_path)
        ctx = DP.Kontekst(korpus=korpus, razresheno_platit=False)
    cx = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True) if dry_run \
        else sqlite3.connect(db_path, timeout=30)
    cx.row_factory = sqlite3.Row
    itog = {'vzyato': 0, 'doopredeleno': 0, 'po_putyam': {}, 'v_signals': 0, 'primery': []}
    try:
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (TABLE,)).fetchone():
            out('таблицы %s ещё нет — сначала миграция' % TABLE)
            return itog
        rows = [dict(r) for r in cx.execute(
            'SELECT * FROM %s WHERE status<>? ORDER BY COALESCE(ts_popytki,ts_pervyy) '
            'LIMIT ?' % TABLE, ('доопределено', int(limit) * 4))]
        for r in rows:
            if itog['vzyato'] >= int(limit):
                break
            if min_dney is not None:
                d = _dney_nazad(r.get('ts_popytki'))
                if d is not None and d < int(min_dney):
                    continue
            elif not pora_probovat(r.get('popytok'), r.get('ts_popytki')):
                continue
            itog['vzyato'] += 1
            sob = {'title': r.get('title'), 'what': r.get('what'), 'region': r.get('region'),
                   'source_url': r.get('source_url'), 'source_name': r.get('source'),
                   'published': r.get('event_date'), 'event_type': r.get('event_type'),
                   'sum': r.get('sum'), 'hotness': r.get('hotness')}
            rez = DP.doopredelit(sob, ctx)
            popytok = int(r.get('popytok') or 0) + 1
            if rez.get('company'):
                itog['doopredeleno'] += 1
                itog['po_putyam'][rez['путь']] = itog['po_putyam'].get(rez['путь'], 0) + 1
                if len(itog['primery']) < 10:
                    itog['primery'].append({'title': (r.get('title') or '')[:70],
                                            'company': rez['company'], 'inn': rez.get('inn'),
                                            'путь': rez['путь'], 'uverennost': rez['uverennost']})
                if not dry_run:
                    cx.execute(
                        'UPDATE %s SET status=?, company=?, inn=?, uverennost=?, put=?, '
                        'uliki=?, popytok=?, ts_popytki=?, updated_at=? WHERE kluch=?' % TABLE,
                        ('доопределено', rez['company'], rez.get('inn') or '',
                         rez['uverennost'], rez['путь'],
                         json.dumps(rez.get('uliki') or [], ensure_ascii=False)[:4000],
                         popytok, _now(), _now(), r['kluch']))
                    cx.commit()
                    _v_jsonl({'op': 'doopredeleno', 'ts': _now(), 'kluch': r['kluch'],
                              'company': rez['company'], 'inn': rez.get('inn'),
                              'путь': rez['путь'], 'uverennost': rez['uverennost'],
                              'uliki': (rez.get('uliki') or [])[:20]})
                    if v_signals and rez.get('inn') and rez['uverennost'] == 'high':
                        itog['v_signals'] += _v_signals(r, rez, db_path)
            else:
                if not dry_run:
                    # спит = пауза растёт по расписанию; из кучи НЕ удаляем никогда
                    st = 'спит' if popytok >= len(PAUZY_DNEY) else 'ждёт'
                    cx.execute(
                        'UPDATE %s SET status=?, popytok=?, ts_popytki=?, uliki=?, '
                        'puti_probovali=?, updated_at=? WHERE kluch=?' % TABLE,
                        (st, popytok, _now(),
                         json.dumps((rez.get('uliki') or [])[:20], ensure_ascii=False)[:4000],
                         json.dumps(rez.get('probovali') or [], ensure_ascii=False),
                         _now(), r['kluch']))
                    cx.commit()
    finally:
        cx.close()
    out('ПРОХОД ПО КУЧЕ%s: взято %d, доопределено %d %s' % (
        ' (сухой)' if dry_run else '', itog['vzyato'], itog['doopredeleno'],
        itog['po_putyam'] or ''))
    for p in itog['primery']:
        out('  %s -> %s (%s, %s)' % (p['title'], p['company'], p['путь'], p['uverennost']))
    return itog


def _v_signals(row, rez, db_path):
    """Перенести доопределённое событие в `signals` штатным путём (enrich_db)."""
    try:
        import enrich_db as EDB
        db = EDB.EnrichDB(db_path)
        db.upsert_company(rez['inn'], name=rez['company'], region=row.get('region'))
        db.add_signal(rez['inn'], source=row.get('source') or 'куча',
                      event_type=row.get('event_type') or '',
                      what=(row.get('what') or '') + ' [имя доопределено: %s]' % rez['путь'],
                      sum=row.get('sum') or '', source_url=row.get('source_url') or '',
                      hotness=int(row.get('hotness') or 0), ts=row.get('event_date') or '',
                      inn_conf=rez['uverennost'])
        return 1
    except Exception:  # noqa: BLE001
        return 0


# ----------------------------------------------------------------- статистика
def statistika(db_path=None, out=print):
    """Что в куче: сколько ждёт, сколько спит, сколько доопределено, по регионам и путям."""
    db_path = db_path or DB_PATH
    cx = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
    res = {}
    try:
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (TABLE,)).fetchone():
            out('таблицы %s ещё нет — сначала миграция' % TABLE)
            return {'net_tablicy': True}
        res['vsego'] = cx.execute('SELECT COUNT(*) FROM %s' % TABLE).fetchone()[0]
        res['po_statusu'] = dict(cx.execute(
            'SELECT status, COUNT(*) FROM %s GROUP BY status' % TABLE).fetchall())
        res['po_putyam'] = dict(cx.execute(
            'SELECT put, COUNT(*) FROM %s WHERE put IS NOT NULL AND put<>"" GROUP BY put'
            % TABLE).fetchall())
        res['top_regiony'] = cx.execute(
            'SELECT region, COUNT(*) c FROM %s GROUP BY region ORDER BY c DESC LIMIT 8'
            % TABLE).fetchall()
        res['pora_probovat'] = sum(
            1 for popytok, ts in cx.execute('SELECT popytok, ts_popytki FROM %s '
                                            'WHERE status<>"доопределено"' % TABLE)
            if pora_probovat(popytok, ts))
    finally:
        cx.close()
    out('КУЧА %s: %s' % (TABLE, json.dumps(res, ensure_ascii=False)))
    return res


# ----------------------------------------------------------------- CLI
def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    cmd = a[0] if a else 'statistika'
    dry = '--primenit' not in a          # ПО УМОЛЧАНИЮ СУХО
    db = DB_PATH
    if '--db' in a:
        db = a[a.index('--db') + 1]
    lim = int(a[a.index('--limit') + 1]) if '--limit' in a else 100
    if cmd == 'migraciya':
        migraciya(db, dry_run=dry)
    elif cmd == 'prohod':
        min_d = int(a[a.index('--min-dney') + 1]) if '--min-dney' in a else None
        povtornyy_prohod(db, limit=lim, dry_run=dry, v_signals=('--v-signals' in a),
                         min_dney=min_d)
    elif cmd == 'statistika':
        statistika(db)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
