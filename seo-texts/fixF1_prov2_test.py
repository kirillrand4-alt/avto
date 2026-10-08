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
FAZY = set(sys.argv[sys.argv.index('--run') + 1:]) or {'filtry', 'poisk', 'sob', 'stat', 'csv'}
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

# ===================================================================== 1. фильтры главной
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
def proverit_filtry(u, metka):
    kak(u)
    t = get('/centro').text
    vse = total(t)
    fl = razobrat_filtry(t)
    plohie = []; bez_chisla = []
    for imya, v, n, lab in fl:
        if imya in ('sort', 'call_status', 'assigned_user', 'region', 'segment_dop') and n is None:
            if imya == 'region':
                tt = get('/centro', {imya: v}).text
                if total(tt) <= 0:
                    plohie.append((imya, v, 'регион из списка ничего не нашёл', total(tt)))
            continue
        if n is None:
            bez_chisla.append((imya, v, lab[:40])); continue
        tt = get('/centro', {imya: v}).text
        if total(tt) != n:
            plohie.append((imya, v, lab[:60], 'показано %s' % n, 'найдено %s' % total(tt)))
    ok(not plohie, '%s %s: пунктов фильтров с числом %d, каждый находит показанное число' % (metka, u, sum(1 for x in fl if x[2] is not None)),
       plohie=plohie[:30])
    OUT['dannye']['filtry_%s_%s' % (metka, u)] = {'vsego': vse, 'punkty': fl, 'plohie': plohie, 'bez_chisla': bez_chisla}
    return fl
if 'filtry' in FAZY:
    p('== фильтры главной (состояние = боевое)')
    kak('meyer_admin'); t = get('/centro').text
    ok(total(t) == 600, 'админ, «Вся очередь»: %d компаний' % total(t))
    for u in ('meyer1', 'meyer2', 'meyer3', 'meyer4'):
        kak('meyer_admin'); n_a = total(get('/centro', {'assigned_user': u}).text)
        kak(u); n_u = total(get('/centro').text)
        ok(n_a == 150 and n_u == 150, '%s: у админа по продавцу %d, у самого продавца %d (ожидается 150)' % (u, n_a, n_u))
    fa = proverit_filtry('meyer_admin', 'до')
    fs = proverit_filtry('meyer1', 'до')
    kak('meyer_admin'); t = get('/centro').text
    m = re.search(r'<select name="call_status">(.*?)</select>', t, re.S)
    opc = [(H.unescape(a), H.unescape(b)) for a, b in re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1))] if m else []
    dopusk = {'', 'new', 'v_rabote', 'ne_ponravilas', 'dubl', 'ne_dozvonilsya', 'lpr_nomer'}
    ok(m and {v for v, _ in opc} <= dopusk, 'фильтр «Результат звонка»: %s' % [b for _, b in opc], lishnie=[x for x in opc if x[0] not in dopusk])

# ===================================================================== 2. поиск
def iskat(u, q):
    kak(u); t = get('/centro', {'q': q}).text
    return total(t), inns_stranicy(t)
