# -*- coding: utf-8 -*-
"""Скоринг лидов (решение владельца, пункты 1,2,4,5,6 + флаг из 3; УК НЕ используем).
Чистый детерминированный код поверх enrich.db + базы обзвона: НИЧЕГО не отправляет,
LLM не зовёт. Запускается раннером (task=lead_scoring) или локально.

Пункты владельца:
 1. Готовность к покупке 0-100: сигнал 40п + выручка 20п + verified 15п + роль-email 15п
    (сумма макс 90, ранжирование перцентильное) -> топ-20% = call_today (звонок в день письма).
 2. ЛПР-матч: ФИО директора базы [13] x emails.person -> lpr_email («Для [ФИО]» напрямую).
 3. (флаг) budget_confirmed: займ ФРП / резидент ОЭЗ-ТОР из signals -> бюджет подтверждён.
 4. capex_window: 0-30 / 31-90 / 90+ дней с последнего сигнала (срочный тон vs кейс-подход).
 5. buying_power: micro/small/medium/large/enterprise из выручки [34] + бюджет-балла ОКВЭД
    (балл 5 сдвигает на ступень вверх, балл 2 - вниз). Уставный капитал НЕ задействуем.
 6. verified_domain: verified in {inn,ogrn,phone,provider} -> смелее CTA/ссылки.

stdin: {"op":"score","top_pct":20,"cap":0,"division":"","min_score":0,
        "base_fields":{inn:{"revenue":..,"director":".."}}(опц., вместо скана CSV)}
stdout: {"rows":[...по убыванию score...], "summary":{...}}"""
import os, sys, json, re, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enrich_db as EDB

# --- пункт 1: веса владельца ---
_GOOD_VERIFIED = ('inn', 'ogrn', 'phone', 'provider')          # пункт 6
_VERIF_PTS = {'inn': 15, 'ogrn': 15, 'phone': 13, 'provider': 10}
_ROLE_PTS = {'снабжение/закупки': 15, 'гл.инженер': 13, 'директор': 12,
             'продажи': 8, 'общий': 5, 'приёмная': 4, 'бухгалтерия': 2, 'кадры': 2}
_DATE_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')


