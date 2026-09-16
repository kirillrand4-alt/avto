# -*- coding: utf-8 -*-
"""Миграция схемы под ведение объекта во времени (ТЗ, задачи 5 и 6).

Что делает:
  1. ALTER TABLE signals ADD COLUMN stage / object_key / event_date / stage_ts;
  2. CREATE TABLE signal_history(object_key, inn, stage, ts, source_url, ...);
  3. индексы по object_key, event_date, stage;
  4. простановка задним числом по уже накопленным строкам `signals`
     (`stage`, `object_key`, `event_date`, `stage_ts`) и сборка истории
     переходов в `signal_history`.

ИДЕМПОТЕНТНОСТЬ. Повторный запуск не ломается и не плодит дублей:
  * колонки добавляются через try/except (как это уже сделано в `enrich_db.py`);
  * таблица и индексы — через IF NOT EXISTS;
  * бэкфилл по умолчанию трогает только строки, где поле ещё пустое
    (`--force` пересчитывает всё заново: понадобится, когда поправят словари
    в `stadii.py` и стадии надо будет пересчитать);
  * `signal_history` имеет UNIQUE(object_key, stage, source_url), запись идёт
    через INSERT OR IGNORE — второй прогон добавит 0 строк.

ЗАПУСК (на сервере, где лежит база):
    python migraciya_stadii.py --dry-run              # только показать план
    python migraciya_stadii.py                        # применить
    python migraciya_stadii.py --db C:\\sender\\enrich.db --force
    python migraciya_stadii.py --dry-run --limit 200  # прикинуть на 200 строках

`--dry-run` открывает базу в режиме ТОЛЬКО ДЛЯ ЧТЕНИЯ (`mode=ro`) — ошибиться
и записать в боевую базу невозможно физически, а не по договорённости.
Он печатает: какие колонки появятся, сколько строк будет затронуто, как
разложатся стадии и даты, и 10 примеров «было -> станет».
"""
import argparse
import collections
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stadii as S  # noqa: E402

DB_DEFAULT = r'C:\sender\enrich.db'

# Новые колонки signals. event_date_src хранит, ОТКУДА взята дата
# ('ts' — из источника, 'updated_at' — дата записи): без него нельзя отличить
# настоящую дату события от подстановки, а по свежести звонят.
NEW_COLS = (
    ('stage', 'INTEGER'),        # 0..4, см. stadii.STAGE_NAMES
    ('object_key', 'TEXT'),      # ключ карточки объекта
    ('event_date', 'TEXT'),      # 'YYYY-MM-DD'
    ('event_date_src', 'TEXT'),  # ts | published | updated_at | ''
    ('stage_ts', 'TEXT'),        # когда стадия у этой строки зафиксирована
)

DDL_HISTORY = """
CREATE TABLE IF NOT EXISTS signal_history(
  object_key TEXT,
  inn        TEXT,
  stage      INTEGER,
  ts         TEXT,        -- дата перехода (event_date строки-основания)
  source_url TEXT,        -- чем подтверждён переход: ссылка на новость
  event_type TEXT,
  what       TEXT,
  created_at TEXT,
  UNIQUE(object_key, stage, source_url));
"""

DDL_INDEXES = (
    'CREATE INDEX IF NOT EXISTS ix_sig_objkey ON signals(object_key)',
    'CREATE INDEX IF NOT EXISTS ix_sig_evdate ON signals(event_date)',
    'CREATE INDEX IF NOT EXISTS ix_sig_stage ON signals(stage)',
    'CREATE INDEX IF NOT EXISTS ix_hist_objkey ON signal_history(object_key)',
    'CREATE INDEX IF NOT EXISTS ix_hist_inn ON signal_history(inn)',
    'CREATE INDEX IF NOT EXISTS ix_hist_ts ON signal_history(ts)',
)

