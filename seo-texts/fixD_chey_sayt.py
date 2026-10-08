# -*- coding: utf-8 -*-
"""fixD: «чей сайт» по всем компаниям панели Meyer (локальный разбор скачанных страниц).

Для каждой пары «компания – домен источника номера (и домен `sayt`)» собираются доказательства
по всем скачанным страницам домена (страница-источник, главная, «контакты/реквизиты/о компании»):
  свой      – ИНН или ОГРН компании на сайте; ФИО руководителя из checko; юрадрес из checko
              (индекс + улица); точное юрназвание + город юрадреса;
  группа    – на сайте ИНН/ОГРН/название управляющей организации или учредителя-юрлица из checko,
              или ИНН другой компании той же группы (общая УК/учредитель/руководитель по checko);
  чужой     – на сайте чужой ИНН/ОГРН (с подписью «ИНН»/«ОГРН»), своих признаков нет;
  не определено – ни того, ни другого (косвенные признаки записываются: город, название).
Ручные решения (проверено глазами, таблица РУЧНЫЕ) имеют приоритет и подписаны «проверено вручную».

    python3 fixD_chey_sayt.py <каталог.db> <папка-страниц> <svyazi.json> <checko-razbor.json> <выход.json>
"""
import gzip
import html as H
import json
import os
import re
import sqlite3
import sys

BAZA, PAPKA, SVYAZI, RAZBOR, VYHOD = sys.argv[1:6]
indeks = json.load(open(os.path.join(PAPKA, '_indeks.json'), encoding='utf-8'))
svyazi = json.load(open(SVYAZI, encoding='utf-8'))
razbor = json.load(open(RAZBOR, encoding='utf-8'))
NE_SAYTY = ('zakupki.gov.ru', 'tender.pro', 'b2b-center.ru', 'rts-tender.ru', 'sberbank-ast.ru', 'roseltorg.ru',
            'fabrikant.ru', 'etp-ets.ru', 'tektorg.ru', 'otc.ru', 'zakazrf.ru', 'etpgpb.ru', 'lot-online.ru',
            'onlinecontract.ru', 'bidzaar.com', 'tenderguru.ru', 'rostender.info', 'b2b-energo.ru',
            'gazneftetorg.ru', 'etprf.ru', 'zakupki.rosatom.ru', 'tenderplan.ru', 'zakupki.mos.ru', 'torgi.gov.ru',
            'checko.ru', 'inndex.ru', 'companies.rbc.ru', 'b2book.ru', 'b2b.house', 'companium.ru',
            'zachestnyibiznes.ru', 'star-pro.ru', 'ofcheck.ru', 'credinform', 'rusprofile', 'list-org.com',
            'sbis.ru', 'saby.ru', 'audit-it.ru', 'vk.com', 't.me', 'ok.ru', 'youtube.com', 'hh.ru')
BANKI = re.compile(r'БАНК|СБЕРБАНК|ВТБ|ГАЗПРОМБАНК|АЛЬФА-БАНК|РОССЕЛЬХОЗБАНК|ВНЕШНЕЭКОНОМИЧЕСК', re.I)
GOS = re.compile(r'РОССИЙСКАЯ ФЕДЕРАЦИЯ|АДМИНИСТРАЦ|МИНИСТЕРСТВ|КОМИТЕТ|ДЕПАРТАМЕНТ|МУНИЦИПАЛЬН|ФЕДЕРАЛЬН|'
                 r'ГОСУДАРСТВ|ИМУЩЕСТВ|ДОСТУП К СВЕДЕНИЯМ', re.I)
OBSHCHIE_SLOVA = set('''ооо оао зао пао ао ип общество ограниченной ответственностью акционерное открытое закрытое
компания группа торговый дом тд пк спк сппк спок кооператив производственный сельскохозяйственный
потребительский перерабатывающий сбытовой снабженческий фирма завод комбинат предприятие агро продукт
продукты молоко мясо хлеб сыр масло рыба мясокомбинат молокозавод хлебозавод маслозавод молочный мясной
хлебный рыбный пищевой пищевые старт империя мельница амур феникс фабрика производство центр ресурс маркет
плюс юг север восток запад русь россия русский сибирь урал мясоперерабатывающий племенной холдинг
агрокомплекс управляющая холдинговая агропромышленный инвест групп group компаний ''' .split())


