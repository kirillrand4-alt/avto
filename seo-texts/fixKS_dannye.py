# -*- coding: utf-8 -*-
r"""fixKS (21.10): какие данные есть у панели КЦ для статистики. Только чтение (sqlite mode=ro), без телефонов.

Службы nssm obzvon / p25obzvon / seostat: каталог, параметры, окружение (только пути баз и префиксы, секреты скрыты).
База продаж КЦ: таблицы, действия журнала и ключи payload, статусы, скрытые. Каталог: колонки и заполненность полей
для разрезов. Очередь по менеджерам: назначено → в каталоге → не скрыто → не перенесено во вкладки = показывается.

    python3 zapusk_na_servere.py fixKS_dannye.py
"""
import collections
import io
import json
import os
import re
import sqlite3
import subprocess

SEKRET = re.compile(r'(PASS|SECRET|TOKEN|KEY|PAROL|AUTH|USERS|ADMINS)', re.I)
DROP = r'C:\seostat\drop\drop-storage'
out = []


def p(*a):
    s = ' '.join(str(x) for x in a)
    out.append(s)
    print(s)


def nssm(svc, par):
    for exe in (r'C:\nssm.exe', r'C:\Windows\System32\nssm.exe'):
        if os.path.exists(exe):
            r = subprocess.run([exe, 'get', svc, par], capture_output=True, timeout=60)
            t = r.stdout.decode('utf-16-le', 'replace') if b'\x00' in r.stdout else r.stdout.decode('cp866', 'replace')
            return t.replace('\x00', '').strip()
    return ''


okr = {}
for svc in ('obzvon', 'p25obzvon', 'seostat'):
    p('\nслужба', svc)
    for par in ('Application', 'AppParameters', 'AppDirectory', 'AppStdout', 'AppExit'):
        p('   %s: %s' % (par, nssm(svc, par)[:200]))
    env = nssm(svc, 'AppEnvironmentExtra')
    d = {}
    for l in env.splitlines():
        if '=' in l:
            k, v = l.split('=', 1)
            d[k.strip()] = v.strip()
    okr[svc] = d
    p('   окружение:', {k: ('<скрыто>' if SEKRET.search(k) else v[:120]) for k, v in d.items()})

