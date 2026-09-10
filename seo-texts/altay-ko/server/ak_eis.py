# -*- coding: utf-8 -*-
"""Т2.3. ЕИС zakupki.gov.ru по Алтайскому краю (customerPlace=22000000000): закупка машин, ТО, запчасти, проверки.
Этап 1: лента по словам (44-ФЗ + 223-ФЗ), страницы по 50 -> eis-lenta.jsonl (резюм по (слово, страница)).
Этап 2: карточка каждой закупки -> ИНН заказчика (блок заказчика), «Требования заказчика», предмет -> eis-kartochki.jsonl (резюм по url).
Этап 3: влив в AK-BAZA.fakty (ссылка = карточка, цитата = предмет + кусок), предприятие -> predpriyatiya.
argv: [бюджет_сек] [TEST]. Печатает ГОТОВО, когда лента и карточки исчерпаны."""
import os, sys, re, json, time, html, sqlite3, requests
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
requests.packages.urllib3.disable_warnings()
AK = r'C:\sender\_ops\ak'; DB = os.path.join(AK, 'AK-BAZA.sqlite')
F_L = os.path.join(AK, 'eis-lenta.jsonl'); F_K = os.path.join(AK, 'eis-kartochki.jsonl')
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1400; TEST = 'TEST' in sys.argv
T0 = time.time(); TS = time.strftime('%Y-%m-%d %H:%M')
if 'RESET' in sys.argv:
    for fn in (F_L, F_K):
        if os.path.exists(fn): os.remove(fn)
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept-Language': 'ru,en;q=0.8'}
S = requests.Session(); S.headers.update(UA)
GRUPPY = {
 'закупка машины': ['компрессор', 'компрессорная установка', 'винтовой компрессор', 'поршневой компрессор', 'турбокомпрессор', 'нагнетатель воздуха', 'воздуходувка',
                    'компрессорная станция', 'воздухоразделительная установка', 'генератор азота', 'генератор кислорода', 'азотная станция', 'кислородная станция',
                    'осушитель сжатого воздуха', 'ресивер воздушный', 'воздухосборник', 'сжатого воздуха', 'компрессорной', 'холодильный компрессорный агрегат'],
 'закупка ТО': ['техническое обслуживание компрессор', 'ремонт компрессора', 'сервисное обслуживание компрессорного оборудования', 'ревизия компрессора',
                'капитальный ремонт компрессорной установки', 'обслуживание осушителя сжатого воздуха', 'ремонт воздуходувки', 'обслуживание компрессорной станции'],
 'закупка запчастей': ['запасные части компрессор', 'ремкомплект компрессора', 'клапан компрессора', 'масло компрессорное', 'фильтр компрессора', 'сепаратор компрессора',
                       'винтовой блок', 'воздушный фильтр компрессора', 'поршневые кольца компрессора', 'ротор компрессора'],
 'проверка': ['экспертиза промышленной безопасности компрессор', 'диагностирование компрессорной установки', 'освидетельствование воздухосборника', 'техническое освидетельствование ресивера'],
}
if TEST:
    GRUPPY = {'закупка машины': ['компрессор']}
SADOVAYA = re.compile(r'садов|бытов|ранцев|листь|пылесос|снегоубор|опрыскиват|бензинов\w*\s*воздуходув|аккумуляторн\w*\s*воздуходув|автомобильн\w*\s*компрессор|шин|кондиционер|холодильник\b|медицинск\w*\s*компрессор|ингалятор|аквариум', re.I)
VIDY = [('генератор кислорода', r'кислородн\w*\s*(станц|генератор|установ)|генератор\w*\s*кислород'), ('генератор азота', r'азотн\w*\s*(станц|генератор|установ)|генератор\w*\s*азот'),
        ('ВРУ', r'воздухоразделительн'), ('нагнетатель', r'нагнетател'), ('воздуходувка', r'воздуходув|турбовоздуходув'), ('осушитель', r'осушител'),
        ('ресивер', r'ресивер|воздухосборник'), ('МКС / передвижная', r'передвижн\w*\s*компрессорн|мобильн\w*\s*компрессорн|\bпкс\b|\bмкс\b'),
        ('запчасти', r'запасн\w+\s+част|ремкомплект|клапан|масло|фильтр|сепаратор|винтов\w+\s+блок|кольц|ротор'), ('компрессор', r'компрессор')]
