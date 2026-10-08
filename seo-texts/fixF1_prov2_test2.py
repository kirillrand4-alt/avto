# -*- coding: utf-8 -*-
"""fixF1: копия теста проверяющего prov2 (выход – файлы fixF1-*, чтобы не затереть его результаты). prov2 (повторная проверка панели Meyer после исправлений; только чтение боевого).
TestClient на ВРЕМЕННЫХ копиях каталога и базы продаж: фильтры главной, поиск, новые
результаты звонка (синтетика только в копиях), статистика – каждая ссылка-цифра, CSV = список.
Отчёт -> C:\\seostat\\drop\\drop-storage\\prov2-test.json и prov2-test.txt."""
import csv, datetime as dt, html as H, io, json, os, re, shutil, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
if '--run' not in sys.argv:
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--run'] + sys.argv[1:],
                       capture_output=True, timeout=1650, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5500:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(0)
FAZY = set()
sys.path.insert(0, KOREN)
import zapusk  # noqa: F401
import logging, warnings
warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
import glob
for _st in glob.glob(os.path.join(KOREN, '_bekap', 'fixF1p-*')) + glob.glob(os.path.join(KOREN, '_bekap', 'fixF1pt-*')):
    try:
        shutil.rmtree(_st); print('убрана старая копия', _st)
    except Exception as _e:
        print('старая копия не убрана', _st, _e)
TMP = os.path.join(KOREN, '_bekap', 'fixF1pt-%d' % os.getpid())
os.makedirs(TMP, exist_ok=True)
def kopiya(src, imya):
    dst = os.path.join(TMP, imya)
    s = sqlite3.connect('file:%s?mode=ro' % src, uri=True); d = sqlite3.connect(dst); s.backup(d); d.close(); s.close()
    return dst
ZH_S = os.environ['CENTRO_SALES_DB']; ZH_K = os.environ['CENTRIFUGAL_DB']
def schet(put):
    c = sqlite3.connect('file:%s?mode=ro' % put, uri=True); out = {}
    for t in ('activity_log', 'company_state', 'company_comment', 'company_assignment', 'contact', 'zvonok_sobytie'):
        try: out[t] = c.execute('select count(*) from %s' % t).fetchone()[0]
        except Exception: pass
    try: out['score_sum'] = round(c.execute('select sum(assignment_score) from company_assignment').fetchone()[0] or 0, 1)
    except Exception: pass
    c.close(); return out
DO = (schet(ZH_S), schet(ZH_K))
S = kopiya(ZH_S, 'sales.db'); K = kopiya(ZH_K, 'katalog.db')
for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'): os.environ[k] = S
for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'): os.environ[k] = K
from app.api import routes_centro_sales as rcs
from app.api import routes_park as rp
from app.api.routes_obzvon import _same_origin
from app.services import centro_catalog as cat
from app.obzvon import create_app
from fastapi.testclient import TestClient
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[_same_origin] = lambda: None
OUT = {'proverki': [], 'dannye': {}}
LOG = []
def p(*a):
    s = ' '.join(str(x) for x in a); LOG.append(s); print(s)
def ok(uslovie, tekst, **dop):
    OUT['proverki'].append({'ok': bool(uslovie), 't': tekst, **dop})
    p(('ОК   ' if uslovie else 'ПЛОХО ') + tekst + ((' ' + json.dumps(dop, ensure_ascii=False, default=str)[:600]) if dop and not uslovie else ''))
USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
for i in range(1, 5):
    USERS['meyer%d' % i] = {'id': i, 'username': 'meyer%d' % i, 'role': 'sales', 'is_active': 1}
def kak(u):
    vnutr.dependency_overrides[rcs.current_user] = (lambda U=USERS[u]: U)
KL = TestClient(vnutr)
KL.__enter__()
def get(url, params=None):
    return KL.get(url if url.startswith(PUT) else PUT + url, params=params, follow_redirects=False)
def total(t):
    m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
    return int(m.group(1)) if m else -1
def inns_stranicy(t):
    return re.findall(r'<tr data-href="[^"]*/centro\?inn=(\d+)', t)
def spisok_inn(params):
    """Все ИНН списка по порядку (постранично, size=100)."""
    out = []; pg = 1
    while True:
        pr = dict(params); pr.update({'size': '100', 'page': str(pg)})
        t = get('/centro', pr).text
        n = total(t); i = inns_stranicy(t); out += i
        if len(out) >= n or not i or pg > 30:
            return out, n
        pg += 1
naz = {}
sb = sqlite3.connect(S); sb.row_factory = sqlite3.Row
for r in sb.execute('select inn, username, assignment_score, stupen_ocheredi from company_assignment'):
    naz[str(r['inn'])] = dict(r)
sb.close()
def ochered(u):
    return sorted([i for i, a in naz.items() if a['username'] == u], key=lambda i: (-float(naz[i]['assignment_score']), i))
