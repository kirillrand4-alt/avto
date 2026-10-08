# -*- coding: utf-8 -*-
"""После добавления 39 крупных: чистка и снимки холдингов.
1. Повторный прогон заливки вернул в каталог старый блок «неличные – вниз» внутри цикла
   (его признак сменился, когда правило переехало за цикл). На результат не влиял – правило
   после цикла всё равно решает последним, – но двух правил в коде быть не должно.
2. Подпись «ЛПР не найден…» у ранее залитых без ЛПР: «через коммутатор» только если лучший
   номер – приёмная или общий; иначе «номер с сайта» (как у добавленных).
3. Счётчики Базы 6 в import_info – итоговые, а не последней порции.
4. Карточки двух холдингов – на дроп для снимка."""
import io, json, os, re, shutil, sqlite3, subprocess, sys, time
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
CAT = os.path.join(KOREN, 'app', 'services', 'centro_catalog.py')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
JSON_PUT = r'C:\seostat\drop\drop-storage\meyer-baza6.json'
DROP = r'C:\seostat\drop\drop-storage'
PORT = 8016
PUT = '/obzvon-meyer'
if '--snimki' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa
    import logging, warnings
    warnings.filterwarnings('ignore'); logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.services import centro_catalog as cat
    from app.obzvon import create_app
    from fastapi.testclient import TestClient
    vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    with TestClient(vnutr) as k:
        for inn in ('1832104677', '7224031400'):
            o = k.get(PUT + '/centro?inn=' + inn)
            io.open(os.path.join(DROP, 'centro2-holding-%s.html' % inn), 'w', encoding='utf-8').write(o.text)
            print('карточка %s: %s, блок холдинга %s' % (inn, o.status_code, 'kholding-section' in o.text))
    # правило «верх» работает: у компании без ЛПР и без приёмной номера наверху
    kont = cat.contacts('1323010142')
    print('без ЛПР и приёмной (1323010142): наверху %d из %d' % (sum(1 for x in kont if x['has_role']), len(kont)))
    raise SystemExit(0)

B = os.path.join(KOREN, '_bekap', time.strftime('baza6-chistka-%Y%m%d-%H%M%S'))
os.makedirs(B, exist_ok=True)
t = io.open(CAT, encoding='utf-8').read()
lishniy = '''        # неличный номер (продажи, бухгалтерия, общий…) – в «остальные», но с видом
        if str(item.get("nomer_ne_lichnyy") or "").strip():
            item["has_role"] = 0
        result.append(item)'''
if t.count(lishniy) == 1 and 'est_verh = any(' in t:
    shutil.copy2(CAT, os.path.join(B, 'centro_catalog.py'))
    io.open(CAT, 'w', encoding='utf-8').write(t.replace(lishniy, '        result.append(item)', 1))
    print('[ок] каталог: лишний блок убран, правило одно – после цикла')
else:
    print('[—] лишнего блока нет (%d), правило после цикла: %s' % (t.count(lishniy), 'est_verh = any(' in t))
d = json.load(io.open(JSON_PUT, encoding='utf-8'))
k = sqlite3.connect(KAT)
dst = sqlite3.connect(os.path.join(B, 'meyer_baza1.db'))
k.backup(dst)
dst.close()
n = 0
for c in d['kompanii']:
    if c['lpr_kratko'].startswith('ЛПР не найден'):
        r = k.execute("update company set lpr_kratko=? where inn=? and bazy='База 6' and lpr_kratko<>?",
                      (c['lpr_kratko'], c['inn'], c['lpr_kratko']))
        n += r.rowcount
vsego6 = k.execute("select count(*) from company where bazy like '%База 6%'").fetchone()[0]
for kk, v in {'baza6_kompaniy_vsego': str(vsego6), 'baza6_kompaniy_novyh': str(vsego6 - 3),
              'baza6_sliyanie': '3', 'baza6_kontaktov': str(k.execute(
                  "select count(*) from contact where inn in (select inn from company where bazy like '%База 6%')").fetchone()[0]),
              'baza6_dobavleno': '39 крупных без ЛПР, с мобильными (владелец: «добавь»)'}.items():
    k.execute('INSERT OR REPLACE INTO import_info (key, value) VALUES (?,?)', (kk, v))
k.commit()
print('[ок] подпись «ЛПР не найден…» обновлена у %d компаний; Базы 6 всего %d' % (n, vsego6))
sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: чистка после добавления 39 %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg, stderr=subprocess.STDOUT,
                 creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
time.sleep(10)
import urllib.request
try:
    print('вход: %s' % urllib.request.urlopen('http://127.0.0.1:%d%s/centro/login' % (PORT, PUT), timeout=30).status)
except Exception as e:  # noqa
    print('вход: %s' % e)
r = subprocess.run([VENV, os.path.abspath(__file__), '--snimki'], capture_output=True, timeout=600, cwd=KOREN, env=sreda)
print(r.stdout.decode('utf-8', 'replace')[-1500:])
if r.returncode:
    print(r.stderr.decode('utf-8', 'replace')[-2000:])