VIDY = [(v, re.compile(r, re.I)) for v, r in VIDY]
BLOK = re.compile(r'(Наименование организации|Заказчик|Сведения о заказчике|Организация, осуществляющая размещение)(.{0,3000}?)ИНН\D{0,40}(\d{10,12})', re.S | re.I)
ZAKAZCHIK = re.compile(r'[Тт]ребовани\w+\s+заказчика\s*(?:«([^»]{5,220})»|"([^"]{5,220})")')
POSREDNIK = re.compile(r'агентств\w+ (государственн|муниципальн)|департамент\w* (государственн|муниципальн)|комитет\w* .{0,30}(закупк|заказ)|управлени\w* .{0,30}(закупк|заказ)|центр\w* .{0,20}(закупок|заказа)|уполномоченн\w+ орган|казначейств', re.I)
AVTO = re.compile(r'автомоб|автотранспорт|трактор|комбайн|двигател|дизел\w+ двигат|\bзил\b|камаз|\bгаз-|\bпаз\b|\bуаз\b|маз\b|шасси|тормозн|пневмоподвес|автобус|турбин\w* двс|кондиционер|сплит', re.I)
HOLOD = re.compile(r'холодильн|фреон|хладон|\br\d{2,3}a?\b|embraco|danfoss|шхс|морозильн|витрин|рефриж', re.I)
def get(url, tries=3):
    for i in range(tries):
        try:
            r = S.get(url, timeout=60, verify=False)
            if r.status_code == 200 and len(r.text) > 5000: return r.text
            time.sleep(3 + 4 * i)
        except Exception: time.sleep(3 + 4 * i)
    return ''
def vid(pred):
    for v, rx in VIDY:
        if rx.search(pred): return v
    return ''
# ---- этап 1
gotovo = set(); lenta = {}
if os.path.exists(F_L):
    for l in open(F_L, encoding='utf-8'):
        try: d = json.loads(l)
        except Exception: continue
        if not d.get('err'): gotovo.add((d['slovo'], d['stranica']))
        for z in d.get('zapisi', []): lenta.setdefault(z['url'], z)