def _sel(cx):
    """SELECT для бэкфилла. Новых колонок может ещё не быть (dry-run до ALTER) —
    тогда подставляем NULL, чтобы запрос не падал и строка считалась пустой."""
    est = _cols(cx, 'signals')
    def c(name):
        return 's.%s' % name if name in est else 'NULL'
    return ("SELECT s.rowid, s.ts, s.updated_at, s.event_type, s.what, s.inn, "
            "s.source_url, COALESCE(c.region,''), %s, %s, %s "
            "FROM signals s LEFT JOIN companies c ON c.inn=s.inn"
            % (c('stage'), c('object_key'), c('event_date')))


def _cols(cx, table):
    return {r[1] for r in cx.execute('PRAGMA table_info(%s)' % table).fetchall()}


def _has_table(cx, name):
    return bool(cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (name,)).fetchone())


def dobavit_kolonki(cx, prosto_pokazat=False):
    """ALTER TABLE на недостающие колонки. Возврат: список добавленных имён."""
    est = _cols(cx, 'signals')
    dobavleno = []
    for name, typ in NEW_COLS:
        if name in est:
            continue
        dobavleno.append(name)
        if not prosto_pokazat:
            try:
                cx.execute('ALTER TABLE signals ADD COLUMN %s %s' % (name, typ))
            except sqlite3.OperationalError:
                pass     # колонка уже есть (гонка с другим прогоном) — не беда
    return dobavleno


def backfill(cx, force=False, limit=0, prosto_pokazat=False):
    """Простановка stage/object_key/event_date по накопленным строкам.

    Без `force` трогаем только строки, где поле пустое: повторный прогон
    ничего не переписывает. С `force` пересчитываем всё (после правки словарей).
    """
    rows = cx.execute(_sel(cx)).fetchall()
    if limit:
        rows = rows[:limit]
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    st_cnt = collections.Counter()
    src_cnt = collections.Counter()
    prim = []
    upd = 0
    hist = {}    # object_key -> {stage: (ts, url, et, what, inn)} — ранняя дата
    for (rid, ts, ua, et, wh, inn, url, reg,
         st_est, key_est, date_est) in rows:
        st = S.stage_of(et, wh)
        key = S.object_key(reg, wh, inn)
        date, src = S.event_date_of(ts, ua)
        st_cnt[st] += 1
        src_cnt[src or 'нет'] += 1
        nuzhno = force or st_est is None or not key_est or not date_est
        if len(prim) < 10:
            prim.append((rid, (ts or '')[:28], (et or '')[:18], (wh or '')[:34],
                         st, key, date or '-', src or '-'))
        # история: по одной строке на (объект, стадия) — самое РАННЕЕ основание
        if key and st:
            b = hist.setdefault(key, {})
            if st not in b or (date or '9999') < (b[st][0] or '9999'):
                b[st] = (date, url or '', et or '', wh or '', inn or '')
        if not nuzhno:
            continue
        upd += 1
        if not prosto_pokazat:
            cx.execute('UPDATE signals SET stage=?, object_key=?, event_date=?, '
                       'event_date_src=?, stage_ts=COALESCE(stage_ts,?) WHERE rowid=?',
                       (st, key, date, src, date or now, rid))
    n_hist = 0
    if not prosto_pokazat:
        for key, b in hist.items():
            for st, (date, url, et, wh, inn) in b.items():
                cur = cx.execute(
                    'INSERT OR IGNORE INTO signal_history'
                    '(object_key,inn,stage,ts,source_url,event_type,what,created_at) '
                    'VALUES(?,?,?,?,?,?,?,?)',
                    (key, inn, st, date, url, et, wh, now))
                n_hist += cur.rowcount
        cx.commit()
    else:
        n_hist = sum(len(b) for b in hist.values())
    perehody = sum(1 for b in hist.values() if len(b) > 1)
    return dict(vsego=len(rows), obnovleno=upd, stadii=st_cnt, istochnik_daty=src_cnt,
                primery=prim, istoriya=n_hist, objectov=len(hist), s_perehodom=perehody)


