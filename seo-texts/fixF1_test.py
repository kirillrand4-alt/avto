# -*- coding: utf-8 -*-
"""fixF1: проверка доводки очереди, фильтров и статистики (по тестам проверяющего prov2).
Только ВРЕМЕННЫЕ копии каталога и базы продаж: синтетические отметки, перезвоны, скрытие – в
копиях; боевые базы сверяются до/после.

  1. перезвон на завтра не наверху, на сегодня и просроченный – наверху; CSV и очередь продавца
     в статистике – в том же порядке;
  2. числа у пунктов фильтров = строк списка (админ, продавец; до и после 10 отметок; во вкладке
     и при выбранном другом фильтре);
  3. статистика = списки по ссылкам (все цифры) после «взял в работу» + скрытия;
  4. регионы продавца – только с его компаниями, число = строк;
  5. рендер админ/продавец 200, «тот же ЛПР», балл компании с пометкой.

  сервер:   python3 zapusk_na_servere.py fixF1_test.py   (отчёт -> дроп fixF1-test.txt/.json)
  локально: python3 fixF1_test.py --lokalno <папка с app> (окружение – loc_env.sh)
"""
import csv, datetime as dt, html as H, io, json, os, re, shutil, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
DROP = r'C:\seostat\drop\drop-storage'
PUT = '/obzvon-meyer'
LOK = '--lokalno' in sys.argv
if not LOK and '--run' not in sys.argv:
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__), '--run'] + sys.argv[1:],
                       capture_output=True, timeout=1650, cwd=KOREN, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-5500:])
    if r.returncode:
        sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(0)
if LOK:
    KOREN = os.path.abspath(sys.argv[sys.argv.index('--lokalno') + 1])
    DROP = os.path.join(os.path.dirname(KOREN), 'test_out')
    os.makedirs(DROP, exist_ok=True)
sys.path.insert(0, KOREN)
if not LOK:
    import zapusk  # noqa: F401
import logging, warnings, glob
warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
for _st in glob.glob(os.path.join(KOREN, '_bekap', 'fixF1t-*')):
    try:
        shutil.rmtree(_st)
    except Exception:
        pass
TMP = os.path.join(KOREN, '_bekap', 'fixF1t-%d' % os.getpid())
os.makedirs(TMP, exist_ok=True)


def kopiya(src, imya):
    dst = os.path.join(TMP, imya)
    s = sqlite3.connect('file:%s?mode=ro' % src, uri=True); d = sqlite3.connect(dst); s.backup(d); d.close(); s.close()
    return dst


ZH_S = os.environ['CENTRO_SALES_DB']; ZH_K = os.environ['CENTRIFUGAL_DB']


def schet(put):
    c = sqlite3.connect('file:%s?mode=ro' % put, uri=True); out = {}
    for t in ('activity_log', 'company_state', 'company_comment', 'company_assignment', 'contact', 'zvonok_sobytie', 'hidden_item'):
        try: out[t] = c.execute('select count(*) from %s' % t).fetchone()[0]
        except Exception: pass
    c.close(); return out


DO = (schet(ZH_S), schet(ZH_K))
S = kopiya(ZH_S, 'sales.db'); K = kopiya(ZH_K, 'katalog.db')
for k in ('CENTRO_SALES_DB', 'PARK_OCHERED_SALES_DB'): os.environ[k] = S
for k in ('CENTRIFUGAL_DB', 'CENTRO_DB', 'PARK_OCHERED_DB'): os.environ[k] = K
from app.api import routes_centro_sales as rcs
from app.api.routes_obzvon import _same_origin
from app.obzvon import create_app
from fastapi.testclient import TestClient
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides[_same_origin] = lambda: None
OUT = {'proverki': [], 'dannye': {}}
LOG = []


def p(*a):
    s = ' '.join(str(x) for x in a); LOG.append(s); print(s); sys.stdout.flush()


def ok(uslovie, tekst, **dop):
    OUT['proverki'].append({'ok': bool(uslovie), 't': tekst, **dop})
    p(('ОК   ' if uslovie else 'ПЛОХО ') + tekst + ((' ' + json.dumps(dop, ensure_ascii=False, default=str)[:700]) if dop and not uslovie else ''))