f = open(F_L, 'a', encoding='utf-8')
konch = {}
n_new = 0
for st in range(1, 200):
    if time.time() - T0 > BUDGET: break
    aktivn = [(g, s) for g, ss in GRUPPY.items() for s in ss if not konch.get(s)]
    if not aktivn: break
    for gr, slovo in aktivn:
        if (slovo, st) in gotovo: continue
        if time.time() - T0 > BUDGET: break
        url = ('https://zakupki.gov.ru/epz/order/extendedsearch/results.html?searchString=' + requests.utils.quote(slovo) +
               '&morphology=on&fz44=on&fz223=on&customerPlace=22000000000&customerPlaceWithNested=on&recordsPerPage=_50&sortBy=UPDATE_DATE&pageNumber=' + str(st))
        h = get(url)
        if not h:
            f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': 'net', 'zapisi': []}, ensure_ascii=False) + '\n'); f.flush(); continue
        m = re.search(r'search-results__total[^>]*>\s*([\d\s]+)', h); total = int(re.sub(r'\D', '', m.group(1)) or 0) if m else -1
        zapisi = []
        for blk in re.findall(r'<div class="search-registry-entry-block[^"]*">(.*?)<div class="registry-entry__body-block">(.*?)(?=<div class="search-registry-entry-block|$)', h, re.S):
            pass
        # проще: режем по карточкам
        chunks = re.split(r'<div class="search-registry-entry-block', h)[1:]
        for ch in chunks:
            mu = re.search(r'href="((?:https://zakupki\.gov\.ru)?/(?:epz/order/notice/[a-z0-9]+/view/common-info\.html|223/purchase/public/purchase/info/common-info\.html)\?[^"]*regNumber=\d+[^"]*)"', ch)
            if not mu: continue
            u = mu.group(1); u = u if u.startswith('http') else 'https://zakupki.gov.ru' + u
            u = html.unescape(u)
            num = re.search(r'regNumber=(\d+)', u); num = num.group(1) if num else u
            pred = re.search(r'registry-entry__body-value">\s*([^<]{3,600})', ch); pred = html.unescape(pred.group(1)).strip() if pred else ''
            zak = re.search(r'registry-entry__body-href">\s*<a[^>]*>\s*([^<]{3,200})', ch); zak = html.unescape(zak.group(1)).strip() if zak else ''
            cena = re.search(r'price-block__value">\s*([^<]{1,40})', ch); cena = cena.group(1).strip() if cena else ''
            dat = re.search(r'Размещено[^<]*</div>\s*<div[^>]*>\s*(\d{2}\.\d{2}\.\d{4})', ch); dat = dat.group(1) if dat else (re.search(r'(\d{2}\.\d{2}\.\d{4})', ch) or [None, ''])[1]
            fz = '223' if '/223/' in u else '44'
            zapisi.append({'url': u, 'nomer': num, 'predmet': pred[:600], 'zakazchik_lenty': zak, 'cena': cena, 'data': dat, 'fz': fz, 'slovo': slovo, 'gruppa': gr})
        f.write(json.dumps({'slovo': slovo, 'stranica': st, 'err': '', 'total': total, 'zapisi': zapisi}, ensure_ascii=False) + '\n'); f.flush()
        gotovo.add((slovo, st))
        for z in zapisi:
            if z['url'] not in lenta: lenta[z['url']] = z; n_new += 1
        if not zapisi or (total >= 0 and st * 50 >= total): konch[slovo] = True
        time.sleep(0.7)
        if TEST: konch[slovo] = True
f.close()
lenta_polna = all(konch.get(s) for ss in GRUPPY.values() for s in ss) or any(True for _ in [0]) and not [1 for ss in GRUPPY.values() for s in ss if not konch.get(s) and (s, 1) not in gotovo]
print(f'этап 1: страниц готово {len(gotovo)}, закупок в ленте {len(lenta)} (новых {n_new}), слов кончилось {sum(1 for v in konch.values() if v)}', flush=True)
# ---- этап 2
F_O = os.path.join(AK, 'eis-org.jsonl')
orgs = {}
if os.path.exists(F_O):
    for l in open(F_O, encoding='utf-8'):
        try: d = json.loads(l); orgs[d['code']] = d
        except Exception: pass
fo = open(F_O, 'a', encoding='utf-8')
def org_info(code, fz):
    """ИНН/имя/адрес организации ЕИС по коду; кэш в eis-org.jsonl."""
    if code in orgs: return orgs[code]
    u = ('https://zakupki.gov.ru/epz/organization/view/info.html?organizationCode=' + code) if fz == '44' else ('https://zakupki.gov.ru/223/ppa/public/organization/view/info.html?agencyId=' + code)
    h = get(u); d = {'code': code, 'inn': '', 'imya': '', 'adres': '', 'url': u}
    if h:
        t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', h)))
        m = re.search(r'ИНН\s*\|[\s|]*(\d{10,12})', t); d['inn'] = m.group(1) if m else ''
        m = re.search(r'(?:Полное наименование|Наименование организации|Полное наименование организации)\s*\|[\s|]*([^|]{5,250})', t); d['imya'] = m.group(1).strip() if m else ''
        m = re.search(r'(?:Место нахождения|Адрес места нахождения|Почтовый адрес)\s*\|[\s|]*([^|]{5,250})', t); d['adres'] = m.group(1).strip() if m else ''
    orgs[code] = d; fo.write(json.dumps(d, ensure_ascii=False) + '\n'); fo.flush()
    time.sleep(0.5)
    return d
