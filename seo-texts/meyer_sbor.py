# -*- coding: utf-8 -*-
"""База под Мейер ИЗ НАШЕЙ БАЗЫ, а не из справочника. Источник у каждой строки.

ЧТО ОТКУДА, и почему именно так:
  enrich.db / companies        169 790 компаний, метка division (meyer / kc), сайт,
                               activity, best_email, phones. Это наша база.
  enrich.db / phone_contacts   777 736 строк: телефон, person, role, source, source_url.
                               ЭТО ГЛАВНОЕ: у 98 % строк есть ссылка на источник.
                               В первом заходе я сюда не заглянула и получила одного
                               названного человека на 43 559 компаний.
  enrich.db / people           названные люди с должностями, немного, но самые ценные.
  obzvon-index.db              справочник реквизитов: ОКВЭД основной И дополнительные,
                               выручка, год отчётности, численность, директор по ЕГРЮЛ.
                               Берётся только для полей, которых в нашей базе нет.

ВИД КОНТАКТА называется прямо, а не прячется: личный с именем / роль ЛПР без имени /
директор по ЕГРЮЛ / приёмная и общий. Владелец просил не секретарей - значит надо видеть,
где секретарь, а не выбрасывать его молча.
"""
import csv, collections, io, os, re, sqlite3

DROP = r'C:\seostat\drop\drop-storage'
E = sqlite3.connect(r'C:\sender\enrich.db').cursor()
O = sqlite3.connect(r'C:\sender\obzvon-index.db').cursor()

SEGMENTY = [
    ('1 Экспортёры (кандидаты: опт зерна и продуктов)',
     ['46.21', '46.31', '46.32', '46.33', '46.36', '46.38', '46.17', '46.11.31']),
    ('2 Семеноводы', ['01.64', '01.11', '01.13.52', '01.25.2']),
    ('3 Пищевые предприятия', ['10.']),
    ('4 Элеваторы', ['52.10.3', '01.63', '10.61']),
    ('5 Орехи', ['10.39.2', '01.25.3']),
    ('6 Ягоды', ['01.25.1', '10.32', '10.39.2']),
]
LPR = [
    (1, 'техническая и качество', re.compile(
        r'главн\w*\s*инженер|технич\w*\s*директор|директор\s+по\s+производств|'
        r'главн\w*\s*технолог|главн\w*\s*механик|главн\w*\s*энергетик|'
        r'качеств|технолог|заведующ\w+\s+(?:элеватор|производств)|'
        r'начальник\s+производств|главн\w*\s*агроном|агроном|семеновод|лаборатор', re.I)),
    (2, 'закупки и снабжение', re.compile(r'закупк|снабжен|тендер|коммерческ', re.I)),
    (3, 'первое лицо', re.compile(r'директор|руководител|генеральн|собственник|учредител', re.I)),
    (4, 'производство и техника прочее', re.compile(r'инженер|механик|энергетик|мастер|'
                                                    r'начальник|производств|цех', re.I)),
    (5, 'приёмная, общий, продажи', re.compile(r'приёмн|приемн|общий|секрет|продаж|'
                                               r'диспетчер|номер предприятия|кадры|бухгалтер', re.I)),
]


def rang(s):
    for r, imya, rx in LPR:
        if rx.search(s or ''):
            return r, imya
    return 6, 'не определено'


# ---------- 1. сегменты по ОКВЭД из справочника (там он полный)
usl, par = [], []
for _, kody in SEGMENTY:
    for k in kody:
        usl.append('okved_main like ?')
        par.append(k + '%')
        usl.append('okved_all_codes like ?')
        par.append('%' + k + '%')
spravka = {}
for row in O.execute(
        'select inn, name_short, region, address, okved_main, okved_all_codes, revenue, '
        'revenue_rub, god_otch, ssch, director, sites, emails_base, phones_base, status, ogrn '
        'from obzvon where %s' % ' or '.join(usl), par):
    spravka[str(row[0]).strip()] = row
print('компаний по шести сегментам (справочник): %d' % len(spravka))