def domen(u):
    u = (u or '').strip().lower()
    if '//' in u:
        u = u.split('//', 1)[1]
    d = u.split('/', 1)[0].split('?', 1)[0].split(':', 1)[0].strip('.')
    d = d[4:] if d.startswith('www.') else d
    if any(ord(c) > 127 for c in d):
        try:
            d = d.encode('idna').decode('ascii')
        except UnicodeError:
            pass
    return d if '.' in d else ''


def ne_sayt(d):
    return any(d == x or d.endswith('.' + x) or (x in d and '.' not in x) for x in NE_SAYTY)


def norm(s):
    return re.sub(r'\s+', ' ', (s or '').lower().replace('ё', 'е')).strip()


_kesh = {}


def tekst_stranicy(url):
    if url in _kesh:
        return _kesh[url]
    z = indeks.get(url) or {}
    t = ''
    if z.get('fajl') and z.get('kod') == 200:
        b = gzip.open(os.path.join(PAPKA, z['fajl'])).read()
        m = re.search(rb'charset=["\']?([\w-]+)', b[:4000])
        kod = (m.group(1).decode('ascii', 'ignore') if m else '') or 'utf-8'
        try:
            t = b.decode(kod, 'replace')
        except LookupError:
            t = b.decode('utf-8', 'replace')
        if t.count('�') > 50 and kod.lower() not in ('windows-1251', 'cp1251'):
            t2 = b.decode('cp1251', 'replace')
            if t2.count('�') < t.count('�'):
                t = t2
        t = re.sub(r'<script.*?</script>|<style.*?</style>|<!--.*?-->|<noscript.*?</noscript>', ' ', t, flags=re.S | re.I)
        t = H.unescape(re.sub(r'<[^>]+>', ' ', t))
        t = re.sub(r'[   ]', ' ', t)
        t = re.sub(r'\s+', ' ', t)
    _kesh[url] = t
    return t


def stranicy_domena(d):
    return [u for u, z in indeks.items() if domen(u) == d and z.get('kod') == 200]


def yadro_nazvaniya(naim):
    """Отличительная часть юрназвания: всё, что в кавычках, без ОПФ."""
    n = (naim or '').replace('«', '"').replace('»', '"').replace('“', '"').replace('”', '"')
    m = [x.strip() for x in n.split('"')[1:] if x.strip()]
    core = (' '.join(m) if m else re.sub(r'^(ООО|ОАО|ЗАО|ПАО|АО|ИП|СПК|СППК|СПССПК|СПСК|СППСК|СППЗСК)\s+', '', n)).strip(' "')
    return core


def otlichitelnye(core):
    return [w for w in re.findall(r'[а-яёa-z0-9-]{4,}', norm(core)) if w not in OBSHCHIE_SLOVA]


def gorod(adres):
    m = re.search(r'\b(?:г\.|город|пгт\.?|с\.|п\.|пос\.|ст-ца|рп\.?|д\.|х\.)\s*([А-ЯЁ][а-яёА-ЯЁ-]+(?:\s[А-ЯЁ][а-яё-]+)?)', adres or '')
    return m.group(1).strip('-') if m else ''


def ulica(adres):
    m = re.search(r'\b(?:ул\.|улица|пр-кт|проспект|пер\.|ш\.|шоссе|пр-д|проезд|б-р|наб\.|тер\.|мкр\.?|пл\.)\s*([А-ЯЁ0-9][А-Яа-яЁё0-9.-]+(?:\s[А-ЯЁ][а-яё-]+)?)', adres or '')
    return m.group(1).strip('.') if m else ''