def main():
    ap = argparse.ArgumentParser(description='Миграция signals под стадии и даты')
    ap.add_argument('--db', default=DB_DEFAULT)
    ap.add_argument('--dry-run', action='store_true',
                    help='ничего не менять, база открывается только на чтение')
    ap.add_argument('--force', action='store_true',
                    help='пересчитать stage/object_key/event_date даже у заполненных')
    ap.add_argument('--limit', type=int, default=0, help='взять только N строк (проба)')
    ap.add_argument('--no-backfill', action='store_true',
                    help='только схема, без простановки задним числом')
    a = ap.parse_args()

    suhoy = a.dry_run
    if suhoy:
        cx = sqlite3.connect('file:%s?mode=ro' % a.db.replace('\\', '/'), uri=True)
        print('=== DRY-RUN: база открыта ТОЛЬКО НА ЧТЕНИЕ, ничего не изменится ===')
    else:
        if not os.path.exists(a.db):
            print('базы нет: %s' % a.db)
            return 2
        cx = sqlite3.connect(a.db, timeout=60)
        cx.execute('PRAGMA journal_mode=WAL')
    print('база: %s' % a.db)

    est = _cols(cx, 'signals')
    print('--- 1. колонки signals ---')
    for name, typ in NEW_COLS:
        print('   %-15s %-8s %s' % (name, typ, 'уже есть' if name in est else 'БУДЕТ ДОБАВЛЕНА'))
    dob = dobavit_kolonki(cx, prosto_pokazat=suhoy)
    print('   добавлено колонок: %d' % len(dob))

    print('--- 2. таблица signal_history ---')
    if _has_table(cx, 'signal_history'):
        n = cx.execute('SELECT COUNT(*) FROM signal_history').fetchone()[0]
        print('   уже есть, строк: %d' % n)
    else:
        print('   БУДЕТ СОЗДАНА: object_key, inn, stage, ts, source_url, event_type, '
              'what, created_at; UNIQUE(object_key, stage, source_url)')
        if not suhoy:
            cx.executescript(DDL_HISTORY)

    print('--- 3. индексы ---')
    for ddl in DDL_INDEXES:
        имя = ddl.split('IF NOT EXISTS ')[1].split(' ')[0]
        print('   %s' % имя)
        if not suhoy:
            try:
                cx.execute(ddl)
            except sqlite3.OperationalError as e:
                print('   пропущен (%s)' % e)
    if not suhoy:
        cx.commit()

    if a.no_backfill:
        print('--- 4. простановка задним числом: пропущена (--no-backfill) ---')
        return 0

    print('--- 4. простановка задним числом %s---' % ('(предпросмотр) ' if suhoy else ''))
    if suhoy and not est & {'stage', 'object_key', 'event_date'}:
        print('   колонок ещё нет — считаю, что все строки пустые')
    r = backfill(cx, force=a.force, limit=a.limit, prosto_pokazat=suhoy)
    print('   строк в signals: %d, будет обновлено: %d' % (r['vsego'], r['obnovleno']))
    print('   стадии: ' + ', '.join('%d %s %d (%.1f%%)'
                                    % (s, S.STAGE_NAMES[s], r['stadii'][s],
                                       100.0 * r['stadii'][s] / max(1, r['vsego']))
                                    for s in (1, 2, 3, 4, 0)))
    print('   дата события: ' + ', '.join('%s %d' % (k, v)
                                          for k, v in r['istochnik_daty'].most_common()))
    print('   объектов (object_key): %d, из них с >1 стадией: %d; строк истории: %d'
          % (r['objectov'], r['s_perehodom'], r['istoriya']))
    print('   --- примеры «было -> станет» ---')
    for rid, ts, et, wh, st, key, date, src in r['primery']:
        print('   #%-7s ts=%-28s %-18s | ст.%d %-22s %s (%s)'
              % (rid, ts or '""', et, st, S.STAGE_NAMES[st], date, src))
    print('=== %s ===' % ('DRY-RUN окончен, база не тронута' if suhoy else 'миграция применена'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