# ---------- 2. наша база
nasha = {}
for inn, name, div, okv, reg, site, act, best_email, phones in E.execute(
        'select inn, name, division, okved, region, site, activity, best_email, phones '
        'from companies'):
    i = str(inn or '').strip()
    if i in spravka:
        nasha[i] = {'name': name, 'division': div, 'okved': okv, 'region': reg,
                    'site': site, 'activity': act, 'best_email': best_email, 'phones': phones}
print('из них ЕСТЬ в нашей базе companies: %d' % len(nasha))

# ---------- 3. контакты со ссылками
kont = collections.defaultdict(list)
for inn, ph, person, role, src, url in E.execute(
        'select inn, phone, person, role, source, source_url from phone_contacts'):
    i = str(inn or '').strip()
    if i in spravka:
        r, gr = rang((role or '') + ' ' + (person or ''))
        kont[i].append({'phone': ph or '', 'person': (person or '').strip(),
                        'role': (role or '').strip(), 'source': src or '',
                        'url': url or '', 'rang': r, 'gruppa': gr})
for inn, post, role, ph, em, src, url in E.execute(
        'select inn, post, role, phone, email, source, source_url from people'):
    i = str(inn or '').strip()
    if i in spravka and (post or '').strip():
        r, gr = rang(post)
        kont[i].append({'phone': ph or '', 'person': (post or '').strip(),
                        'role': (role or '').strip(), 'source': src or 'people',
                        'url': url or '', 'rang': r, 'gruppa': gr, 'imennoy': True})
for i in kont:
    kont[i].sort(key=lambda x: (0 if x.get('person') else 1, x['rang']))
print('компаний с хоть одним контактом из нашей базы: %d (строк контактов %d)'
      % (len(kont), sum(len(v) for v in kont.values())))

EGRUL = 'https://egrul.nalog.ru/index.html#!/search?query='
SH = ['segmenty', 'nazvanie', 'inn', 'ogrn', 'status', 'region', 'adres', 'sayt',
      'okved_osnovnoy', 'okved_dopolnitelnye', 'opisanie_deyatelnosti', 'vyruchka',
      'vyruchka_rub', 'god_otchetnosti', 'sotrudnikov',
      'fio_kontakta', 'dolzhnost_ili_rol', 'vid_kontakta', 'rang_lpr',
      'pryamoy_telefon', 'rabochiy_telefon', 'email',
      'istochnik_kontakta', 'ssylka_na_istochnik_kontakta',
      'kontaktov_vsego', 'kontaktov_s_imenem', 'kontaktov_rang_1_2',
      'drugie_kontakty', 'razmetka_nashey_bazy', 'est_v_nashey_baze', 'ssylka_egryul']