def region_osnova(region):
    r = norm(region).replace('республика', '').replace('область', '').replace('край', '').replace('автономный округ', '')
    r = re.sub(r'\s+', ' ', r).strip(' -–')
    if not r:
        return ''
    w = max(r.split(), key=len)
    return w[:-2] if len(w) > 6 else w


INN_RE = re.compile(r'ИНН(?:\s*/\s*КПП)?\s*[:№.]?\s*(\d{10}|\d{12})(?!\d)', re.I)
OGRN_RE = re.compile(r'ОГРН(?:ИП)?\s*[:№.]?\s*(\d{13}|\d{15})(?!\d)', re.I)
UR_NAZV = re.compile(r'((?:ООО|ОАО|ЗАО|ПАО|АО|ИП|СПК|ТОО|Общество с ограниченной ответственностью|Акционерное общество)'
                     r'\s*[«"][^»"]{2,60}[»"])')


def gruppa_checko(inn):
    """Все ключи группы компании по checko: ОГРН/ИНН УК и учредителей-юрлиц (без банков и государства),
    ИНН руководителя-человека, ИНН учредителей-людей."""
    z = svyazi.get(inn) or {}
    ogrn, inn_org, naim = set(), set(), []
    for u in z.get('uk', []):
        ogrn.add(u['ogrn'])
        if u.get('inn'):
            inn_org.add(u['inn'])
        naim.append(u['naim'])
    if (z.get('ruk') or {}).get('vid') == 'company' and z['ruk'].get('inn'):
        inn_org.add(z['ruk']['inn'])
    for u in z.get('uchrediteli', []):
        if u['vid'] == 'org' and not BANKI.search(u['naim']) and not GOS.search(u['naim']):
            ogrn.add(u['id'])
            naim.append(u['naim'])
    return ogrn, inn_org, naim