kb = sqlite3.connect('file:%s?mode=ro' % K, uri=True); kb.row_factory = sqlite3.Row
COMP = {r['inn']: dict(r) for r in kb.execute('select * from company')}
kb.close()


def post(u, dannye, put='/centro/save'):
    kak(u)
    return KL.post(PUT + put, data=dannye, follow_redirects=False)
def sql_s(q, a=()):
    c = sqlite3.connect(S); c.row_factory = sqlite3.Row
    try: return [dict(r) for r in c.execute(q, a)]
    finally: c.close()
def ssylki_cifry(t):
    out = []
    for u, n in re.findall(r'<a href="(%s/centro(?:\?[^"#]*)?)">\s*(\d+)\s*</a>' % re.escape(PUT), t):
        out.append((H.unescape(u), int(n)))
    return list(dict.fromkeys(out))
def proverit_stat(params, metka):
    kak('meyer_admin')
    o = get('/centro/stats', params); t = o.text
    ss = ssylki_cifry(t)
    plohie = []
    for u, n in ss:
        nn = total(get(u).text)
        if nn != n:
            plohie.append((u, n, nn))
    ok(o.status_code == 200 and not plohie, 'статистика %s: ссылок-цифр %d, все = числу строк списка' % (metka, len(ss)), plohie=plohie[:20])
    return t
segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()
A = ochered('meyer1'); B = ochered('meyer2')
p('== перезвон после «не дозвонился»: где компания в очереди')
kak('meyer1'); vs0, _ = spisok_inn({})
y = A[100]
zavtra = (segodnya + dt.timedelta(days=1)).isoformat() + 'T10:00'
r = post('meyer1', {'inn': y, 'call_result': 'ne_dozvonilsya', 'comment': 'перезвонить завтра', 'next_contact_at': zavtra})
kak('meyer1'); vs1, _ = spisok_inn({})
ok(r.status_code == 303, 'сохранено: %s' % r.status_code)
p('   место до: %d, после «не дозвонился» с перезвоном на завтра: %d; №1 очереди теперь %s' % (vs0.index(y) + 1, vs1.index(y) + 1, vs1[0]))
ok(vs1.index(y) + 1 > 1, 'компания с перезвоном НА ЗАВТРА не обгоняет всю очередь сегодня (место %d)' % (vs1.index(y) + 1))
kak('meyer_admin'); t = get('/centro/stats', {'user': 'meyer1'}).text
ok('сначала новые, затем перезвоны по' in t, 'подпись очереди в статистике: «сначала новые, затем перезвоны по сроку»')
p('== скрытые компании и цифры статистики')
x1 = A[20]; x2 = B[20]; x3 = B[21]
post('meyer1', {'inn': x1, 'call_result': 'v_rabote', 'comment': 'КП'})
post('meyer2', {'inn': x2, 'call_result': 'ne_ponravilas', 'prichina': 'нет потребности', 'comment': ''})
r1 = post('meyer1', {'inn': x1, 'kind': 'company', 'value': x1, 'reason': 'проверка'}, '/centro/hide')
r2 = post('meyer2', {'inn': x3, 'kind': 'company', 'value': x3, 'reason': 'проверка'}, '/centro/hide')
ok(r1.status_code in (303, 302) and r2.status_code in (303, 302), 'скрыто (копия): %s %s; hidden_item: %d' % (r1.status_code, r2.status_code, len(sql_s("select * from hidden_item where kind='company'"))))
proverit_stat({}, 'со скрытыми, сегодня')
proverit_stat({'stat_vse': '1'}, 'со скрытыми, всё время')
t = get('/centro/stats').text
m = re.findall(r'<td><a href="[^"]*/centro\?call_status=([a-z_]+)">(\d+)</a></td>', t)
for kod, n in m:
    nn = total(get('/centro', {'call_status': kod}).text)
    ok(int(n) == nn, '«По результатам звонка» %s: %s, список %d' % (kod, n, nn))
KL.__exit__(None, None, None)
POSLE = (schet(ZH_S), schet(ZH_K))
ok(DO == POSLE, 'боевые базы не тронуты: %s' % (POSLE,), do=DO)
plohih = sum(1 for x in OUT['proverki'] if not x['ok'])
p('ПЛОХИХ ПРОВЕРОК: %d из %d' % (plohih, len(OUT['proverki'])))
io.open(os.path.join(DROP, 'fixF1-prov2_test22.json'), 'w', encoding='utf-8').write(json.dumps(OUT, ensure_ascii=False, default=str))
io.open(os.path.join(DROP, 'fixF1-prov2_test22.txt'), 'w', encoding='utf-8').write('\n'.join(LOG))
import gc; gc.collect()
try: shutil.rmtree(TMP)
except Exception as e: p('копии не удалены (уберутся следующим прогоном)', e)