stroki, vse_kont = [], []
for i, sp in spravka.items():
    (inn, name_s, region, address, okved_main, okved_all, revenue, revenue_rub,
     god, ssch, director, sites, emails_b, phones_b, status, ogrn) = sp
    n = nasha.get(i, {})
    om, oa = str(okved_main or ''), str(okved_all or '')
    segs = [imya for imya, kody in SEGMENTY
            if any(om.startswith(k) or k in oa for k in kody)]
    ks = kont.get(i, [])
    s_imenem = [x for x in ks if x['person']]
    lpr12 = [x for x in ks if x['rang'] <= 2]
    g = (s_imenem[0] if s_imenem else (lpr12[0] if lpr12 else (ks[0] if ks else None)))
    if g:
        fio = g['person']
        dolzh = g['role'] or g['gruppa']
        vid = ('личный контакт с именем' if g['person'] and g['rang'] <= 4
               else 'роль ЛПР без имени' if g['rang'] <= 2
               else 'первое лицо' if g['rang'] == 3
               else 'приёмная или общий номер' if g['rang'] == 5
               else 'номер без роли')
        ist, url = g['source'], g['url']
        pryam = g['phone'] if g['person'] else ''
        rab = g['phone'] if not g['person'] else ''
        rng = g['rang']
    else:
        fio, dolzh, ist, url, pryam, rab, rng = '', '', '', '', '', '', 9
        vid = 'контакта нет'
    if not rab:
        rab = (str(n.get('phones') or '').split('|')[0].strip()
               or str(phones_b or '').split('|')[0].strip())
    if not fio and str(director or '').strip():
        fio = str(director).strip()
        dolzh = 'руководитель по ЕГРЮЛ'
        vid = 'директор по ЕГРЮЛ (имя есть, прямого номера нет)'
        ist, url, rng = 'ЕГРЮЛ через справочник obzvon-index.db', EGRUL + i, 3
    pochta = (n.get('best_email') or '').strip() or str(emails_b or '').split('|')[0].strip()
    stroki.append({
        'segmenty': ' | '.join(segs), 'nazvanie': n.get('name') or name_s, 'inn': i,
        'ogrn': ogrn or '', 'status': status or '', 'region': n.get('region') or region or '',
        'adres': address or '', 'sayt': (n.get('site') or str(sites or '').split('|')[0]).strip(),
        'okved_osnovnoy': om, 'okved_dopolnitelnye': oa[:400],
        'opisanie_deyatelnosti': (n.get('activity') or re.sub(r'^\S+\s+', '', om))[:250],
        'vyruchka': revenue or '', 'vyruchka_rub': revenue_rub or '',
        'god_otchetnosti': god or '', 'sotrudnikov': ssch or '',
        'fio_kontakta': fio, 'dolzhnost_ili_rol': dolzh, 'vid_kontakta': vid, 'rang_lpr': rng,
        'pryamoy_telefon': pryam, 'rabochiy_telefon': rab, 'email': pochta,
        'istochnik_kontakta': ist, 'ssylka_na_istochnik_kontakta': url,
        'kontaktov_vsego': len(ks), 'kontaktov_s_imenem': len(s_imenem),
        'kontaktov_rang_1_2': len(lpr12),
        'drugie_kontakty': ' ;; '.join('%s %s [%s]' % (x['person'] or x['role'] or x['gruppa'],
                                                       x['phone'], x['source'][:18])
                                       for x in ks[1:4]),
        'razmetka_nashey_bazy': n.get('division') or '',
        'est_v_nashey_baze': 'да' if i in nasha else 'нет, только в справочнике',
        'ssylka_egryul': EGRUL + i,
    })
    for x in ks:
        vse_kont.append([i, n.get('name') or name_s, ' | '.join(segs), x['person'],
                         x['role'], x['gruppa'], x['rang'], x['phone'], x['source'], x['url']])

p1 = os.path.join(DROP, 'MEYER-BAZA-KOMPANII.csv')
with io.open(p1, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=SH, delimiter=';')
    w.writeheader()
    for s in stroki:
        w.writerow(s)
p2 = os.path.join(DROP, 'MEYER-BAZA-KONTAKTY.csv')
with io.open(p2, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f, delimiter=';')
    w.writerow(['inn', 'nazvanie', 'segmenty', 'fio', 'rol_kak_v_istochnike', 'gruppa_lpr',
                'rang', 'telefon', 'istochnik', 'ssylka_na_istochnik'])
    for r in vse_kont:
        w.writerow(r)

print('\n########## ЧИСЛА')
print('  компаний ........................ %d' % len(stroki))
for imya, _ in SEGMENTY:
    print('    %-48s %6d' % (imya, len([s for s in stroki if imya in s['segmenty']])))
print('  есть в НАШЕЙ базе companies ..... %d' % len([s for s in stroki if s['est_v_nashey_baze'] == 'да']))
print('  с меткой meyer .................. %d' % len([s for s in stroki if 'meyer' in (s['razmetka_nashey_bazy'] or '')]))
print('  действующих ..................... %d' % len([s for s in stroki if 'ействующ' in s['status']]))
print('  строк контактов со ссылкой ...... %d' % len([r for r in vse_kont if r[9]]))
print('\n  ПО ВИДУ КОНТАКТА (вот честная цена базы):')
for k, v in collections.Counter(s['vid_kontakta'] for s in stroki).most_common():
    print('    %-50s %6d' % (k, v))
print('\n  с сайтом %d · с выручкой %d · с почтой %d · с рабочим телефоном %d'
      % (len([s for s in stroki if s['sayt']]), len([s for s in stroki if s['vyruchka']]),
         len([s for s in stroki if s['email']]), len([s for s in stroki if s['rabochiy_telefon']])))
print('  КОНТРОЛЬ выдуманный ИНН 9999999999 в выборке: %d'
      % len([s for s in stroki if s['inn'] == '9999999999']))
print('  файлы: %s ; %s' % (p1, p2))