def _days_ago(*texts):
    """Дни с даты (лениво: первая YYYY-MM-DD в ts/updated_at). None если не распарсили."""
    for t in texts:
        m = _DATE_RE.search(str(t or ''))
        if m:
            try:
                then = time.mktime(time.strptime(m.group(0), '%Y-%m-%d'))
                return max(0, int((time.time() - then) // 86400))
            except Exception:  # noqa: BLE001
                continue
    return None


def _signal_pts(days):
    if days is None:
        return 10          # сигнал есть, дата не распарсилась - середина
    if days <= 30:
        return 40
    if days <= 90:
        return 30
    if days <= 180:
        return 20
    return 10


def _revenue_pts(rev):
    if not rev or rev <= 0:
        return 0
    for thr, p in ((1e9, 20), (3e8, 17), (1e8, 14), (3e7, 10), (1e7, 6)):
        if rev >= thr:
            return p
    return 3


def _capex_window(days):                                        # пункт 4
    if days is None:
        return ''
    return '0-30' if days <= 30 else ('31-90' if days <= 90 else '90+')


def _budget_confirmed(sig_texts):                               # пункт 3 (флаг)
    blob = ' '.join(sig_texts).lower()
    if re.search(r'фрп|займ', blob):
        return 'фрп'
    if re.search(r'резидент|оэз|тосэр|\bтор\b', blob):
        return 'оэз/тор'
    return ''


_TIERS = ['micro', 'small', 'medium', 'large', 'enterprise']


def _buying_power(rev, budget):                                 # пункт 5 (без УК)
    if not rev or rev < 1e7:
        i = 0
    elif rev < 1e8:
        i = 1
    elif rev < 1e9:
        i = 2
    elif rev < 5e9:
        i = 3
    else:
        i = 4
    if budget >= 5:
        i = min(4, i + 1)   # капиталоёмкий ОКВЭД - ступень вверх
    elif budget == 2:
        i = max(0, i - 1)   # мелкий фит - ступень вниз
    return _TIERS[i]


def _norm_fio(s):
    return [w for w in re.sub(r'[^а-яёa-z ]', ' ', (s or '').lower().replace('ё', 'е')).split()
            if len(w) > 1]


def _lpr_match(director, persons):                              # пункт 2
    """ФИО директора [13] x ФИО у email. Совпадение >=2 токенов (фамилия+имя)."""
    d = set(_norm_fio(director))
    if len(d) < 2:
        return None
    for email, person in persons:
        p = set(_norm_fio(person))
        if len(d & p) >= 2:
            return {'email': email, 'person': person}
    return None


def _base_fields(want_inns):
    """Один проход по базе: {inn: {revenue [34], director [13]}}. Нет базы - пусто."""
    import csv
    try:
        import enrich_contacts as EC
        p = EC._get_base()
    except Exception:  # noqa: BLE001
        p = None
    if not p or not want_inns:
        return {}
    INN, DIRECTOR, REV = 1, 13, 34
    try:
        csv.field_size_limit(2 ** 18)
    except Exception:  # noqa: BLE001
        pass
    out = {}
    with open(p, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter=';')
        next(rd, None)
        while True:
            try:
                row = next(rd)
            except StopIteration:
                break
            except Exception:  # noqa: BLE001
                continue
            if len(row) <= REV:
                continue
            inn = (row[INN] or '').strip()
            if inn not in want_inns:
                continue
            try:
                rev = float(re.sub(r'[^\d.]', '', (row[REV] or '0').replace(',', '.')) or 0)
            except Exception:  # noqa: BLE001
                rev = 0.0
            out[inn] = {'revenue': rev, 'director': (row[DIRECTOR] or '').strip()}
            if len(out) >= len(want_inns):
                break
    return out


def score_all(db=None, base_fields=None, division=''):
    """Скоринг всех компаний enrich.db. Возврат: (rows по убыванию score, summary)."""
    db = db or EDB.EnrichDB()
    cx = db.cx
    comps = {}
    for r in cx.execute('SELECT inn,name,division,okved,site,verified,is_competitor,'
                        'best_email FROM companies').fetchall():
        comps[r[0]] = dict(inn=r[0], name=r[1] or '', division=r[2] or '', okved=r[3] or '',
                           site=r[4] or '', verified=r[5] or '', is_competitor=bool(r[6]),
                           best_email=r[7] or '')
    emails = {}
    for r in cx.execute('SELECT inn,email,role,person,mx_ok FROM emails').fetchall():
        emails.setdefault(r[0], []).append(dict(email=r[1], role=r[2] or '',
                                                person=r[3] or '', mx_ok=r[4]))
    sigs = {}
    for r in cx.execute('SELECT inn,event_type,what,ts,updated_at,hotness FROM signals').fetchall():
        sigs.setdefault(r[0], []).append(dict(event_type=r[1] or '', what=r[2] or '',
                                              ts=r[3] or '', updated_at=r[4] or '',
                                              hotness=r[5] or 0))
    if base_fields is None:
        base_fields = _base_fields(set(comps))
    rows, excluded = [], {'competitor': 0, 'mismatch': 0}
    for inn, c in comps.items():
        if division and division not in (c['division'] or ''):
            continue
        if c['is_competitor']:
            excluded['competitor'] += 1
            continue
        if c['verified'] == 'mismatch':
            excluded['mismatch'] += 1
            continue
        ems = emails.get(inn, [])
        ss = sigs.get(inn, [])
        bf = base_fields.get(inn, {})
        rev = bf.get('revenue') or 0.0
        # свежесть: самый свежий сигнал
        days = None
        for s in ss:
            d = _days_ago(s['ts'], s['updated_at'])
            if d is not None and (days is None or d < days):
                days = d
        sp = _signal_pts(days) if ss else 0
        vp = _VERIF_PTS.get(c['verified'], 0)
        rp = max((_ROLE_PTS.get(e['role'], 0) for e in ems), default=0)
        score = sp + _revenue_pts(rev) + vp + rp
        _dv, budget = EDB.division_for_okveds(c['okved'])
        lpr = _lpr_match(bf.get('director', ''), [(e['email'], e['person']) for e in ems])
        rows.append(dict(
            inn=inn, name=c['name'], division=c['division'], score=score,
            parts=dict(signal=sp, revenue=_revenue_pts(rev), verified=vp, role=rp),
            lpr=lpr,                                            # 2
            budget_confirmed=_budget_confirmed(                 # 3 (флаг)
                [s['event_type'] + ' ' + s['what'] for s in ss]),
            capex_window=_capex_window(days),                   # 4
            buying_power=_buying_power(rev, budget),            # 5
            verified_domain=c['verified'] in _GOOD_VERIFIED,    # 6
            best_email=c['best_email'],
            best_role=max(ems, key=lambda e: _ROLE_PTS.get(e['role'], 0))['role'] if ems else '',
            site=c['site'], revenue=rev, signals=len(ss)))
    rows.sort(key=lambda r: -r['score'])
    return rows, dict(companies=len(comps), scored=len(rows), excluded=excluded,
                      base_matched=len(base_fields))


def main():
    try:
        args = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        args = {}
    if args.get('op', 'score') != 'score':
        json.dump({'error': f"unknown op {args.get('op')}"}, sys.stdout)
        return
    rows, summary = score_all(base_fields=args.get('base_fields'),
                              division=args.get('division', ''))
    top_pct = float(args.get('top_pct', 20))
    n_top = max(1, int(len(rows) * top_pct / 100)) if rows else 0
    for i, r in enumerate(rows):
        r['call_today'] = i < n_top                              # 1: топ-20% - звонок в день письма
    if args.get('min_score'):
        rows = [r for r in rows if r['score'] >= int(args['min_score'])]
    cap = int(args.get('cap', 0))
    if cap > 0:
        rows = rows[:cap]
    summary['call_today'] = n_top
    json.dump({'rows': rows, 'summary': summary}, sys.stdout, ensure_ascii=False)


if __name__ == '__main__':
    main()
