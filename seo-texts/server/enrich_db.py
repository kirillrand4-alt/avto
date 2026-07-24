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
  site TEXT, cand_site TEXT, activity TEXT, is_competitor INTEGER DEFAULT 0, verified TEXT,
  best_email TEXT, phones TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS emails(
  inn TEXT, email TEXT, role TEXT, person TEXT, mx_ok INTEGER, source TEXT,
  source_url TEXT, updated_at TEXT, UNIQUE(inn, email));
CREATE TABLE IF NOT EXISTS signals(
  inn TEXT, source TEXT, event_type TEXT, what TEXT, sum TEXT, source_url TEXT,
  hotness INTEGER, ts TEXT, updated_at TEXT, UNIQUE(inn, source, what));
CREATE TABLE IF NOT EXISTS donors(
  domain TEXT PRIMARY KEY, rss TEXT, rss_items INTEGER DEFAULT 0,
  event_count INTEGER DEFAULT 0, status TEXT, first_seen TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS seen_news(
  k TEXT PRIMARY KEY, ts TEXT);
CREATE INDEX IF NOT EXISTS ix_comp_div ON companies(division);
CREATE INDEX IF NOT EXISTS ix_comp_site ON companies(site);
CREATE INDEX IF NOT EXISTS ix_email_inn ON emails(inn);
CREATE INDEX IF NOT EXISTS ix_sig_inn ON signals(inn);
"""

# МАППИНГ ОКВЭД → направление (файл владельца «ОКВЭД и оборудование», 77 кодов).
# kc=КомпрессорЦентр (компрессоры/азот/кислород/МКС), meyer=фотосепараторы/рентген.
# budget 1-5 — балл бюджета владельца (5=капиталоёмкие). Матч префиксный (25.11 матчит 25.11.х).
OKVED_DIRECTIONS = {
    '01.63': ('meyer', 4),
    '01.64': ('meyer', 4),
    '03.22': ('kc', 3),
    '06.10': ('kc', 5),
    '06.20': ('kc', 5),
    '07.10': ('kc+meyer', 5),
    '07.29': ('meyer', 5),
    '08.11': ('kc', 4),
    '08.12': ('kc', 4),
    '09.10': ('kc', 5),
    '10.11': ('meyer', 5),
    '10.12': ('meyer', 5),
    '10.13': ('meyer', 5),
    '10.20': ('meyer', 5),
    '10.31': ('meyer', 4),
    '10.32': ('meyer', 4),
    '10.39': ('meyer', 4),
    '10.41': ('meyer', 3),
    '10.42': ('meyer', 3),
    '10.51': ('meyer', 5),
    '10.52': ('meyer', 5),
    '10.61': ('kc+meyer', 4),
    '10.62': ('meyer', 3),
    '10.71': ('meyer', 4),
    '10.72': ('meyer', 4),
    '10.73': ('meyer', 4),
    '10.81': ('meyer', 4),
    '10.82': ('meyer', 4),
    '10.83': ('meyer', 4),
    '10.84': ('meyer', 4),
    '10.85': ('meyer', 5),
    '10.86': ('meyer', 5),
    '10.89': ('kc+meyer', 3),
    '11.01': ('meyer', 3),
    '11.02': ('meyer', 3),
    '11.05': ('meyer', 4),
    '11.07': ('meyer', 4),
    '19.20': ('kc', 4),
    '20.11': ('kc', 5),
    '20.13': ('kc', 4),
    '20.15': ('kc', 4),
    '21.20': ('kc', 4),
    '23.12': ('kc', 4),
    '24.10': ('kc', 5),
    '25.11': ('kc', 3),
    '25.12': ('kc', 2),
    '25.21': ('kc', 3),
    '25.29': ('kc', 4),
    '25.30.1': ('kc', 4),
    '25.50': ('kc', 4),
    '25.61': ('kc', 4),
    '25.62': ('kc', 5),
    '25.73': ('kc', 3),
    '25.91': ('kc', 3),
    '25.92': ('kc', 3),
    '25.93': ('kc', 3),
    '25.94': ('kc', 3),
    '35.11': ('kc', 4),
    '35.22': ('kc', 5),
    '35.30': ('kc', 3),
    '36.00': ('kc', 3),
    '37.00': ('kc', 4),
    '38.32': ('meyer', 4),
    '42.11': ('kc', 4),
    '42.21': ('kc', 4),
    '43.11': ('kc', 4),
    '43.12': ('kc', 4),
    '43.13': ('kc', 4),
    '43.99': ('kc', 4),
    '49.50': ('kc', 5),
    '52.10.3': ('meyer', 4),
    '52.21.3': ('kc', 3),
    '71.20': ('kc', 2),
    '72.19': ('kc', 2),
    '77.32': ('kc', 5),
    '84.25': ('kc', 2),
    '86.10': ('kc', 5),
}

import re as _re

# ОКВЭД-КОНКУРЕНТЫ. ПРАВИЛО ВЛАДЕЛЬЦА (2026-07-24, «давай так»): исключать как
# конкурента, если 28.13/28.12 — ОСНОВНОЙ ОКВЭД, ИЛИ провайдер по сайту/названию
# подтвердил «производит компрессоры/насосы» (is_compressor_maker). ВТОРИЧНЫЙ
# 28.13 сам по себе — НЕ повод: аудит базы показал 1116 компаний с 28.13 и у ВСЕХ
# он вторичный «про запас» (ГАЗПРОМ Газораспределение, ХИМПРОМ — это клиенты).
# Реальный КОНАР (осн. 28.14, доп. 28.12+28.13, сам машиностроитель) ловится
# второй ступенью — провайдер-судьёй по сайту.
PRIMARY_COMPETITOR_OKVEDS = {
    '28.13': 'производство насосов и компрессоров (конкурент КЦ)',
    '28.12': 'гидравлическое/пневматическое силовое оборудование (конкурент КЦ)',
}
# исторические алиасы для okved_audit (счётчики по полному списку — информативно)
COMPETITOR_OKVEDS = PRIMARY_COMPETITOR_OKVEDS
COMPETITOR_OKVEDS_CANDIDATES = {
    '28.25': 'промышленное холодильное и вентиляционное оборудование',
    '28.29': 'машины и оборудование общего назначения (в т.ч. газогенераторы)',
    '28.93': 'машины для пищевой промышленности (сепараторы — конкурент Meyer)',
}


def is_competitor_primary(primary_okved_text):
    """ПРАВИЛО ВЛАДЕЛЬЦА, ступень 1: конкурент, если ОСНОВНОЙ ОКВЭД — 28.13/28.12
    (префиксно: 28.13.1 матчит). На вход — строка основного ОКВЭД («28.13 Производство…»).
    Ступень 2 (провайдер is_compressor_maker по сайту) живёт в enrich_one/extract_roles.
    Возврат: (bool, код|'')."""
    m = _re.search(r'\d{2}\.\d+(?:\.\d+)?', str(primary_okved_text or ''))
    if not m:
        return (False, '')
    code = m.group(0)
    for k in PRIMARY_COMPETITOR_OKVEDS:
        if code == k or code.startswith(k + '.'):
            return (True, k)
    return (False, '')


def is_competitor_by_okved(*okved_texts, extra=None):
    """Информативная проверка по ВСЕМ ОКВЭД (для аудита/отчётов; НЕ для блокировки —
    блокирует только is_competitor_primary + провайдер, см. правило владельца).
    Возврат: (bool, [сматченные коды])."""
    codes = set(COMPETITOR_OKVEDS) | set(extra or ())
    hit = []
    for txt in okved_texts:
        for code in _re.findall(r'\d{2}\.\d+(?:\.\d+)?|(?<!\d)\d{2}(?!\d)', str(txt or '')):
            for k in codes:
                if code == k or code.startswith(k + '.'):
                    hit.append(k)
    return (bool(hit), sorted(set(hit)))


def division_for_okveds(*okved_texts):
    """Направление(я) и макс-бюджет по ВСЕМ ОКВЭД компании (основной + доп).
    okved_texts — строки с кодами в любом виде («25.11 Производство...», строка ВсеОКВЭД).
    Матч префиксный: код компании 25.11.1 матчит запись 25.11. Возврат ('kc'|'meyer'|
    'kc+meyer'|'', budget 0-5). Пусто = ни один из 77 таргет-кодов не совпал."""
    divs, budget = set(), 0
    for txt in okved_texts:
        for code in _re.findall(r'\d{2}\.\d+(?:\.\d+)?|(?<!\d)\d{2}(?!\d)', str(txt or '')):
            for k, (d, b) in OKVED_DIRECTIONS.items():
                if code == k or code.startswith(k + '.'):
                    divs |= set(d.split('+'))
                    budget = max(budget, b)
    return ('+'.join(sorted(divs)), budget)



class EnrichDB:
    def __init__(self, path=None, now=None):
        self.path = path or DB_PATH
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        self.now = now or time.strftime('%Y-%m-%dT%H:%M:%S')
        # check_same_thread=False: enrich пишет из пула потоков, доступ сериализован
        # внешним локом (_wlock); WAL допускает конкурентных читателей.
        self.cx = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self.cx.execute('PRAGMA journal_mode=WAL')
        self.cx.executescript(_SCHEMA)
        try:                       # миграция старых БД: добавить cand_site, если колонки нет
            self.cx.execute('ALTER TABLE companies ADD COLUMN cand_site TEXT')
        except Exception:  # noqa: BLE001  колонка уже существует
            pass
        try:                       # миграция: URL страницы-источника каждого контакта
            self.cx.execute('ALTER TABLE emails ADD COLUMN source_url TEXT')
        except Exception:  # noqa: BLE001  колонка уже существует
            pass
        self.cx.commit()

    def upsert_company(self, inn, **f):
        """UPSERT компании. Непустые поля перезаписывают, пустые — НЕ затирают старое."""
        if not inn:
            return
        inn = str(inn)
        cols = ('name', 'division', 'okved', 'region', 'pxr', 'site', 'cand_site', 'activity',
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

    # КАНОН ролей: варианты модели («закупки», «снабженец», «коммерческий») → 8 фиксированных
    # значений. Без этого таргет по роли в рассылке промахивается (WHERE role='снабжение/закупки'
    # не поймает 'закупки'). Нормализуем на ЗАПИСИ — единый канон для всех источников.
    _ROLE_CANON = [
        (('закуп', 'снабж', 'поставщик', 'тендер', 'procurement'), 'снабжение/закупки'),
        (('продаж', 'сбыт', 'коммерч', 'sales', 'менеджер по прод'), 'продажи'),
        (('директор', 'руковод', 'ген.дир', 'гендир', 'founder', 'owner', 'ceo'), 'директор'),
        (('инженер', 'техни', 'энергетик', 'главный механик', 'гл.мех', 'производств'), 'гл.инженер'),
        (('бухгалт', 'финанс', 'эконом', 'accountant'), 'бухгалтерия'),
        (('кадр', 'персонал', 'hr', 'рекрут'), 'кадры'),
        (('приём', 'приемн', 'секрет', 'reception', 'office', 'офис', 'ресепш'), 'приёмная'),
    ]

    @staticmethod
    def _canon_role(role):
        r = (role or '').strip().lower()
        if not r:
            return ''
        for keys, canon in EnrichDB._ROLE_CANON:
            if any(k in r for k in keys):
                return canon
        return 'общий'

    def add_email(self, inn, email, role='', person='', mx_ok=None, source='', source_url=''):
        if not (inn and email):
            return
        role = self._canon_role(role)
        self.cx.execute(
            'INSERT INTO emails(inn,email,role,person,mx_ok,source,source_url,updated_at) '
            'VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(inn,email) DO UPDATE SET '
            'role=CASE WHEN excluded.role!="" THEN excluded.role ELSE emails.role END, '
            'person=CASE WHEN excluded.person!="" THEN excluded.person ELSE emails.person END, '
            'mx_ok=COALESCE(excluded.mx_ok,emails.mx_ok), '
            'source_url=CASE WHEN excluded.source_url!="" THEN excluded.source_url '
            'ELSE emails.source_url END, updated_at=excluded.updated_at',
            (str(inn), email.lower().strip(), role or '', person or '',
             (1 if mx_ok else 0) if mx_ok is not None else None, source or '',
             source_url or '', self.now))
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

    def seen_add(self, k):
        """Кросс-чанковый/кросс-прогонный дедуп новостей. Возвращает True если k НОВЫЙ
        (вставлен → обрабатываем), False если уже видели (пропускаем провайдер). Атомарно."""
        if not k:
            return True
        try:
            cur = self.cx.execute('INSERT OR IGNORE INTO seen_news(k,ts) VALUES(?,?)', (k, self.now))
            self.cx.commit()
            return cur.rowcount > 0     # 1 = вставлено (новое), 0 = уже было
        except Exception:  # noqa: BLE001
            return True

    def bump_donor(self, domain, inc=1):
        """+inc к счётчику капекс-событий домена (донор-кандидат). Вызывается на КАЖДОЕ
        событие из _persist_event — частота донора накапливается durable, не теряется."""
        if not domain:
            return
        self.cx.execute(
            'INSERT INTO donors(domain,event_count,first_seen,updated_at) VALUES(?,?,?,?) '
            'ON CONFLICT(domain) DO UPDATE SET event_count=event_count+?, updated_at=?',
            (domain, inc, self.now, self.now, inc, self.now))
        self.cx.commit()

    def add_donor(self, domain, rss='', rss_items=0, status='live'):
        """Проверенная RSS-лента донора (результат дискавери) — durable, чтобы не терять
        и не передискаверивать."""
        if not domain:
            return
        self.cx.execute(
            'INSERT INTO donors(domain,rss,rss_items,status,first_seen,updated_at) VALUES(?,?,?,?,?,?) '
            'ON CONFLICT(domain) DO UPDATE SET rss=excluded.rss, rss_items=excluded.rss_items, '
            'status=excluded.status, updated_at=excluded.updated_at',
            (domain, rss or '', int(rss_items or 0), status, self.now, self.now))
        self.cx.commit()

    def top_donor_domains(self, limit=200, only_no_rss=False):
        """Домены-кандидаты по убыванию частоты событий (для RSS-дискавери). only_no_rss —
        только те, у кого RSS ещё не найден."""
        q = 'SELECT domain FROM donors'
        if only_no_rss:
            q += " WHERE (rss IS NULL OR rss='')"
        q += ' ORDER BY event_count DESC LIMIT ?'
        return [r[0] for r in self.cx.execute(q, (limit,)).fetchall()]

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
            ems = self.cx.execute('SELECT email,role,person,mx_ok,source_url FROM emails WHERE inn=?',
                                  (comp['inn'],)).fetchall()
            comp['emails'] = [{'email': e[0], 'role': e[1], 'person': e[2], 'mx_ok': e[3],
                               'source_url': e[4] or ''} for e in ems]
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
    elif op == 'rebuild_donors':
        # ретро-пересборка доноров из news_stream*.jsonl (события ДО добавления bump_donor
        # в конвейер не считались). Идемпотентно: счётчики ПЕРЕЗАПИСЫВАЮТСЯ пересчитанным
        # значением (не инкремент), rss/status от дискавери не трогаются.
        import glob as _g
        d = os.path.dirname(os.path.abspath(__file__))
        cnt = {}
        files = args.get('streams') or _g.glob(os.path.join(d, 'news_stream*.jsonl'))
        for p in files:
            try:
                for line in open(p, encoding='utf-8'):
                    try:
                        rec = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    m = _re.match(r'https?://([^/]+)', str(rec.get('source_url') or ''))
                    if m:
                        dom = m.group(1).lstrip('www.')
                        cnt[dom] = cnt.get(dom, 0) + 1
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'rebuild_donors {p}: {str(e)[:80]}\n')
        for dom, n in cnt.items():
            db.cx.execute(
                'INSERT INTO donors(domain,event_count,first_seen,updated_at) VALUES(?,?,?,?) '
                'ON CONFLICT(domain) DO UPDATE SET '
                'event_count=MAX(excluded.event_count,donors.event_count), updated_at=excluded.updated_at',
                (dom, n, db.now, db.now))
        db.cx.commit()
        total = db.cx.execute('SELECT COUNT(*) FROM donors').fetchone()[0]
        json.dump({'ok': True, 'streams': files, 'domains_in_streams': len(cnt),
                   'donors_total_now': total}, sys.stdout, ensure_ascii=False)
    elif op == 'donors':
        # выгрузка донорской базы новостей: домен, счётчик событий, RSS (если найден)
        rows = db.cx.execute(
            'SELECT domain, event_count, rss, rss_items, status, first_seen, updated_at '
            'FROM donors ORDER BY event_count DESC LIMIT ?',
            (int(args.get('limit', 500)),)).fetchall()
        json.dump({'donors': [
            {'domain': r[0], 'event_count': r[1], 'rss': r[2] or '', 'rss_items': r[3],
             'status': r[4] or '', 'first_seen': r[5], 'updated_at': r[6]} for r in rows],
            'total': db.cx.execute('SELECT COUNT(*) FROM donors').fetchone()[0]},
            sys.stdout, ensure_ascii=False)
    elif op == 'export':
        json.dump({'rows': db.export_rows()}, sys.stdout, ensure_ascii=False)
    elif op == 'snapshot':
        # консистентный снимок БД (SQLite backup, безопасно под WAL-записью) → на дроп под
        # стабильным именем. Для dry-run инженера на ЖИВЫХ данных (реальные скор/verified/роли).
        import urllib.request
        name = args.get('name', 'enrich_snapshot.db')
        drop = os.environ.get('DROP_URL', '').rstrip('/')
        tok = os.environ.get('DROP_TOKEN', '')
        tmp = os.path.join(os.path.dirname(os.path.abspath(db.path)), '_snapshot_tmp.db')
        try:
            dst = sqlite3.connect(tmp)
            with dst:
                db.cx.backup(dst)
            dst.close()
            blob = open(tmp, 'rb').read()
            os.remove(tmp)
            req = urllib.request.Request(drop + '/' + name, data=blob, method='PUT',
                                         headers={'X-Drop-Token': tok})
            urllib.request.urlopen(req, timeout=300)
            json.dump({'ok': True, 'uploaded': name, 'bytes': len(blob), 'stats': db.stats()},
                      sys.stdout, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            json.dump({'ok': False, 'error': str(e)[:200]}, sys.stdout, ensure_ascii=False)
    elif op == 'rebuild':
        # восстановить БД из append-only JSONL (если SQLite побился)
        import glob
        d = os.path.dirname(os.path.abspath(__file__))
        paths = args.get('streams') or glob.glob(os.path.join(d, 'enrich_stream*.jsonl'))
        n = 0
        for p in paths:
            try:
                for line in open(p, encoding='utf-8'):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue  # битая строка — пропускаем, остальные целы
                    inn = str(r.get('inn') or '')
                    if not inn:
                        continue
                    db.upsert_company(inn, name=r.get('name'), okved=r.get('_okved'),
                                      region=r.get('city'), site=r.get('site'),
                                      activity=r.get('activity'), is_competitor=r.get('is_competitor'),
                                      best_email=r.get('best_for_outreach'), phones=r.get('phones'))
                    for e in (r.get('emails') or []):
                        if e.get('email'):
                            db.add_email(inn, e.get('email', ''), role=e.get('role', ''),
                                         person=e.get('person', ''), source=r.get('_src') or 'rebuild')
                    n += 1
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f'rebuild {p}: {str(e)[:80]}\n')
        json.dump({'rebuilt_from': paths, 'companies': n, 'stats': db.stats()},
                  sys.stdout, ensure_ascii=False)
    else:
        json.dump({'error': f'unknown op {op}'}, sys.stdout)


if __name__ == '__main__':
    main()