if 'poisk' in FAZY:
    p('== поиск')
    kb = sqlite3.connect('file:%s?mode=ro' % K, uri=True); kb.row_factory = sqlite3.Row
    obrazcy = []
    for r in kb.execute("select inn, value, person, position from contact where kind='phone' order by id"):
        osn, dob = cat._razdelit_dobavochnyy(r['value'])
        d = re.sub(r'\D', '', osn)
        if len(d) == 11 and d[1] == '9' and r['inn'] in naz:
            obrazcy.append((r['inn'], d[1:], 'мобильный'))
        elif len(d) == 11 and d[1] in '348' and r['inn'] in naz and dob and not any(o[2] == 'с добавочным' for o in obrazcy):
            obrazcy.append((r['inn'], d[1:], 'с добавочным'))
        if len([o for o in obrazcy if o[2] == 'мобильный']) >= 3 and any(o[2] == 'с добавочным' for o in obrazcy):
            break
    pl = kb.execute("select inn, phone from person where coalesce(phone,'')<>'' and coalesce(chuzhoy_istochnik,'')='' limit 50").fetchall()
    for r in pl:
        d = re.sub(r'\D', '', cat._razdelit_dobavochnyy(r['phone'])[0])
        if len(d) == 11 and r['inn'] in naz:
            if not kb.execute("select 1 from contact where inn=? and value like ?", (r['inn'], '%' + d[-4:] + '%')).fetchone():
                obrazcy.append((r['inn'], d[1:], 'только в «Людях предприятия»')); break
    rez_nomer = []
    for inn, k10, vid in obrazcy:
        formy = {'+7XXXXXXXXXX': '+7' + k10, '8XXXXXXXXXX': '8' + k10,
                 '8 (XXX) XXX-XX-XX': '8 (%s) %s-%s-%s' % (k10[:3], k10[3:6], k10[6:8], k10[8:]),
                 '+7 XXX XXX-XX-XX': '+7 %s %s-%s-%s' % (k10[:3], k10[3:6], k10[6:8], k10[8:]),
                 'XXXXXXXXXX': k10, 'XXX-XX-XX (7 цифр)': '%s-%s-%s' % (k10[3:6], k10[6:8], k10[8:])}
        for nf, q in formy.items():
            for u in ('meyer_admin', naz[inn]['username']):
                n, ii = iskat(u, q)
                rez_nomer.append({'inn': inn, 'vid': vid, 'forma': nf, 'kto': u, 'naydeno': n, 'est': inn in ii})
            # продавец, у которого этой компании нет, найти не должен
        chuzh = next(x for x in ('meyer1', 'meyer2', 'meyer3', 'meyer4') if x != naz[inn]['username'])
        n, ii = iskat(chuzh, '+7' + k10)
        rez_nomer.append({'inn': inn, 'vid': vid, 'forma': '+7… чужим продавцом', 'kto': chuzh, 'naydeno': n, 'est': inn in ii, 'chuzhoy': 1})
    plohie = [x for x in rez_nomer if (not x.get('chuzhoy') and not x['est']) or (x.get('chuzhoy') and x['est'])]
    ok(rez_nomer and not plohie, 'поиск по номеру: %d образцов × 6 форм × (админ, продавец) + чужой продавец' % len(obrazcy), plohie=plohie[:20])
    OUT['dannye']['poisk_nomer'] = rez_nomer
    # город
    goroda = []
    for inn, c in list(COMP.items()):
        m = re.search(r'\bг\. ([А-ЯЁ][а-яё]+(?:-[А-ЯЁа-яё]+)?)', str(c.get('adres') or ''))
        if m and len(goroda) < 4 and m.group(1) not in [g[1] for g in goroda] and m.group(1) not in ('Москва', 'Санкт-Петербург'):
            goroda.append((inn, m.group(1)))
    m = re.search(r'\b(?:с|пос|п|ст-ца|рп|д|х|пгт)\. ([А-ЯЁ][а-яё]+)', ' '.join(str(c.get('adres') or '') for c in list(COMP.values())[100:140]))
    sela = []
    for inn, c in COMP.items():
        mm = re.search(r'\b(?:с|пос|п|ст-ца|рп|д|х|пгт)\. ([А-ЯЁ][а-яё]{4,})', str(c.get('adres') or ''))
        if mm and len(sela) < 2:
            sela.append((inn, mm.group(1)))
    rez_gorod = []
    for inn, g in goroda + sela:
        for u in ('meyer_admin', naz[inn]['username']):
            n, ii = iskat(u, g)
            kak(u); vse, _n = spisok_inn({'q': g})
            sovp = sum(1 for i in vse if g.lower().replace('ё', 'е') in (str(COMP[i].get('adres') or '') + ' ' + str(COMP[i].get('region') or '')).lower().replace('ё', 'е'))
            rez_gorod.append({'inn': inn, 'gorod': g, 'kto': u, 'naydeno': n, 'est': inn in vse, 'iz_nih_v_adrese': sovp})
    ok(all(x['est'] for x in rez_gorod), 'поиск по городу/селу: %s' % [(x['gorod'], x['kto'], x['naydeno'], x['iz_nih_v_adrese']) for x in rez_gorod],
       plohie=[x for x in rez_gorod if not x['est']])
    OUT['dannye']['poisk_gorod'] = rez_gorod
    # ФИО
    fio = kb.execute("select inn, person from contact where kind='phone' and length(coalesce(person,''))>12 and person like '% % %' and coalesce(chuzhoy_istochnik,'')='' limit 3").fetchall()
    fio += kb.execute("select inn, person from person where length(coalesce(person,''))>12 and person like '% % %' and coalesce(chuzhoy_istochnik,'')='' limit 2").fetchall()
    rez_fio = []
    for r in fio:
        if r['inn'] not in naz:
            continue
        polnoe = ' '.join(str(r['person']).split())
        fam = polnoe.split()[0]
        for q in (polnoe, fam, polnoe.lower()):
            for u in ('meyer_admin', naz[r['inn']]['username']):
                kak(u); vse, n = spisok_inn({'q': q})
                rez_fio.append({'inn': r['inn'], 'q': ('полное' if q == polnoe else 'фамилия' if q == fam else 'строчными'), 'kto': u, 'naydeno': n, 'est': r['inn'] in vse})
    ok(rez_fio and all(x['est'] for x in rez_fio), 'поиск по ФИО (полное, фамилия, строчными): %d запросов' % len(rez_fio), plohie=[x for x in rez_fio if not x['est']])
    OUT['dannye']['poisk_fio'] = rez_fio
    kb.close()
    # ИНН
    rez_inn = []
    for inn in list(naz)[:6]:
        u = naz[inn]['username']
        for kto in ('meyer_admin', u):
            n, ii = iskat(kto, inn)
            rez_inn.append({'inn': inn, 'kto': kto, 'naydeno': n, 'est': ii == [inn]})
        chuzh = next(x for x in ('meyer1', 'meyer2', 'meyer3', 'meyer4') if x != u)
        n, ii = iskat(chuzh, inn)
        rez_inn.append({'inn': inn, 'kto': chuzh, 'naydeno': n, 'est': n == 0, 'chuzhoy': 1})
    ok(all(x['est'] for x in rez_inn), 'поиск по ИНН: ровно 1 строка у админа и владельца, 0 у чужого продавца', plohie=[x for x in rez_inn if not x['est']])
    OUT['dannye']['poisk_inn'] = rez_inn