def glavnoe():
    k = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
    k.row_factory = sqlite3.Row
    komp = {r['inn']: dict(r) for r in k.execute('select * from company')}
    kont = [dict(r) for r in k.execute('select id, inn, value, person, role, position, source, source_url, '
                                       'nomer_ne_lichnyy, fragment from contact')]
    # группа по checko между компаниями панели: общий ключ (УК/учредитель-юрлицо ОГРН, руководитель-человек ИНН,
    # учредитель-человек ИНН с долей от 20 %) или одна – учредитель/УК другой
    ogrn_inn = {z['ogrn']: i for i, z in svyazi.items() if z.get('ogrn')}
    kl = {}
    for i, z in svyazi.items():
        s = set()
        og, io_, _ = gruppa_checko(i)
        s |= {('o', x) for x in og} | {('o', ogrn_inn.get(x)) for x in og if ogrn_inn.get(x)}
        s |= {('io', x) for x in io_}
        if z.get('ogrn'):
            s.add(('o', z['ogrn']))
        s.add(('io', i))
        if (z.get('ruk') or {}).get('vid') == 'person' and z['ruk'].get('inn'):
            s.add(('fl', z['ruk']['inn']))
        for u in z.get('uchrediteli', []):
            if u['vid'] == 'fl':
                try:
                    dolya = float(u['dolya'].replace('%', '').replace(',', '.'))
                except ValueError:
                    dolya = 0
                if dolya >= 20:
                    s.add(('fl', u['id']))
        kl[i] = s
    # союз по общему ключу (кроме своего ИНН/ОГРН, которые есть только у себя, – они связывают дочку с материнской)
    rod = {i: i for i in kl}

    def koren(x):
        while rod[x] != x:
            rod[x] = rod[rod[x]]
            x = rod[x]
        return x
    po_klyuchu = {}
    for i, s in kl.items():
        for kk in s:
            po_klyuchu.setdefault(kk, set()).add(i)
    for kk, s in po_klyuchu.items():
        s = sorted(s)
        for j in s[1:]:
            rod[koren(j)] = koren(s[0])
    gruppa_po_checko = {}
    for i in kl:
        gruppa_po_checko.setdefault(koren(i), set()).add(i)
    chlen_gruppy = {i: g for g in gruppa_po_checko.values() if len(g) > 1 for i in g}

    itog = {}
    for inn, c in komp.items():
        r = razbor.get(inn) or {}
        ogrn = r.get('ogrn') or ''
        adres = c.get('adres') or r.get('adres') or ''
        ruk_fio = r.get('ruk_fio') if r.get('ruk_vid') == 'person' else ''
        core = yadro_nazvaniya(c.get('predpriyatie') or r.get('naim'))
        region = c.get('region') or ''
        slova = otlichitelnye(core)
        g_ogrn, g_inn, g_naim = gruppa_checko(inn)
        sosedi = chlen_gruppy.get(inn, set()) - {inn}
        sosedi_ogrn = {(razbor.get(x) or {}).get('ogrn') for x in sosedi} - {None, ''}
        domeny = {}
        for kt in kont:
            if kt['inn'] != inn:
                continue
            for u in (kt['source_url'] or '').replace(';', ' ').split():
                d = domen(u)
                if u.startswith('http') and d and not ne_sayt(d):
                    domeny.setdefault(d, {'urls': set(), 'kontakty': set()})
                    domeny[d]['urls'].add(u)
                    domeny[d]['kontakty'].add(kt['id'])
        sd = ''
        for s in re.split(r'[\s,;]+', c.get('sayt') or ''):
            if domen(s if '//' in s else 'http://' + s):
                sd = domen(s if '//' in s else 'http://' + s)
                break
        if sd and not ne_sayt(sd):
            domeny.setdefault(sd, {'urls': set(), 'kontakty': set()})
        rez = {}
        for d, info in domeny.items():
            urls = stranicy_domena(d)
            tekst = ' '.join(tekst_stranicy(u) for u in urls)
            nt = norm(tekst)
            dok_svoj, dok_myagk, dok_gr, dok_chuzh, kosv = [], [], [], [], []
            if re.search(r'(?<!\d)%s(?!\d)' % inn, tekst):
                dok_svoj.append('ИНН %s на сайте' % inn)
            if ogrn and re.search(r'(?<!\d)%s(?!\d)' % ogrn, tekst):
                dok_svoj.append('ОГРН %s на сайте' % ogrn)
            if ruk_fio:
                ch = ruk_fio.split()
                if len(ch) >= 2 and len(ch[0]) >= 4:
                    fam, im = norm(ch[0]), norm(ch[1])
                    otch = norm(ch[2]) if len(ch) > 2 else ''
                    pat = [r'\b%s\s+%s' % (re.escape(fam), re.escape(im)), r'\b%s\s+%s\.' % (re.escape(fam), re.escape(im[0])),
                           r'\b%s\s+%s' % (re.escape(im), re.escape(fam)),
                           r'\b%s\.\s*%s\.\s*%s\b' % (re.escape(im[0]), re.escape(otch[:1] or 'x'), re.escape(fam))]
                    if any(re.search(p, nt) for p in pat):
                        dok_myagk.append('руководитель по checko «%s» на сайте' % ruk_fio)
            m_ind = re.match(r'\s*(\d{6})', adres)
            ul = ulica(adres)
            if m_ind and m_ind.group(1) in tekst and ul and norm(ul) in nt:
                dok_myagk.append('юрадрес по checko (%s, %s) на сайте' % (m_ind.group(1), ul))
            gor = gorod(adres)
            nt2 = ' ' + re.sub(r'[^0-9a-zа-я]+', ' ', nt) + ' '
            fraza = ' ' + re.sub(r'[^0-9a-zа-я]+', ' ', norm(core)).strip() + ' '
            otl = [w for w in otlichitelnye(core) if len(w) >= 5]
            fraza_est = bool(otl) and fraza in nt2
            ur_tochno = bool(otl) and any(re.sub(r'[^0-9a-zа-я]+', ' ', norm(yadro_nazvaniya(u))).strip() == fraza.strip()
                                          for u in UR_NAZV.findall(tekst))
            gor_est = bool(gor) and (' ' + re.sub(r'[^0-9a-zа-я]+', ' ', norm(gor)).strip()) in nt2
            ro = region_osnova(region)
            reg_est = bool(ro) and ro in nt
            mesto = ('город %s' % gor) if gor_est else (('регион %s' % region) if reg_est else '')
            if (ur_tochno or fraza_est) and mesto:
                dok_myagk.append('%s «%s» и %s на сайте' % ('юрназвание' if ur_tochno else 'название', core, mesto))
            elif ur_tochno or fraza_est:
                kosv.append('%s «%s» на сайте (города/региона компании нет)' % ('юрназвание' if ur_tochno else 'название', core))
            elif mesto:
                kosv.append('%s на сайте' % mesto)
            chuzhie_inn = sorted(set(x for x in INN_RE.findall(tekst) if x != inn))
            chuzhie_ogrn = sorted(set(x for x in OGRN_RE.findall(tekst) if x != ogrn))
            for x in chuzhie_inn:
                if x in g_inn or any((razbor.get(s) or {}).get('inn_stranicy') == x or s == x for s in sosedi):
                    dok_gr.append('ИНН %s юрлица группы на сайте' % x)
            for x in chuzhie_ogrn:
                if x in g_ogrn or x in sosedi_ogrn:
                    dok_gr.append('ОГРН %s юрлица группы на сайте' % x)
            for nm in g_naim:
                yc = [w for w in otlichitelnye(yadro_nazvaniya(nm)) if len(w) >= 5]
                if yc and all(w in nt for w in yc):
                    dok_gr.append('название УК/учредителя «%s» на сайте' % yadro_nazvaniya(nm))
            chuzh_inn = [x for x in chuzhie_inn if x not in g_inn and x not in sosedi]
            chuzh_ogrn = [x for x in chuzhie_ogrn if x not in g_ogrn and x not in sosedi_ogrn]
            if chuzh_inn:
                dok_chuzh.append('на сайте чужой ИНН: %s' % ', '.join(chuzh_inn[:4]))
            if chuzh_ogrn:
                dok_chuzh.append('на сайте чужой ОГРН: %s' % ', '.join(chuzh_ogrn[:4]))
            ur = sorted(set(m.strip() for m in UR_NAZV.findall(tekst)))[:6]
            proverit = False
            krepk = [x for x in dok_myagk if x.startswith(('руководитель', 'юрадрес'))]
            if dok_svoj:
                verdikt = 'свой'
            elif krepk:
                verdikt = 'свой'
                proverit = bool(dok_chuzh)
            elif dok_gr:
                verdikt = 'группа'
            elif dok_chuzh:
                verdikt = 'чужой'
                proverit = bool(dok_myagk)
            elif dok_myagk:
                verdikt = 'свой'
            else:
                verdikt = 'не определено'
            rez[d] = {'verdikt': verdikt, 'proverit': proverit, 'svoj': dok_svoj + dok_myagk, 'svoj_tverd': bool(dok_svoj), 'gruppa': sorted(set(dok_gr)), 'chuzhoy': dok_chuzh,
                      'kosv': kosv, 'urnazv': ur, 'stranic': len(urls), 'urls': sorted(info['urls']),
                      'kontakty': sorted(info['kontakty']), 'eto_sayt': d == sd,
                      'tekst_dlina': len(tekst)}
        itog[inn] = {'nazvanie': c.get('predpriyatie'), 'bazy': c.get('bazy'), 'sayt': c.get('sayt'), 'sayt_domen': sd,
                     'sayt_chey': c.get('sayt_chey'), 'gruppa_checko': sorted(sosedi), 'domeny': rez,
                     'core': core, 'gorod': gorod(adres), 'region': c.get('region')}
    json.dump(itog, open(VYHOD, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    from collections import Counter
    sch = Counter(v['verdikt'] for x in itog.values() for v in x['domeny'].values())
    print('пар компания-домен: %d; %s' % (sum(sch.values()), dict(sch)))


if __name__ == '__main__':
    glavnoe()