USERS = {'meyer_admin': {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}}
for i in range(1, 5):
    USERS['meyer%d' % i] = {'id': i, 'username': 'meyer%d' % i, 'role': 'sales', 'is_active': 1}


def kak(u):
    vnutr.dependency_overrides[rcs.current_user] = (lambda U=USERS[u]: U)


KL = TestClient(vnutr)
KL.__enter__()


def get(url, params=None):
    return KL.get(url if url.startswith(PUT) else PUT + url, params=params, follow_redirects=False)


def post(u, dannye, put='/centro/save'):
    kak(u)
    return KL.post(PUT + put, data=dannye, follow_redirects=False)


def total(t):
    m = re.search(r'<b class="total-count">(\d+) компаний</b>', t)
    return int(m.group(1)) if m else -1


def inns_stranicy(t):
    return re.findall(r'<tr data-href="[^"]*/centro\?inn=(\d+)', t)


def spisok_inn(params):
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
for r in sb.execute('select inn, username, assignment_score from company_assignment'):
    naz[str(r['inn'])] = dict(r)
sb.close()
segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()


def razobrat_filtry(t):
    res = []
    for m in re.finditer(r'<select name="([a-z_]+)"[^>]*>(.*?)</select>', t, re.S):
        imya, telo = m.group(1), m.group(2)
        for o in re.finditer(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', telo):
            v, lab = H.unescape(o.group(1)), H.unescape(o.group(2)).strip()
            if not v:
                continue
            mm = re.search(r'[·–]\s*(\d+)\s*$', lab)
            res.append((imya, v, int(mm.group(1)) if mm else None, lab))
    for m in re.finditer(r'<input type="checkbox" name="([a-z_]+)" value="1"[^>]*>([^<]*)</label>', t):
        lab = H.unescape(m.group(2)).strip()
        mm = re.search(r'·\s*(\d+)\s*$', lab)
        res.append((m.group(1), '1', int(mm.group(1)) if mm else None, lab))
    seen = set(); out = []
    for x in res:
        if (x[0], x[1]) not in seen:
            seen.add((x[0], x[1])); out.append(x)
    return out


def proverit_filtry(u, metka, baza=None, vse_punkty=True):
    """Каждый пункт с числом: список с этим пунктом (и прочими параметрами baza) = число."""
    baza = dict(baza or {})
    kak(u)
    t = get('/centro', baza).text
    fl = razobrat_filtry(t)
    plohie = []; regiony_pustye = []; n_chisel = 0; provereno = 0
    for imya, v, n, lab in fl:
        if imya in baza or imya in ('sort', 'call_status', 'assigned_user'):
            continue
        if n is None:
            if imya == 'region':
                regiony_pustye.append(v)
            continue
        n_chisel += 1
        if not vse_punkty and imya == 'region' and provereno > 25:
            continue
        pr = dict(baza); pr[imya] = v
        provereno += 1
        nn = total(get('/centro', pr).text)
        if nn != n:
            plohie.append((imya, v, lab[:60], 'показано %s' % n, 'найдено %s' % nn))
    ok(not plohie and not regiony_pustye,
       '%s %s%s: пунктов с числом %d (проверено %d), каждый находит показанное число' % (
           metka, u, (' при ' + json.dumps(baza, ensure_ascii=False)) if baza else '', n_chisel, provereno),
       plohie=plohie[:20], regiony_bez_chisla=regiony_pustye[:10])
    OUT['dannye']['filtry_%s_%s_%s' % (metka, u, '_'.join(baza))] = {'punkty': fl, 'plohie': plohie}
    return fl


def regiony(u):
    kak(u)
    t = get('/centro').text
    m = re.search(r'<select name="region">(.*?)</select>', t, re.S)
    return [(H.unescape(a), int(b)) for a, b in re.findall(r'<option value="([^"]+)"[^>]*>[^<]*· (\d+)</option>', m.group(1))] if m else []


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
    m = re.findall(r'<td><a href="[^"]*/centro\?call_status=([a-z_]+)">(\d+)</a></td>', t)
    for kod, n in m:
        kak('meyer_admin'); nn = total(get('/centro', {'call_status': kod}).text)
        if int(n) != nn:
            plohie.append(('По результатам звонка ' + kod, n, nn))
    ok(o.status_code == 200 and not plohie, 'статистика %s: ссылок-цифр %d, все = числу строк списка' % (metka, len(ss)), plohie=plohie[:20])
    return t


def csv_inn(params):
    kak('meyer_admin')
    o = KL.get(PUT + '/centro/vygruzka.csv', params=params)
    rr = list(csv.reader(io.StringIO(o.content.decode('utf-8-sig')), delimiter=';'))
    zag, telo = (rr[0], rr[1:]) if rr else ([], [])
    ii = zag.index('ИНН') if 'ИНН' in zag else 2
    return [x[ii] for x in telo], zag, telo


def ochered_v_stat(u):
    kak('meyer_admin')
    t = get('/centro/stats', {'user': u}).text
    hv = t.split('id="ochered-prodavca"')[-1] if 'id="ochered-prodavca"' in t else ''
    return re.findall(r'<td><a href="[^"]*/centro\?inn=(\d+)', hv)


# ===================================================================== 0. рендер
p('== рендер')
for u, url, kod in (('meyer_admin', '/centro', 200), ('meyer_admin', '/centro?call_status=v_rabote', 200),
                    ('meyer_admin', '/centro?inn=1829013726', 200), ('meyer_admin', '/centro/stats', 200),
                    ('meyer_admin', '/centro/stats?user=meyer2', 200), ('meyer_admin', '/centro/vygruzka.csv', 200),
                    ('meyer2', '/centro', 200), ('meyer2', '/centro?inn=1829013726', 200), ('meyer2', '/centro/stats', 403),
                    ('meyer1', '/centro', 200), ('meyer3', '/centro', 200), ('meyer4', '/centro', 200)):
    kak(u); t0 = time.time(); o = get(url)
    ok(o.status_code == kod, '%s %s: %s (%.2f с)' % (u, url, o.status_code, time.time() - t0))
kak('meyer2'); t = get('/centro', {'size': '100'}).text
tz = re.findall(r'class="f1-tot-zhe"[^>]*>(.*?)</span>', t, re.S)
ok(len(tz) >= 2, '«тот же ЛПР» у Ерохина: %d строк, напр. %s' % (len(tz), H.unescape(re.sub(r'<[^>]+>', '', tz[0]))[:140] if tz else '-'))
kak('meyer_admin'); t = get('/centro', {'q': '2344007569'}).text
m = re.search(r'class="f1-konec">([^<]*)', t)
ok(m and '−' not in m.group(1) and '-953' not in re.sub(r'title="[^"]*"', '', t.split('och-ball')[-1][:400]),
   'балл компании с пометкой 2344007569: «%s» (число – в подсказке)' % (m.group(1) if m else '-'))
t = get('/centro', {'inn': '2344007569'}).text
ok('в конце: пометка «недействующая»' in t, 'карточка 2344007569: «в конце: пометка …»')

# ===================================================================== 1. перезвон
p('== перезвон после «не дозвонился»: место в очереди')
kak('meyer1'); vs0, n0 = spisok_inn({})
y, z, w = vs0[100], vs0[110], vs0[120]
zavtra = (segodnya + dt.timedelta(days=1)).isoformat() + 'T10:00'
segodnya_vecher = segodnya.isoformat() + 'T23:50'
vchera = (segodnya - dt.timedelta(days=1)).isoformat() + 'T09:00'
r1 = post('meyer1', {'inn': y, 'call_result': 'ne_dozvonilsya', 'comment': 'перезвонить завтра', 'next_contact_at': zavtra})
kak('meyer1'); vs1, _ = spisok_inn({})
ok(r1.status_code == 303 and y in vs1 and vs1.index(y) == vs0.index(y),
   'перезвон НА ЗАВТРА: место до %d, после %d (на своём месте по баллу); №1 – %s' % (vs0.index(y) + 1, vs1.index(y) + 1 if y in vs1 else -1, vs1[0]))
r2 = post('meyer1', {'inn': z, 'call_result': 'ne_dozvonilsya', 'comment': 'перезвонить сегодня', 'next_contact_at': segodnya_vecher})
kak('meyer1'); vs2, _ = spisok_inn({})
ok(r2.status_code == 303 and vs2[0] == z, 'перезвон НА СЕГОДНЯ (%s): место %d → %d' % (segodnya_vecher, vs0.index(z) + 1, vs2.index(z) + 1))
r3 = post('meyer1', {'inn': w, 'call_result': 'ne_dozvonilsya', 'comment': 'просрочен', 'next_contact_at': vchera})
kak('meyer1'); vs3, _ = spisok_inn({})
ok(r3.status_code == 303 and vs3[:2] == [w, z] and vs3.index(y) == vs0.index(y) + 2,
   'просроченный (%s) – №1, сегодняшний – №2, завтрашний – %d (сдвинут на 2 поднявшихся)' % (vchera, vs3.index(y) + 1))
ci, zag, telo = csv_inn({'assigned_user': 'meyer1'})
ok(ci == vs3, 'CSV директора по meyer1 – тот же порядок (%d строк)' % len(ci))
ok('Скрыта' in zag, 'CSV: колонка «Скрыта»')
ci_all, _, _ = csv_inn({})
kak('meyer_admin'); vs_all, _ = spisok_inn({})
ok(ci_all == vs_all, 'CSV директора «вся очередь» = список (%d)' % len(ci_all))
oq = ochered_v_stat('meyer1')
ok(oq[:len(vs3)] == vs3, 'очередь meyer1 в статистике – тот же порядок (%d строк)' % len(oq))
kak('meyer_admin'); t = get('/centro/stats', {'user': 'meyer1'}).text
ok('наверху – перезвоны, срок которых наступил' in t and 'сначала новые, затем перезвоны по' in t, 'подпись порядка в статистике')

# ===================================================================== 2. фильтры до отметок
p('== числа у фильтров (после трёх «не дозвонился» с перезвонами)')
proverit_filtry('meyer_admin', 'до')
proverit_filtry('meyer1', 'до')
proverit_filtry('meyer2', 'до')
rg = regiony('meyer1')
ok(rg and all(n > 0 for _, n in rg), 'регионы meyer1: %d, у каждого число > 0' % len(rg))
rg_a = regiony('meyer_admin')
ok(len(rg_a) > len(rg), 'регионы директора: %d (все регионы каталога, с числами)' % len(rg_a))

# ===================================================================== 3. 10 отметок
p('== 10 синтетических отметок (копия)')
och = {}
for u in ('meyer1', 'meyer2', 'meyer3', 'meyer4'):
    kak(u); och[u] = spisok_inn({})[0]
plan = [('meyer1', och['meyer1'][3], 'v_rabote', {}), ('meyer1', och['meyer1'][4], 'ne_ponravilas', {'prichina': 'нет потребности'}),
        ('meyer1', och['meyer1'][5], 'dubl', {}), ('meyer2', och['meyer2'][3], 'v_rabote', {'comment': 'КП'}),
        ('meyer2', och['meyer2'][4], 'ne_ponravilas', {'prichina': 'не наш профиль'}),
        ('meyer3', och['meyer3'][3], 'ne_ponravilas', {'prichina': 'компания закрыта', 'comment': 'ликвидируют'}),
        ('meyer3', och['meyer3'][4], 'v_rabote', {}), ('meyer4', och['meyer4'][3], 'ne_ponravilas', {'prichina': 'уже купили у конкурентов'}),
        ('meyer_admin', och['meyer4'][4], 'v_rabote', {'comment': 'админ за продавца'}),
        ('meyer2', och['meyer2'][5], 'lpr_nomer', {'lpr_fio': 'Тестов Тест Тестович', 'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '8 (900) 000-00-00'})]
kody = []
for u, inn, rez, dop in plan:
    d = {'inn': inn, 'call_result': rez}; d.update(dop)
    kody.append(post(u, d).status_code)
ok(all(k == 303 for k in kody), 'отметки сохранены: %s' % kody)
proverit_filtry('meyer_admin', 'после')
proverit_filtry('meyer1', 'после')
proverit_filtry('meyer2', 'после')
proverit_filtry('meyer_admin', 'после', {'call_status': 'v_rabote'})
proverit_filtry('meyer_admin', 'после', {'segment': '3 пищевые'}, vse_punkty=False)
proverit_filtry('meyer3', 'после', {'lpr_mobilnyy': '1'})

# ===================================================================== 4. скрытые и статистика
p('== скрытые компании и цифры статистики')
x1 = och['meyer1'][3]          # взят в работу meyer1 – скрываем
x3 = och['meyer2'][21]         # новый у meyer2 – скрываем
r1 = post('meyer1', {'inn': x1, 'kind': 'company', 'value': x1, 'reason': 'проверка'}, '/centro/hide')
r2 = post('meyer2', {'inn': x3, 'kind': 'company', 'value': x3, 'reason': 'проверка'}, '/centro/hide')
ok(r1.status_code in (302, 303) and r2.status_code in (302, 303), 'скрыто (копия): %s %s' % (r1.status_code, r2.status_code))
kak('meyer1'); vs, _ = spisok_inn({'call_status': 'v_rabote'})
ok(x1 not in vs, 'у продавца скрытая во вкладке «Взял в работу» не видна')
kak('meyer_admin'); t = get('/centro', {'call_status': 'v_rabote', 'size': '100'}).text
ok(x1 in inns_stranicy(t) and 'f1-skryta' in t, 'у директора во вкладке «Взял в работу» скрытая видна с пометкой «скрыта»')
kak('meyer_admin'); vs, _ = spisok_inn({})
ok(x3 not in vs and x1 not in vs, '«Вся очередь» директора – без скрытых')
ci, zag, telo = csv_inn({'call_status': 'v_rabote'})
ii = zag.index('Скрыта') if 'Скрыта' in zag else -1
ok(x1 in ci and ii >= 0 and telo[ci.index(x1)][ii].startswith('скрыта'), 'CSV вкладки: скрытая с пометкой «скрыта»')
t = proverit_stat({}, 'сегодня (со скрытыми)')
proverit_stat({'stat_vse': '1'}, 'всё время (со скрытыми)')
proverit_stat({'stat_user': 'meyer1'}, 'meyer1')
proverit_stat({'stat_user': 'meyer2', 'stat_vse': '1'}, 'meyer2, всё время')
proverit_stat({'stat_ot': (segodnya - dt.timedelta(days=6)).isoformat()}, '7 дней')
oq = ochered_v_stat('meyer2'); kak('meyer2'); vs2, _ = spisok_inn({})
ok(oq[:len(vs2)] == vs2 and x3 not in oq, 'очередь meyer2 в статистике = его список, без скрытой (%d)' % len(oq))
# лента: ссылка на скрытую открывает карточку
kak('meyer_admin'); t = get('/centro/stats').text
ss = [H.unescape(u) for u in re.findall(r'<a href="(%s/centro\?inn=%s[^"]*)"' % (re.escape(PUT), x1), t)]
ok(ss and all(get(u).status_code == 200 for u in ss), 'лента: ссылка на скрытую компанию открывает карточку (%s)' % ss[:1])
t = get(ss[0]).text if ss else ''
ok('>скрыта<' in t or 'скрыта</span>' in t, 'карточка скрытой у директора – пометка «скрыта»')
proverit_filtry('meyer_admin', 'со скрытыми', {'call_status': 'v_rabote'})
proverit_filtry('meyer_admin', 'со скрытыми')

KL.__exit__(None, None, None)
POSLE = (schet(ZH_S), schet(ZH_K))
ok(DO == POSLE, 'боевые базы не тронуты: %s' % (POSLE,), do=DO)
plohih = sum(1 for x in OUT['proverki'] if not x['ok'])
p('ПЛОХИХ ПРОВЕРОК: %d из %d' % (plohih, len(OUT['proverki'])))
io.open(os.path.join(DROP, 'fixF1-test.json'), 'w', encoding='utf-8').write(json.dumps(OUT, ensure_ascii=False, default=str))
io.open(os.path.join(DROP, 'fixF1-test.txt'), 'w', encoding='utf-8').write('\n'.join(LOG))
import gc; gc.collect()
try: shutil.rmtree(TMP)
except Exception as e: p('копии не удалены (уберутся следующим прогоном)', e)