# ===================================================================== 3. новые результаты (копия)
def post(u, dannye):
    kak(u)
    return KL.post(PUT + '/centro/save', data=dannye, follow_redirects=False)
def sql_s(q, a=()):
    c = sqlite3.connect(S); c.row_factory = sqlite3.Row
    try: return [dict(r) for r in c.execute(q, a)]
    finally: c.close()
def sql_k(q, a=()):
    c = sqlite3.connect(K); c.row_factory = sqlite3.Row
    try: return [dict(r) for r in c.execute(q, a)]
    finally: c.close()
def stupen1(u, n=1, stupeni=(1,)):
    return [i for i in ochered(u) if naz[i]['stupen_ocheredi'] in stupeni and not COMP[i].get('pometka_ocheredi')][:n]
segodnya = (dt.datetime.utcnow() + dt.timedelta(hours=3)).date()
if 'sob' in FAZY:
    p('== новые результаты звонка (временная копия базы продаж и каталога)')
    A = ochered('meyer1'); B = ochered('meyer2'); C = ochered('meyer3'); D = ochered('meyer4')
    a0, a1 = A[0], A[5]
    # --- «Не дозвонился»
    r1 = post('meyer1', {'inn': a0, 'call_result': 'ne_dozvonilsya', 'comment': 'не берут трубку (проверка)'})
    r2 = post('meyer1', {'inn': a0, 'call_result': 'ne_dozvonilsya', 'comment': ''})
    zavtra = (segodnya + dt.timedelta(days=1)).isoformat() + 'T10:00'
    r3 = post('meyer1', {'inn': a1, 'call_result': 'ne_dozvonilsya', 'comment': 'перезвонить', 'next_contact_at': zavtra})
    ok(r1.status_code == 303 and r2.status_code == 303 and r3.status_code == 303, '«Не дозвонился»: сохранение 303 (%s %s %s)' % (r1.status_code, r2.status_code, r3.status_code))
    z = sql_s("select * from zvonok_sobytie where vid='ne_dozvonilsya'")
    ok(len(z) == 3 and {x['inn'] for x in z} == {a0, a1} and all(x['state_user'] == 'meyer1' for x in z), 'zvonok_sobytie: 3 попытки, обе компании, засчитаны meyer1')
    st = sql_s('select * from company_state where inn=?', (a0,))
    ok(not st or (st[0]['call_result'] or 'new') == 'new', 'статус компании не изменился (%s)' % (st[0]['call_result'] if st else 'нет записи'))
    kak('meyer1'); vse1, n1 = spisok_inn({})
    ok(n1 == 150 and a0 in vse1 and a1 in vse1, 'компании остались в очереди meyer1 (%d строк; %s на месте %s)' % (n1, a0, vse1.index(a0) + 1 if a0 in vse1 else '-'))
    t = get('/centro').text
    ok('не дозвонился: 2' in t, 'в списке у компании «не дозвонился: 2»')
    t = get('/centro', {'inn': a0}).text
    ok(t.count('Не дозвонился') >= 1 and re.search(r'попыт\w*[^<]{0,40}2|2[^<]{0,20}попыт', t) is not None, 'карточка показывает 2 попытки')
    vs, n = spisok_inn({'call_status': 'ne_dozvonilsya'})
    ok(set(vs) == {a0, a1}, 'вкладка/фильтр «Не дозвонился»: %d (%s)' % (n, vs))
    ok(any('Не дозвонился. не берут трубку' in str(x['body']) for x in sql_s('select body from company_comment where inn=?', (a0,))), 'комментарий попытки сохранён')
    per = sql_s('select next_contact_at, call_result from company_state where inn=?', (a1,))
    ok(per and per[0]['next_contact_at'] == zavtra and per[0]['call_result'] == 'new', 'перезвон при «не дозвонился»: следующий контакт %s, результат new' % per)
    # --- «Получен личный номер ЛПР» продавцом
    b0 = stupen1('meyer2')[0]
    do_b = dict(naz[b0]); poz_do = B.index(b0) + 1
    do_flagi = sql_k('select lpr_mobilnyy, lpr_s_fio, has_tech, lpr_roli, lpr_kratko from company where inn=?', (b0,))[0]
    kak('meyer2'); do_f = {k: total(get('/centro', {k: '1'}).text) for k in ('lpr_mobilnyy', 'lpr_fio', 'has_tech', 'has_role_phone')}
    r = post('meyer2', {'inn': b0, 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович', 'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '8 (900) 000-00-00', 'comment': 'проверка'})
    ok(r.status_code == 303, '«Получен личный номер ЛПР» (meyer2): %s' % r.status_code)
    zs = sql_s("select * from zvonok_sobytie where vid='lpr_nomer' and inn=?", (b0,))
    ok(len(zs) == 1 and zs[0]['nomer'] == '+79000000000' and zs[0]['katalog_contact_id'], 'событие записано, номер +79000000000, каталог: %s' % (zs[0]['katalog_itog'] if zs else '-'))
    kk = sql_k("select * from contact where inn=? and source like 'от продавца%'", (b0,))
    ok(len(kk) == 1 and kk[0]['person'] == 'Тестов Тест Тестович' and kk[0]['position'] == 'главный инженер', 'контакт в КОПИИ каталога: %s' % ({k: kk[0].get(k) for k in ('value', 'role', 'phone_type', 'source', 'is_tech', 'has_role', 'istochniki')} if kk else '-'))
    zh_k = sqlite3.connect('file:%s?mode=ro' % ZH_K, uri=True)
    ok(zh_k.execute("select count(*) from contact where source like 'от продавца%' and person='Тестов Тест Тестович'").fetchone()[0] == 0, 'боевой каталог не тронут')
    zh_k.close()
    posle_flagi = sql_k('select lpr_mobilnyy, lpr_s_fio, has_tech, lpr_roli, lpr_kratko, prioritet_pochemu from company where inn=?', (b0,))[0]
    ok(posle_flagi['lpr_mobilnyy'] == 1 and posle_flagi['lpr_s_fio'] >= 1 and posle_flagi['has_tech'] == 1 and 'главный инженер' in posle_flagi['lpr_roli'],
       'флаги компании выросли: было %s → стало %s' % ({k: do_flagi[k] for k in ('lpr_mobilnyy', 'lpr_s_fio', 'has_tech', 'lpr_roli')}, {k: posle_flagi[k] for k in ('lpr_mobilnyy', 'lpr_s_fio', 'has_tech', 'lpr_roli')}))
    pa = sql_s('select assignment_score, stupen_ocheredi from company_assignment where inn=?', (b0,))[0]
    ok(pa['stupen_ocheredi'] == 4 and abs(pa['assignment_score'] - (do_b['assignment_score'] + 600)) < 0.2,
       'ступень 1→%s, балл %.1f→%.1f' % (pa['stupen_ocheredi'], do_b['assignment_score'], pa['assignment_score']))
    kak('meyer2'); vs2, _ = spisok_inn({})
    ok(b0 in vs2 and vs2.index(b0) + 1 < poz_do, 'место в очереди meyer2: %d → %d' % (poz_do, vs2.index(b0) + 1 if b0 in vs2 else -1))
    posle_f = {k: total(get('/centro', {k: '1'}).text) for k in ('lpr_mobilnyy', 'lpr_fio', 'has_tech', 'has_role_phone')}
    ok(all(posle_f[k] == do_f[k] + 1 for k in posle_f), 'фильтры продавца +1: было %s, стало %s' % (do_f, posle_f))
    t = get('/centro', {'inn': b0}).text
    ok('Тестов Тест Тестович' in t and '+7 900 000-00-00' in t, 'карточка: ЛПР и номер «+7 900 000-00-00» видны')
    ok('tel:+79000000000' in t, 'ссылка звонка tel:+79000000000')
    kak('meyer2'); n, ii = iskat('meyer2', '89000000000')
    ok(b0 in ii, 'поиск по новому номеру находит компанию (%d)' % n)
    vs, n = spisok_inn({'call_status': 'lpr_nomer'})
    ok(vs == [b0], 'фильтр «Получен личный номер ЛПР»: %s' % vs)
    r = post('meyer2', {'inn': b0, 'call_result': 'lpr_nomer', 'lpr_fio': 'Тестов Тест Тестович', 'lpr_dolzhnost': 'главный инженер', 'lpr_nomer': '+79000000000'})
    ok(r.status_code == 303 and len(sql_s("select * from zvonok_sobytie where vid='lpr_nomer' and inn=?", (b0,))) == 1
       and len(sql_k("select * from contact where inn=? and source like 'от продавца%'", (b0,))) == 1, 'повтор того же номера не считается второй раз')
    # --- номер ЛПР админом за продавца, коммерческий директор, рабочий с добавочным
    c0 = stupen1('meyer3')[0]; do_c = dict(naz[c0])
    r = post('meyer_admin', {'inn': c0, 'call_result': 'lpr_nomer', 'lpr_fio': '', 'lpr_dolzhnost': 'коммерческий директор', 'lpr_nomer': '+7 495 000-00-00 доб. 12'})
    zc = sql_s("select * from zvonok_sobytie where vid='lpr_nomer' and inn=?", (c0,))
    kc = sql_k("select * from contact where inn=? and source like 'от продавца%'", (c0,))
    pc = sql_s('select assignment_score, stupen_ocheredi from company_assignment where inn=?', (c0,))[0]
    ok(r.status_code == 303 and zc and zc[0]['state_user'] == 'meyer3' and zc[0]['username'] == 'meyer_admin', 'админ за продавца: засчитано meyer3, нажал meyer_admin')
    ok(kc and kc[0]['phone_type'] == 'рабочий с добавочным' and 'доб. 12' in kc[0]['value'], 'контакт: %s' % ({k: kc[0].get(k) for k in ('value', 'phone_type', 'role')} if kc else '-'))
    ok(pc['stupen_ocheredi'] == 2 and abs(pc['assignment_score'] - (do_c['assignment_score'] + 200)) < 0.2, 'ступень 1→%s (ЛПР рабочий), балл %.1f→%.1f' % (pc['stupen_ocheredi'], do_c['assignment_score'], pc['assignment_score']))
    kak('meyer_admin'); t = get('/centro', {'inn': c0}).text
    ok('tel:+74950000000,12' in t, 'ссылка звонка с добавочным tel:+74950000000,12')
    # --- ошибки ввода
    e1 = post('meyer2', {'inn': B[3], 'call_result': 'lpr_nomer', 'lpr_fio': 'Иванов', 'lpr_dolzhnost': 'директор', 'lpr_nomer': '12345'})
    e2 = post('meyer2', {'inn': B[3], 'call_result': 'lpr_nomer', 'lpr_fio': '', 'lpr_dolzhnost': '', 'lpr_nomer': '+79000000001'})
    e3 = post('meyer2', {'inn': A[3], 'call_result': 'ne_dozvonilsya'})
    e4 = post('meyer2', {'inn': B[3], 'call_result': 'ne_ponravilas', 'prichina': 'не нравится'})
    ok((e1.status_code, e2.status_code, e3.status_code, e4.status_code) == (422, 422, 404, 422),
       'ошибки: неверный номер %s, без ФИО и должности %s, чужая компания %s, причина не из списка %s' % (e1.status_code, e2.status_code, e3.status_code, e4.status_code))
    # --- причины отказа
    PR = rcs.PRICHINY_NE_PONRAVILAS
    novye = ['нет потребности', 'не наш профиль', 'компания закрыта', 'не та компания / не ЛПР']
    ok(all(x in PR for x in novye), 'новые причины в списке: %s' % PR)
    plan = [('meyer1', A[10], 'нет потребности', 'сами сказали'), ('meyer2', B[10], 'не наш профиль', ''),
            ('meyer3', C[10], 'компания закрыта', 'ликвидируют'), ('meyer4', D[10], 'не та компания / не ЛПР', ''),
            ('meyer4', D[11], 'уже купили у конкурентов', 'Атлас'), ('meyer1', A[11], 'нет потребности', '')]
    for u, inn, prich, kom in plan:
        r = post(u, {'inn': inn, 'call_result': 'ne_ponravilas', 'prichina': prich, 'comment': kom})
        st = sql_s('select call_result, prichina from company_state where inn=? and username=?', (inn, u))
        km = sql_s('select body, prichina from company_comment where inn=? order by id desc limit 1', (inn,))
        ok(r.status_code == 303 and st and st[0]['prichina'] == prich and km and km[0]['prichina'] == prich,
           'отказ «%s» (%s): state.prichina=%s, comment.prichina=%s' % (prich, u, st[0]['prichina'] if st else '-', km[0]['prichina'] if km else '-'))
    r = post('meyer1', {'inn': A[12], 'call_result': 'v_rabote', 'comment': 'ждут КП'})
    r = post('meyer2', {'inn': B[12], 'call_result': 'dubl', 'comment': ''})
    r = post('meyer_admin', {'inn': D[12], 'call_result': 'v_rabote', 'comment': 'админ за продавца'})
    r = post('meyer1', {'inn': a0, 'call_result': 'v_rabote', 'comment': 'дозвонился'})     # компания с попытками – в работу
    kak('meyer1'); vs, n = spisok_inn({})
    ok(n == 150 - 4 and A[10] not in vs and A[12] not in vs, 'очередь meyer1 после 4 отметок: %d (обработанные ушли из «Вся очередь»)' % n)
    vs, n = spisok_inn({'call_status': 'ne_ponravilas'})
    ok(set(vs) == {A[10], A[11]}, 'вкладка «Не понравилась» у meyer1: %s' % vs)
    for prich in novye:
        kak('meyer_admin'); vs, n = spisok_inn({'prichina': prich})
        ozh = [inn for u, inn, pr, k in plan if pr == prich]
        ok(sorted(vs) == sorted(ozh), 'фильтр причины «%s»: %d (ожидалось %d)' % (prich, n, len(ozh)))
    kak('meyer_admin'); vs, n = spisok_inn({'bez_poyasneniya': '1'})
    ozh = [inn for u, inn, pr, k in plan if not k]
    ok(sorted(vs) == sorted(ozh), 'отказ без пояснения: %d (ожидалось %d)' % (n, len(ozh)))
    OUT['dannye']['sinteticheskie'] = {'a0': a0, 'a1': a1, 'b0': b0, 'c0': c0, 'plan': plan}
    # фильтры после отметок: число у пункта = строк по нему?
    proverit_filtry('meyer_admin', 'posle')
    proverit_filtry('meyer1', 'posle')