SALES = okr.get('obzvon', {}).get('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
KAT = okr.get('obzvon', {}).get('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
p('\nКЦ: продажи', SALES, ' каталог', KAT)


def ro(put):
    c = sqlite3.connect('file:%s?mode=ro' % put, uri=True, timeout=20)
    c.row_factory = sqlite3.Row
    return c


s = ro(SALES)
tabl = [r[0] for r in s.execute("select name from sqlite_master where type='table' order by 1")]
p('таблицы продаж:', {t: s.execute('select count(*) from "%s"' % t).fetchone()[0] for t in tabl})
for t in ('users', 'company_comment', 'company_state', 'activity_log', 'company_assignment', 'hidden_item'):
    if t in tabl:
        p('   колонки %s: %s' % (t, [r[1] for r in s.execute('pragma table_info("%s")' % t)]))
p('пользователи:', [tuple(r) for r in s.execute('select username, role, is_active from users')])
p('журнал по действиям:', [tuple(r) for r in s.execute(
    'select action, count(*), min(created_at), max(created_at) from activity_log group by 1 order by 2 desc')])
kl = collections.defaultdict(collections.Counter)
rez = collections.Counter()
for r in s.execute('select action, payload_json from activity_log'):
    try:
        pl = json.loads(r[1] or '{}')
    except ValueError:
        pl = {}
    for k in pl:
        kl[r[0]][k] += 1
    if r[0] == 'call_saved':
        rez[str(pl.get('result'))] += 1
p('ключи payload:', {a: dict(c) for a, c in kl.items()})
p('результаты в call_saved:', dict(rez))
p('журнал по пользователям:', [tuple(r) for r in s.execute(
    'select username, count(*), max(created_at) from activity_log group by 1')])
p('статусы company_state:', [tuple(r) for r in s.execute(
    'select username, call_result, count(*) from company_state group by 1,2 order by 1,2')])
p('next_contact_at заполнено:', s.execute("select count(*) from company_state where coalesce(next_contact_at,'')<>''").fetchone()[0])
p('hidden_item по видам:', [tuple(r) for r in s.execute('select kind, count(*) from hidden_item group by 1')])
p('скрытые компании по кому:', [tuple(r) for r in s.execute(
    "select username, count(*) from hidden_item where kind='company' group by 1")])
if 'sud_verdikt' in tabl:
    p('sud_verdikt:', [tuple(r) for r in s.execute('select verdikt, count(*) from sud_verdikt group by 1')])
p('комментарии по пользователям:', [tuple(r) for r in s.execute('select username, count(*) from company_comment group by 1')])

k = ro(KAT)
ktab = [r[0] for r in k.execute("select name from sqlite_master where type='table' order by 1")]
p('\nтаблицы каталога:', ktab)
kol = [r[1] for r in k.execute('pragma table_info(company)')]
p('колонки company (%d):' % len(kol), kol)
n_all = k.execute('select count(*) from company').fetchone()[0]
inn_kat = {re.sub(r'\D', '', str(r[0] or ''))[:12] for r in k.execute('select inn from company')}
inn_kat.discard('')
p('строк company %d, ИНН различных %d' % (n_all, len(inn_kat)))
for pole in ('region', 'segment', 'otrasl', 'bazy', 'okved', 'okved_main', 'osnovnoy_okved', 'priority', 'prioritet', 'kategoriya',
             'status', 'tip', 'istochnik', 'source', 'verdikt', 'lpr_roli', 'segmenty', 'gruppa', 'legal_status', 'medium'):
    if pole in kol:
        z = k.execute('select count(*), count(distinct "%s") from company where coalesce("%s","")<>""' % (pole, pole)).fetchone()
        prim = [r[0] for r in k.execute('select "%s", count(*) from company where coalesce("%s","")<>"" group by 1 order by 2 desc limit 4' % (pole, pole))]
        p('   %s: заполнено %d, значений %d, частые %s' % (pole, z[0], z[1], [str(x)[:40] for x in prim]))
if 'contact' in ktab:
    p('колонки contact:', [r[1] for r in k.execute('pragma table_info(contact)')])

# --- очередь по менеджерам
skr = {str(r[0]) for r in s.execute("select inn from hidden_item where kind='company'")}
VKLADKI = ('v_rabote', 'ne_ponravilas', 'dubl')
po = collections.defaultdict(collections.Counter)
for r in s.execute("select a.username, a.inn, coalesce(st.call_result,'new') from company_assignment a "
                   "left join company_state st on st.inn=a.inn and st.username=a.username"):
    u, inn, res = r[0], str(r[1]), r[2]
    c = po[u]
    c['naznacheno'] += 1
    if inn not in inn_kat:
        c['net_v_kataloge'] += 1
        continue
    if inn in skr:
        c['skryto'] += 1
        c['skryto_' + ('vkladka' if res in VKLADKI else 'ochered')] += 1
        continue
    if res in VKLADKI:
        c['vkladka_' + res] += 1
        continue
    c['v_ocheredi'] += 1
    if res != 'new':
        c['v_ocheredi_star_status_' + res] += 1
p('\nочередь по менеджерам:')
for u, c in sorted(po.items()):
    p('   %s: %s' % (u, dict(c)))
p('назначенных ИНН вне каталога всего:', len({str(r[0]) for r in s.execute('select inn from company_assignment')} - inn_kat))
p('каталог без назначения:', len(inn_kat - {str(r[0]) for r in s.execute('select inn from company_assignment')}))

# --- p25 коротко
for svc in ('p25obzvon',):
    sd = okr.get(svc, {}).get('CENTRO_SALES_DB')
    if sd and os.path.exists(sd):
        c = ro(sd)
        p('\n%s продажи %s: пользователи %s, назначений %s' % (svc, sd, [tuple(r) for r in c.execute('select username, role, is_active from users')],
                                                             c.execute('select count(*) from company_assignment').fetchone()[0]))
io.open(os.path.join(DROP, 'fixKS-dannye.txt'), 'w', encoding='utf-8').write('\n'.join(out))
