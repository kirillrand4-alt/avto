# -*- coding: utf-8 -*-
"""Единое хранилище обогащения (система-источник-истины) — SQLite, ключ ИНН, UPSERT.
Сюда пишут ВСЕ источники (news/no-site/ФРП/zakupki/Meyer) с тегом источника и
направления (kc=Компрессор Центр / meyer). Идемпотентно (дедуп по ИНН и по email),
резюмируемо (переживает рестарт). Живёт на сервере: C:\\sender\\enrich.db.

Схема:
  companies(inn PK, name, division, okved, region, pxr, site, activity,
            is_competitor, verified, best_email, phones, updated_at)
  emails(inn, email, role, person, mx_ok, source, updated_at, UNIQUE(inn,email))
  signals(inn, source, event_type, what, sum, source_url, hotness, ts, updated_at)

Использование как библиотека (из enrich_contacts): db=EnrichDB(); db.upsert_company(...);
db.add_email(...); db.add_signal(...). Как CLI: экспорт/статистика."""
import os
import sys
import json
import sqlite3
import time

DB_PATH = os.environ.get('ENRICH_DB', os.path.join(
    os.environ.get('SENDER_DIR', r'C:\sender'), 'enrich.db'))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies(
  inn TEXT PRIMARY KEY, name TEXT, division TEXT, okved TEXT, region TEXT, pxr REAL,
  site TEXT, activity TEXT, is_competitor INTEGER DEFAULT 0, verified TEXT,
  best_email TEXT, phones TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS emails(
  inn TEXT, email TEXT, role TEXT, person TEXT, mx_ok INTEGER, source TEXT,
  updated_at TEXT, UNIQUE(inn, email));
CREATE TABLE IF NOT EXISTS signals(
  inn TEXT, source TEXT, event_type TEXT, what TEXT, sum TEXT, source_url TEXT,
  hotness INTEGER, ts TEXT, updated_at TEXT, UNIQUE(inn, source, what));
CREATE INDEX IF NOT EXISTS ix_comp_div ON companies(division);
CREATE INDEX IF NOT EXISTS ix_comp_site ON companies(site);
CREATE INDEX IF NOT EXISTS ix_email_inn ON emails(inn);
CREATE INDEX IF NOT EXISTS ix_sig_inn ON signals(inn);
"""


class EnrichDB:
    def __init__(self, path=None, now=None):
        self.path = path or DB_PATH
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self.now = now or time.strftime('%Y-%m-%dT%H:%M:%S')
        self.cx = sqlite3.connect(self.path, timeout=30)
        self.cx.execute('PRAGMA journal_mode=WAL')
        self.cx.executescript(_SCHEMA)
        self.cx.commit()

    def upsert_company(self, inn, **f):
        """UPSERT компании. Непустые поля перезаписывают, пустые — НЕ затирают старое."""
        if not inn:
            return
        inn = str(inn)
        cols = ('name', 'division', 'okved', 'region', 'pxr', 'site', 'activity',
                'is_competitor', 'verified', 'best_email', 'phones')
        vals = {}
        for c in cols:
            v = f.get(c)
            if c == 'phones' and isinstance(v, (list, dict)):
                v = json.dumps(v, ensure_ascii=False)
            if c == 'is_competitor' and v is not None:
                v = 1 if v else 0
            if v not in (None, '', []):
                vals[c] = v
        exists = self.cx.execute('SELECT 1 FROM companies WHERE inn=?', (inn,)).fetchone()
        if exists:
            if vals:
                sets = ', '.join(f'{k}=?' for k in vals) + ', updated_at=?'
                self.cx.execute(f'UPDATE companies SET {sets} WHERE inn=?',
                                list(vals.values()) + [self.now, inn])
        else:
            keys = ['inn'] + list(vals) + ['updated_at']
            self.cx.execute(
                f'INSERT INTO companies({",".join(keys)}) VALUES({",".join("?"*len(keys))})',
                [inn] + list(vals.values()) + [self.now])
        self.cx.commit()

    def add_email(self, inn, email, role='', person='', mx_ok=None, source=''):
        if not (inn and email):
            return
        self.cx.execute(
            'INSERT INTO emails(inn,email,role,person,mx_ok,source,updated_at) '
            'VALUES(?,?,?,?,?,?,?) ON CONFLICT(inn,email) DO UPDATE SET '
            'role=CASE WHEN excluded.role!="" THEN excluded.role ELSE emails.role END, '
            'person=CASE WHEN excluded.person!="" THEN excluded.person ELSE emails.person END, '
            'mx_ok=COALESCE(excluded.mx_ok,emails.mx_ok), updated_at=excluded.updated_at',
            (str(inn), email.lower().strip(), role or '', person or '',
             (1 if mx_ok else 0) if mx_ok is not None else None, source or '', self.now))
        self.cx.commit()

    def add_signal(self, inn, source, event_type='', what='', sum='', source_url='', hotness=0, ts=''):
        if not inn:
            return
        self.cx.execute(
            'INSERT OR IGNORE INTO signals(inn,source,event_type,what,sum,source_url,hotness,ts,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?,?)',
            (str(inn), source or '', event_type or '', (what or '')[:400], sum or '',
             source_url or '', int(hotness or 0), ts or '', self.now))
        self.cx.commit()

    def stats(self):
        c = self.cx.execute
        return {
            'companies': c('SELECT COUNT(*) FROM companies').fetchone()[0],
            'with_site': c('SELECT COUNT(*) FROM companies WHERE site!=""').fetchone()[0],
            'with_email': c('SELECT COUNT(DISTINCT inn) FROM emails').fetchone()[0],
            'competitors': c('SELECT COUNT(*) FROM companies WHERE is_competitor=1').fetchone()[0],
            'emails_total': c('SELECT COUNT(*) FROM emails').fetchone()[0],
            'by_division': dict(c('SELECT division,COUNT(*) FROM companies GROUP BY division').fetchall()),
            'signals': c('SELECT COUNT(*) FROM signals').fetchone()[0],
        }

    def export_rows(self):
        """Плоские строки для CSV/Excel: компания + лучший email + роли."""
        rows = []
        for r in self.cx.execute('SELECT * FROM companies').fetchall():
            cols = [d[0] for d in self.cx.description]
            comp = dict(zip(cols, r))
            ems = self.cx.execute('SELECT email,role,person,mx_ok FROM emails WHERE inn=?',
                                  (comp['inn'],)).fetchall()
            comp['emails'] = [{'email': e[0], 'role': e[1], 'person': e[2], 'mx_ok': e[3]} for e in ems]
            rows.append(comp)
        return rows


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        args = {}
    db = EnrichDB(args.get('db'))
    op = args.get('op', 'stats')
    if op == 'stats':
        json.dump(db.stats(), sys.stdout, ensure_ascii=False)
    elif op == 'export':
        json.dump({'rows': db.export_rows()}, sys.stdout, ensure_ascii=False)
    else:
        json.dump({'error': f'unknown op {op}'}, sys.stdout)


if __name__ == '__main__':
    main()