MASH = re.compile('|'.join(r for _, r in [(v, rx.pattern) for v, rx in VIDY]), re.I)
kart = {}
if os.path.exists(F_K):
    for l in open(F_K, encoding='utf-8'):
        try: d = json.loads(l); kart[d['url']] = d
        except Exception: pass
fk = open(F_K, 'a', encoding='utf-8'); n_k = 0; n_err = 0
ochered = [u for u in lenta if u not in kart]
if TEST: ochered = ochered[:10]
for u in ochered:
    if time.time() - T0 > BUDGET: break
    h = get(u)
    if not h:
        n_err += 1; continue
    z = lenta[u]
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' | ', h)))
    obj = re.search(r'Наименование объекта закупки\s*\|[\s|]*([^|]{5,400})', t) or re.search(r'Объект закупки\s*\|[\s|]*([^|]{5,400})', t) or re.search(r'Предмет договора\s*\|[\s|]*([^|]{5,400})', t)
    obj = obj.group(1).strip() if obj else ''
    pozicii = [(k, n.strip()) for k, n in re.findall(r'(\d{2}\.\d{2}\.\d{2}(?:\.\d{3})?)\s*\|[\s|]*([^|]{5,250})', t)]
    poz_mash = [f'{k} {n}' for k, n in pozicii if MASH.search(n) and not SADOVAYA.search(n)][:6]
    trebov = ZAKAZCHIK.search(t); trebov = (trebov.group(1) or trebov.group(2) or '').strip() if trebov else ''
    codes = []
    for cd in re.findall(r'organizationCode=(\d+)', h) + re.findall(r'agencyId=(\d+)', h):
        if cd not in codes: codes.append(cd)
    orgi = [org_info(cd, z['fz']) for cd in codes[:4]]
    m = BLOK.search(t); inn_blok = m.group(3) if m else ''
    # заказчик: первая организация, не похожая на посредника; иначе организатор с пометкой
    zak = None
    for o in orgi:
        if o['inn'] and not POSREDNIK.search(o['imya'] or ''):
            zak = o; break
    posr = False
    if zak is None and orgi:
        zak = orgi[0]; posr = True
    inn = (zak or {}).get('inn') or inn_blok
    imya = (zak or {}).get('imya') or z['zakazchik_lenty']
    d = {'url': u, 'inn': inn, 'zakazchik': imya, 'adres': (zak or {}).get('adres', ''), 'organizator': (orgi[0]['imya'] if orgi else z['zakazchik_lenty']), 'posrednik': posr or bool(POSREDNIK.search(imya or '')),
         'trebovaniya_zakazchika': trebov, 'obekt': obj, 'pozicii_mashina': poz_mash, 'org_codes': codes[:4], 'ts': TS}
    fk.write(json.dumps(d, ensure_ascii=False) + '\n'); fk.flush(); kart[u] = d; n_k += 1
    time.sleep(0.8)
fk.close(); fo.close()
# ---- этап 2б: посредник -> настоящий заказчик через DaData по имени (кэш)
F_D = os.path.join(AK, 'eis-dadata.jsonl'); dd = {}
if os.path.exists(F_D):
    for l in open(F_D, encoding='utf-8'):
        try: d = json.loads(l); dd[d['imya']] = d
        except Exception: pass
DTOK = os.environ.get('DADATA_TOKEN', '')
def dadata_imya(imya):
    if imya in dd: return dd[imya]
    d = {'imya': imya, 'inn': '', 'nazvanie': '', 'adres': ''}
    if DTOK:
        try:
            r = requests.post('https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party', json={'query': imya, 'count': 3, 'locations': [{'kladr_id': '2200000000000'}]},
                              headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'Authorization': 'Token ' + DTOK}, timeout=30)
            for sug in (r.json().get('suggestions') or []):
                dat = sug.get('data') or {}
                if str(dat.get('inn', '')).startswith('22'):
                    d.update({'inn': dat.get('inn'), 'nazvanie': sug.get('value'), 'adres': ((dat.get('address') or {}).get('value') or '')}); break
        except Exception as e:
            d['err'] = repr(e)[:80]
    dd[imya] = d
    with open(F_D, 'a', encoding='utf-8') as f: f.write(json.dumps(d, ensure_ascii=False) + '\n')
    return d
