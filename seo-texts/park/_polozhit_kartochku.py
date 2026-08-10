# Кладёт park_card.html в панель с копией и проверкой: карточка должна открыться и показать
# факты. Панель боевая, поэтому при неудаче возвращаем прежний шаблон.
import http.cookiejar, json, os, re, shutil, time, urllib.parse, urllib.request
IST = r'C:\sender\_ops\park_card.html'
CEL = r'C:\seostat\app\templates\park_card.html'
B = 'http://127.0.0.1:8012/obzvon'
o = {}
bak = CEL + '.bak-%d' % int(time.time())
shutil.copyfile(CEL, bak); shutil.copyfile(IST, CEL)
o['kopiya'] = os.path.basename(bak); o['polozheno'] = os.path.getsize(CEL)
PW = ''
if os.path.exists(r'C:\sender\centro-user3.txt'):
    t = open(r'C:\sender\centro-user3.txt', encoding='utf-8', errors='replace').read()
    m = re.search(r'(?:пароль|password)\s*[:=]\s*(\S+)', t, re.I)
    PW = m.group(1) if m else t.strip().split()[-1]
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:
    op.open(B + '/centro/login', timeout=30)
    op.open(urllib.request.Request(B + '/centro/login', data=urllib.parse.urlencode(
        {'username': 'user3', 'password': PW}).encode()), timeout=40)
    with op.open(B + '/centro/park/0105018196', timeout=90) as r:
        s = r.read().decode('utf-8', 'replace')
    o['karta'] = {'http': r.status, 'знаков': len(s), 'фактов': s.count('fact-card'),
                  'ИНН проверки': '0105018196',
                  'метка общей почты в разметке': 'почта организации, не личная' in s}
    horosho = r.status == 200 and s.count('fact-card') > 0
except Exception as e:  # noqa: BLE001
    o['oshibka'] = str(e)[:150]; horosho = False
if not horosho:
    shutil.copyfile(bak, CEL); o['ОТКАТ'] = 'вернул прежний шаблон'
o['итог'] = 'принято' if horosho else 'ОТКАЧЕНО'
print(json.dumps(o, ensure_ascii=False))
