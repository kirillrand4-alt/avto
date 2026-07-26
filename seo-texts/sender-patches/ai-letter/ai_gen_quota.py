# -*- coding: utf-8 -*-
"""AI-генерация писем кампании ПОРЦИЯМИ по дневной квоте (C6) + единый калибровочный
лог ai_letter_log (C7: ok+brak+раунды). Владелец: «3 сегодня, 3 завтра, 5 послезавтра».

Квота: генерирует НЕ БОЛЕЕ (daily_quota - уже_сгенерировано_сегодня) новых писем в
очередь за запуск. Уже-в-очереди/уже-сегодня — пропускает. Запуск раз в день с нужным N
(или campaign.config.daily_quota). Резюм durable: состояние — в confirm_reviews +
ai_letter_log (серверные), не в песочном файле.

Запуск: python ai_gen_quota.py <кампания> <квота-на-сегодня>
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender')
os.chdir(r'C:\sender')

CFG = r'C:\sender\sender.yaml'
CAMP_NAME = sys.argv[1] if len(sys.argv) > 1 else 'новостные'
QUOTA_ARG = int(sys.argv[2]) if len(sys.argv) > 2 else 0
LOG = r'C:\sender\ai_gen_quota.log'
BATCH = 4


def log(m):
    line = time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + m
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    print(line, flush=True)


from sender.config import Config          # noqa: E402
from sender.store import Store            # noqa: E402
from sender.ai_letter import AiLetterGen, load_facts, log_results  # noqa: E402

cfg = Config.load(CFG, env=os.environ)
db_path = cfg.get('service.db_path', 'sender.db')
store = Store(db_path)
store.init_schema()


def caller(prompt):
    from sender.review_lenses import default_caller
    text, _m = default_caller(prompt)
    return text


con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
camp = con.execute("SELECT id, config_json FROM campaigns WHERE name=?", (CAMP_NAME,)).fetchone()
if not camp:
    log(f'кампания «{CAMP_NAME}» не найдена'); sys.exit(1)
cid = camp['id']
ccfg = {}
try:
    ccfg = json.loads(camp['config_json'] or '{}')
except Exception:  # noqa: BLE001
    pass
quota = QUOTA_ARG or int(ccfg.get('daily_quota') or 0)
if quota <= 0:
    log('квота не задана (аргумент или campaign.config.daily_quota) — нечего делать'); sys.exit(0)

# единый лог: таблица (создаётся log_results); сколько СГЕНЕРИРОВАНО сегодня
con.execute("""CREATE TABLE IF NOT EXISTS ai_letter_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, recipient_id INTEGER,
    email TEXT, status TEXT, subject TEXT, body TEXT, rounds_json TEXT, created_at TEXT)""")
con.commit()
today = time.strftime('%Y-%m-%d')
gen_today = con.execute(
    "SELECT COUNT(*) c FROM ai_letter_log WHERE campaign_id=? AND substr(created_at,1,10)=?",
    (cid, today)).fetchone()['c']
remaining = max(0, quota - gen_today)
log(f'кампания {cid} «{CAMP_NAME}»: квота {quota}, сегодня уже {gen_today}, к генерации {remaining}')
if remaining <= 0:
    log('дневная квота на сегодня выбрана — стоп'); sys.exit(0)

# кандидаты: получатели кампании, у кого ЕЩЁ НЕТ письма в очереди/логе
already = set(r[0] for r in con.execute(
    "SELECT DISTINCT recipient_id FROM ai_letter_log WHERE campaign_id=? AND recipient_id IS NOT NULL",
    (cid,)).fetchall())
already |= set(r[0] for r in con.execute(
    "SELECT DISTINCT recipient_id FROM confirm_reviews WHERE campaign_id=? AND recipient_id IS NOT NULL",
    (cid,)).fetchall())
seg = ccfg.get('segment') or CAMP_NAME
recips = [r for r in con.execute(
    "SELECT id, email, inn, company_name, okved, contact_name, extra_json FROM recipients "
    "WHERE segment=?", (seg,)).fetchall() if r['id'] not in already]
todo = recips[:remaining]
log(f'кандидатов без письма: {len(recips)}, берём {len(todo)} (по квоте)')

# enrich.db для выжимки события
ENR = r'C:\sender\enrich.db'
enr = sqlite3.connect(ENR) if os.path.exists(ENR) else None
if enr:
    enr.row_factory = sqlite3.Row


def digest(inn):
    if not enr or not inn:
        return {}
    row = enr.execute("SELECT event_type, what, sum, source_url FROM signals WHERE inn=? "
                      "ORDER BY COALESCE(hotness,0) DESC LIMIT 1", (str(inn),)).fetchone()
    if not row:
        return {}
    what, et, sm = (row['what'] or '').strip(), (row['event_type'] or '').strip(), (row['sum'] or '').strip()
    rd = ' — '.join(x for x in (et, what) if x) + (f' ({sm})' if sm else '')
    return {'news_detail': what, 'news_type': et, 'news_sum': sm, 'news_url': row['source_url'], 'digest': rd}


gen = AiLetterGen(caller, facts=load_facts())
ok_n = brak_n = 0
for i in range(0, len(todo), BATCH):
    chunk = todo[i:i + BATCH]
    reqs = []
    for r in chunk:
        try:
            extra = json.loads(r['extra_json'] or '{}')
        except Exception:  # noqa: BLE001
            extra = {}
        dg = digest(r['inn'])
        for k in ('news_detail', 'news_type', 'news_sum', 'news_url'):
            if dg.get(k) and not extra.get(k):
                extra[k] = dg[k]
        if not extra.get('news_object') and dg.get('news_detail'):
            extra['news_object'] = dg['news_detail']
        reqs.append({'company_name': r['company_name'], 'okved': r['okved'],
                     'contact_name': r['contact_name'], 'mode': 'auto', 'extra': extra,
                     '_digest': dg.get('digest', ''), '_url': dg.get('news_url', '')})
    try:
        res = gen.generate(reqs)
    except Exception as e:  # noqa: BLE001
        log(f'  батч {i//BATCH}: сбой {str(e)[:100]} — повтор позже'); continue
    logitems = []
    for j, r in enumerate(chunk):
        L = res.ok.get(j)
        if L:
            try:
                # message_id обязателен: без него approve падает «нет message_id —
                # нечего отправлять» (ревью №21). Ключ — канон cadence.
                import hashlib as _hl
                from datetime import datetime as _dt, timezone as _tzz
                from sender.dtos import MessageIn as _MIn
                steps = store.get_steps(cid)
                if not steps:
                    log(f'    {r["email"]}: у кампании нет шага-письма — пропуск'); brak_n += 1; continue
                _step = steps[0]
                _key = _hl.sha256(f'{cid}|{r["id"]}|{_step.step_index}'.encode()).hexdigest()
                _mid, _ = store.enqueue_message(_MIn(
                    idempotency_key=_key, campaign_id=cid, recipient_id=r['id'],
                    sequence_step_id=_step.id, scheduled_at=_dt.now(_tzz.utc)),
                    status='pending_review')
                store.confirm_submit(email=r['email'], subject=L['subject'], body=L['body'],
                                     inn=r['inn'], campaign_id=cid, recipient_id=r['id'],
                                     message_id=_mid,
                                     panel={'ai': True, 'rounds': len(L.get('rounds') or []),
                                            'news_digest': reqs[j].get('_digest', ''),
                                            'news_url': reqs[j].get('_url', '')})
                ok_n += 1
                logitems.append({'email': r['email'], 'recipient_id': r['id'], 'status': 'ok',
                                 'subject': L['subject'], 'body': L['body'], 'rounds': L.get('rounds')})
            except Exception as e:  # noqa: BLE001
                log(f'    submit fail {r["email"]}: {str(e)[:70]}')
        else:
            brak_n += 1
            logitems.append({'email': r['email'], 'recipient_id': r['id'], 'status': 'brak',
                             'subject': '', 'body': '',
                             'rounds': [{'rejected': [str(x)[:120] for x in (res.rejected.get(j) or [])]}]})
    # C7: единый лог — И ok, И brak (для калибровки)
    try:
        log_results(db_path, cid, logitems)
    except Exception as e:  # noqa: BLE001
        log(f'  ai_letter_log fail: {str(e)[:80]}')
    log(f'  батч {i//BATCH}: ok={ok_n} brak={brak_n} (лимит {remaining})')

log(f'ГОТОВО: сегодня сгенерировано ok={ok_n} brak={brak_n} (квота была {quota}, '
    f'уже было {gen_today})')