n_dd = 0
for u, d in kart.items():
    if d.get('posrednik') and d.get('trebovaniya_zakazchika') and not d.get('inn_zakazchika'):
        r = dadata_imya(d['trebovaniya_zakazchika'])
        if r.get('inn'): d['inn_zakazchika'] = r['inn']; d['zakazchik_dadata'] = r['nazvanie']; n_dd += 1
print(f'этап 2б: заказчиков через DaData {n_dd}, кэш имён {len(dd)}', flush=True)
print(f'этап 2: карточек за заход {n_k}, ошибок {n_err}, всего карточек {len(kart)}, организаций в кэше {len(orgs)}, в очереди {len([u for u in lenta if u not in kart])}', flush=True)
# ---- этап 3
c = sqlite3.connect(DB, timeout=120)
n_f = n_p = 0
have = {r[0] for r in c.execute('select inn from predpriyatiya')}
for u, d in kart.items():
    z = lenta.get(u)
    if not z: continue
    inn = d.get('inn_zakazchika') or (d.get('inn') if not d.get('posrednik') else '')
    if not inn: continue
    if not d.get('inn_zakazchika') and d.get('posrednik'): continue
    if not inn.startswith('22'): continue   # контроль региона: только край
    pred = z['predmet'] or d.get('obekt') or ''
    poz = d.get('pozicii_mashina') or []
    tip = ('' if SADOVAYA.search(pred) else vid(pred)) or ('' if SADOVAYA.search(d.get('obekt') or '') else vid(d.get('obekt') or '')) or (vid(poz[0]) if poz else '')
    if not tip: continue
    kontekst = pred + ' ' + (d.get('obekt') or '') + ' ' + ' '.join(poz[:2])
    if AVTO.search(kontekst) and not re.search(r'компрессорн\w+ (станц|установк)|винтов|поршнев\w+ компрессор', kontekst, re.I): continue
    sila_dop = 0
    if HOLOD.search(kontekst) and not re.search(r'сжат\w+ воздух|пневм|винтов', kontekst, re.I):
        tip = 'холодильный компрессор'; sila_dop = -2
    if inn not in have:
        c.execute('insert or ignore into predpriyatiya(inn, nazvanie, adres, istochniki_zapisi, ts) values(?,?,?,?,?)', (inn, d.get('zakazchik_dadata') or d.get('zakazchik') or z['zakazchik_lenty'], d.get('adres', ''), 'eis', TS)); have.add(inn); n_p += 1
    cit = (pred[:250] + (' | позиция: ' + '; '.join(poz[:2]) if poz else '') + (' | Требования заказчика: ' + d['trebovaniya_zakazchika'] if d.get('trebovaniya_zakazchika') else '') + (' | ' + z['cena'] if z.get('cena') else ''))[:600]
    kl = f'{inn}|{u}|{tip}||{cit[:80]}'
    c.execute('''insert or ignore into fakty(inn,predpriyatie,vid_fakta,tip,marka_model,sreda,data,srok_do,status_sroka,sila,istochnik,ssylka,citata,kto_sobral,ts,klyuch)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (inn, d.get('zakazchik_dadata') or d.get('zakazchik') or z['zakazchik_lenty'], z['gruppa'], tip, '', '', z.get('data'), '', '', (4 if z['gruppa'] == 'закупка машины' else 5) + sila_dop, 'zakupki.gov.ru', u, cit, 'ak_eis', TS, kl))
    n_f += c.total_changes and 1
c.commit()
p_inn = c.execute("select count(distinct inn) from fakty where istochnik='zakupki.gov.ru'").fetchone()[0]
n_all = c.execute("select count(*) from fakty where kto_sobral='ak_eis'").fetchone()[0]
print(f'этап 3: фактов ЕИС всего {n_all}, ИНН с фактом ЕИС {p_inn}, новых предприятий {n_p}', flush=True)
c.close()
if lenta_polna and not [u for u in lenta if u not in kart]:
    print('ГОТОВО')
