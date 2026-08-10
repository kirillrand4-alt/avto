# -*- coding: utf-8 -*-
"""Кладёт починку карточки парка: маршрут + шаблон «в парке не показывается».

Что чиним: `/centro/park/<inn>` для предприятия, которого в базе парка нет, падал с 500
(шаблон получал p = None и спотыкался на `p.rang_mashiny`). Такое бывает у каждого
предприятия, уже показанного продавцам в обзвоне, — их 517, и владелец, перейдя по ИНН,
видел не ответ, а ошибку сервера.

Панель боевая, поэтому: копия перед заменой, затем ТРИ проверки живой страницы (карточка,
которая есть; карточка, которой нет; список парка) и откат при первой же неудаче.
"""
import http.cookiejar, io, json, os, re, shutil, sys, time
import urllib.error, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
B = 'http://127.0.0.1:8012/obzvon'
PARY = [(r'C:\sender\_ops\routes_park.py', r'C:\seostat\app\api\routes_park.py'),
        (r'C:\sender\_ops\park_net.html', r'C:\seostat\app\templates\park_net.html')]
o, kopii = {}, []
for ist, cel in PARY:
    if not os.path.exists(ist):
        o['ОШИБКА'] = 'нет исходника ' + ist
        print(json.dumps(o, ensure_ascii=False, indent=1))
        raise SystemExit(1)
    if os.path.exists(cel):
        bak = cel + '.bak-%d' % int(time.time())
        shutil.copyfile(cel, bak)
        kopii.append((bak, cel))
    shutil.copyfile(ist, cel)
    o[os.path.basename(cel)] = os.path.getsize(cel)

# маршрут — часть приложения, его нужно перечитать: перезапускаем службу
o['restart'] = os.popen('powershell -Command "Restart-Service obzvon -Force; \'ok\'"').read()[:60]
time.sleep(8)

PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def zapros(put):
    try:
        with op.open(B + put, timeout=90) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:  # noqa: BLE001
        return 0, str(e)[:120]


try:
    op.open(B + '/centro/login', timeout=30)
    op.open(urllib.request.Request(B + '/centro/login', data=urllib.parse.urlencode(
        {'username': 'user3', 'password': PW}).encode()), timeout=40)
    k1, t1 = zapros('/centro/park/6320004728')   # есть в парке
    k2, t2 = zapros('/centro/park/0268004714')   # убран, потому что виден в обзвоне
    k3, t3 = zapros('/centro/park')              # список парка
    o['карточка есть'] = {'http': k1, 'знаков': len(t1), 'фактов': t1.count('fact-card')}
    o['карточки нет'] = {'http': k2, 'знаков': len(t2),
                         'объяснение вместо ошибки': 'в парке не показывается' in t2,
                         'переход в обзвон': ('/centro?inn=0268004714' in t2)}
    o['список парка'] = {'http': k3, 'знаков': len(t3)}
    horosho = (k1 == 200 and t1.count('fact-card') > 0
               and k2 == 404 and 'в парке не показывается' in t2
               and k3 == 200)
except Exception as e:  # noqa: BLE001
    o['проверка сорвалась'] = str(e)[:150]
    horosho = False

if not horosho:
    for bak, cel in kopii:
        shutil.copyfile(bak, cel)
    os.popen('powershell -Command "Restart-Service obzvon -Force"').read()
    o['ОТКАТ'] = 'вернул прежние файлы и перезапустил службу'
o['итог'] = 'починка принята' if horosho else 'ОТКАЧЕНО'
print(json.dumps(o, ensure_ascii=False, indent=1))