# ===================================================================== 4. статистика: каждая ссылка-цифра
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
    OUT['dannye']['stat_' + metka] = {'ssylki': ss, 'plohie': plohie}
    return t
if 'stat' in FAZY:
    p('== статистика')
    kak('meyer1'); ok(get('/centro/stats').status_code == 403, 'статистика продавцу: 403')
    t_seg = proverit_stat({}, 'segodnya')
    t_7 = proverit_stat({'stat_ot': (segodnya - dt.timedelta(days=6)).isoformat()}, '7dney')
    t_vse = proverit_stat({'stat_vse': '1'}, 'vse')
    t_u = proverit_stat({'stat_user': 'meyer1'}, 'meyer1')
    proverit_stat({'stat_user': 'meyer3', 'stat_vse': '1'}, 'meyer3_vse')
    io.open(os.path.join(DROP, 'fixF1-prov2-stats.html'), 'w', encoding='utf-8').write(t_seg)
    io.open(os.path.join(DROP, 'fixF1-prov2-stats-vse.html'), 'w', encoding='utf-8').write(t_vse)
    # 4×150
    m = re.findall(r'<td><a href="[^"]*user=(meyer\d)[^"]*#ochered-prodavca">[^<]*</a>[^<]*</td>\s*<td>[^<]*</td>\s*<td>(\d+)</td>', t_seg)
    ok(sorted(m) == [('meyer%d' % i, '150') for i in range(1, 5)], '«По продавцам»: назначено %s' % m)
    ok('meyer_admin' not in re.sub(r'<header.*?</header>|<nav.*?</nav>', '', t_seg, flags=re.S) or True, '')
    adm = sql_s("select fio from users where username='meyer_admin'")
    adm_fio = (adm[0]['fio'] or '').strip() if adm else ''
    tabl = re.sub(r'(?s)^.*?<main', '<main', t_seg)
    vhod = [x for x in ('meyer_admin', adm_fio) if x and re.search(r'<td>\s*%s' % re.escape(x), tabl)]
    ok(not vhod, 'строки meyer_admin в таблицах нет (ФИО админа: %s)' % (adm_fio or '—'), naydeno=vhod)
    # «всё время»
    b = re.findall(r'<a href="([^"]*/centro/stats[^"]*)">(сегодня|вчера|7 дней|30 дней|всё время)</a>', t_seg)
    bvse = [H.unescape(u) for u, nz in b if nz == 'всё время']
    bseg = [H.unescape(u) for u, nz in b if nz == 'сегодня']
    ok(bvse and 'stat_vse=1' in bvse[0], '«всё время» ведёт на свой период: %s' % bvse)
    mm = re.search(r'за всё время \(с (\d\d\.\d\d\.\d{4})', t_vse)
    ok(mm is not None and '<b>всё время</b>' in t_vse, '«всё время» открыт: подпись «%s», кнопка активна' % (mm.group(0) if mm else '-'))
    t_7s = get('/centro/stats', {'stat_ot': (segodnya - dt.timedelta(days=6)).isoformat()}).text
    ok('<b>7 дней</b>' in t_7s and '<b>всё время</b>' not in t_7s, 'на 7 днях активна только «7 дней»')
    # якорь к очереди продавца
    ya = re.findall(r'href="([^"]*user=meyer2[^"]*)#ochered-prodavca"', t_seg)
    t_q = get(H.unescape(ya[0])).text if ya else ''
    stroki_q = re.findall(r'<td><a href="[^"]*/centro\?inn=(\d+)', t_q.split('id="ochered-prodavca"')[-1]) if 'id="ochered-prodavca"' in t_q else []
    kak('meyer2'); vs2, n2 = spisok_inn({}); kak('meyer_admin')
    ok(ya and 'id="ochered-prodavca"' in t_q, 'ссылка на продавца с якорем #ochered-prodavca, цель есть на странице')
    ok(stroki_q[:len(vs2)] == vs2, 'очередь продавца в статистике = его список (%d строк, первые %s)' % (len(stroki_q), stroki_q[:3]),
       raznica=[(i, a, b) for i, (a, b) in enumerate(zip(stroki_q, vs2)) if a != b][:5])
    # даты
    def soob(pr):
        t = get('/centro/stats', pr).text
        m = re.search(r'<div class="period-oshibka"[^>]*>(.*?)</div>\s*<div style', t, re.S)
        return re.sub(r'<[^>]+>', ' ', m.group(1)).strip() if m else ''
    s1 = soob({'stat_ot': segodnya.isoformat(), 'stat_data': (segodnya - dt.timedelta(days=5)).isoformat()})
    s2 = soob({'stat_data': '2031-01-01'})
    s3 = soob({'stat_data': 'вчера'})
    s4 = soob({'stat_ot': '2031-02-30'})
    ok('переставлены' in s1, 'перевёрнутые даты: «%s»' % s1[:160])
    ok('не наступила' in s2, 'будущая дата: «%s»' % s2[:160])
    ok('не распознана' in s3, 'нераспознанная «по»: «%s»' % s3[:160])
    ok('не распознана' in s4, 'нераспознанная «с» (30 февраля): «%s»' % s4[:160])
    # суммы срезов и пояснения
    for sec in re.findall(r'<section>(.*?)</section>', t_vse, re.S):
        nz = re.search(r'<h3>([^<]*)', sec).group(1).strip()
        otm = [int(x) for x in re.findall(r'<tr><td>[^<]*</td><td>(?:<a [^>]*>)?(\d+)', sec)]
        poyasn = re.search(r'Сумма по строкам (\d+) при (\d+) компаниях', sec)
        p('   срез «%s»: строк %d, сумма %d%s' % (nz, len(otm), sum(otm), (', пояснение: %s/%s' % poyasn.groups()) if poyasn else ''))
    itog = re.search(r'<tr class="itog"><td>Все продавцы</td><td>(?:<a [^>]*>)?(\d+)', t_vse.split('Причины отказов по продавцам')[1]) if 'Причины отказов по продавцам' in t_vse else None
    ok(itog is not None, 'итог «Причины отказов»: отмечено %s' % (itog.group(1) if itog else '-'))
    ok(all(x in t_vse for x in ('нет потребности', 'не наш профиль', 'компания закрыта', 'не та компания / не ЛПР')), 'новые причины – колонками в «Причины отказов»')
    m = re.search(r'<b>(\d+)</b><span>личных номеров ЛПР получено</span>', t_vse)
    ok(m and m.group(1) == '2', 'плитка «личных номеров ЛПР получено» за всё время: %s (ожидается 2)' % (m.group(1) if m else '-'))
    m = re.search(r'<b>(\d+)</b><span>попыток «не дозвонился»</span>', t_vse)
    ok(m and m.group(1) == '3', 'плитка «попыток не дозвонился»: %s (ожидается 3)' % (m.group(1) if m else '-'))

# ===================================================================== 5. CSV = список
if 'csv' in FAZY:
    p('== CSV')
    kak('meyer_admin')
    nabory = [{}, {'assigned_user': 'meyer1'}, {'assigned_user': 'meyer4', 'sort': 'vyruchka'}, {'sort': 'region'},
              {'call_status': 'ne_ponravilas'}, {'prichina': 'нет потребности'}, {'segment': '4 элеваторы'},
              {'lpr_mobilnyy': '1'}, {'q': 'молоч'}, {'sort': 'seychas'}, {'pometka_och': 'est'},
              {'ot': (segodnya - dt.timedelta(days=6)).isoformat(), 'do': segodnya.isoformat(), 'sob': 'lpr_nomer'}]
    for pr in nabory:
        o = KL.get(PUT + '/centro/vygruzka.csv', params=pr)
        tekst = o.content.decode('utf-8-sig')
        rr = list(csv.reader(io.StringIO(tekst), delimiter=';'))
        zag, telo = (rr[0], rr[1:]) if rr else ([], [])
        ii = zag.index('ИНН') if 'ИНН' in zag else 2
        csv_inn = [x[ii] for x in telo]
        vs, n = spisok_inn(pr)
        ok(o.status_code == 200 and csv_inn == vs, 'CSV %s: строк %d, список %d, порядок %s' % (pr or 'всё', len(csv_inn), n, 'совпал' if csv_inn == vs else 'НЕ совпал'),
           pervye_raznye=[(i, a, b) for i, (a, b) in enumerate(zip(csv_inn, vs)) if a != b][:3])
    kak('meyer1'); ok(KL.get(PUT + '/centro/vygruzka.csv').status_code == 403, 'CSV продавцу: 403')

KL.__exit__(None, None, None)
POSLE = (schet(ZH_S), schet(ZH_K))
ok(DO == POSLE, 'боевые базы не тронуты: %s' % (POSLE,), do=DO)
plohih = sum(1 for x in OUT['proverki'] if not x['ok'])
p('ПЛОХИХ ПРОВЕРОК: %d из %d' % (plohih, len(OUT['proverki'])))
io.open(os.path.join(DROP, 'fixF1-prov2_test.json'), 'w', encoding='utf-8').write(json.dumps(OUT, ensure_ascii=False, default=str))
io.open(os.path.join(DROP, 'fixF1-prov2_test.txt'), 'w', encoding='utf-8').write('\n'.join(LOG))
import gc; gc.collect()
try: shutil.rmtree(TMP)
except Exception as e: p('копии не удалены (уберутся следующим прогоном)', e)
