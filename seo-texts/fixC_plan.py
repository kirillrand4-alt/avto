# -*- coding: utf-8 -*-
"""fixC: план правок контактов каталога Meyer по разбору страниц (локально, без записи).

    python3 fixC_plan.py <каталог.db> <папка страниц> <podpisi.json> <plan.json>

План применяет fixC_kontakty.py на сервере (сверяя id + ИНН + номер). Здесь — только
решения: какие подписи восстановить, какой вид номера поставить, какие номера добавить
(видимый номер вместо битой ссылки tel:, люди на общем номере с разными добавочными,
пропущенные номера формата «(341-41)»), какие ЛПР без телефона показать как «спросить
у приёмной». Правила — в комментариях у каждого шага.
"""
import collections
import json
import os
import re
import sqlite3
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixC_podpisi as P  # noqa: E402
import fixC_razbor as R  # noqa: E402

PUSTYE_DOLZH = {'', 'мобильный с сайта, без подписи'}
# короткие «канонические» подписи витрины ЛПР – ставились по ключевому слову; подпись со
# страницы (если опознана и вид другой) точнее
KANON = {'нач.производства', 'гл.инженер', 'гл.технолог', 'снабжение/закупки', 'техдиректор',
         'гл.механик', 'гл.энергетик'}
# мусор рядом с цифрами: артикулы, ТУ, реквизиты
_MUSOR_PERED = re.compile(r'(?i)(?:mcode|артикул|арт\.|код товара|\bту\b[\s\d.\-]*|гост|огрн|инн|кпп|окпо|'
                          r'бик|р/с|к/с|счет|сч\.)[\s:№#-]{0,4}$')
_SHABLON_TEKST = re.compile(r'(?i)строительн\w* компани|ваша компания|название компании|lorem|пример номера')
CHUZHAYA_ORG = re.compile(r'(?:\b(?:ООО|АО|ЗАО|ОАО|ПАО|ИП|СПК|ТД|ПХ|ГК|КФХ)\b|[«"].+[»"]|завода|комбината|филиала|кафе|ресторан|магазин|блог|действующ\w* на основании)', re.I)
STRANICA_VAKANSIY = re.compile(r'(?i)vakans|vacanc|karer|career|/job|rabota|trudoustr|personal|/hr\b|kadr')


def shablonnyy(d10):
    """Номер вёрстки: две цифры на все десять (989 989-89-89, 900 000-00-00, 123 456-78-90).
    «Красивые» настоящие номера (800 000-00-00 с повторами, «красивые» городские) сюда не попадают."""
    return len(set(d10)) <= 2 or d10 in ('1234567890', '9001234567', '9876543210')


def menyu(podp):
    """Подпись из трёх коротких строк без ФИО – это пункты меню сайта, а не подпись номера."""
    L = [x for x in (podp or '').split('\n') if x.strip()]
    return len(L) >= 3 and all(len(x.split()) <= 4 and not re.search(r'\d|:', x) for x in L)


def domen(u):
    try:
        return (urlsplit(u).hostname or '').lower().replace('www.', '')
    except ValueError:
        return ''


def okrest_fragmenta(fr, k10):
    """Текст фрагмента каталога перед номером (для выбора нужного вхождения на странице)."""
    if not fr:
        return ''
    st = P.fragment_kak_tekst(fr)
    for x in st['vh']:
        if x['k10'] == k10 and not x['tel']:
            return re.sub(r'\s+', ' ', R._TEL.sub(' ', st['t'][max(0, x['nach'] - 80):x['nach']])).strip()[-45:]
    return ''


def vybrat(variants, fr_hvost, dob_db='', vid_kontakta=''):
    """Лучшее вхождение номера на странице. У номера с добавочным – вхождение с тем же
    добавочным (на общем номере у каждого человека свой). Затем – совпавшее с фрагментом
    каталога (из него номер и был взят), если совпадение однозначное. У номера без
    добавочного – вхождения без добавочного. Иначе – самое полное."""
    if not variants:
        return None
    if dob_db and any(v['dob'] == dob_db for v in variants):
        variants = [v for v in variants if v['dob'] == dob_db]
    if fr_hvost and len(fr_hvost) >= 20:
        sovp = [v for v in variants if fr_hvost[-30:] in re.sub(r'\s+', ' ', R._TEL.sub(' ', v['okrest']))]
        if len(sovp) == 1:
            return sovp[0]
    # у подписанного номера – вхождение с той же ролью («техдиректор» ↔ «ТЕХНИЧЕСКИЙ ДИРЕКТОР доб. 208»)
    if vid_kontakta and vid_kontakta not in ('без подписи', 'другая должность'):
        same = [v for v in variants if v['dolzh'] and P.vid_po_tekstu(v['dolzh']) == vid_kontakta]
        if len(same) == 1:
            return same[0]
    if not dob_db and any(not v['dob'] for v in variants):
        variants = [v for v in variants if not v['dob']]

    def sc(v):
        vid = P.vid_po_tekstu(v['dolzh']) if v['dolzh'] else ''
        return 2 * bool(v['fio']) + 2 * bool(vid) + (1 if v['kak'] == 'pered' else 0)
    best = max(variants, key=sc)
    return best if (best['fio'] or best['dolzh']) else variants[0]


def main():
    db, papka, podp_json, vyhod = sys.argv[1:5]
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    komp = {r['inn']: dict(r) for r in c.execute('select * from company')}
    kont = {r['id']: dict(r) for r in c.execute('select * from contact')}
    lyudi = [dict(r) for r in c.execute('select * from person')]
    podp = {r['id']: r for r in json.load(open(podp_json, encoding='utf-8'))}
    tekst = P.zagruzit_stranicy(papka)
    meta = json.load(open(os.path.join(papka, 'meta.json'), encoding='utf-8'))

    est_u = collections.defaultdict(set)          # ИНН -> {(10 цифр, доб.)}
    for k in kont.values():
        k10, dob = P.k10_iz_value(k['value'])
        est_u[k['inn']].add((k10, dob))
        est_u[k['inn']].add((k10, '*'))

    obnov, novye, zhurnal = [], [], collections.Counter()

    def novyy(inn, value, person, dolzh, fr, url, pochemu, ishod=None):
        k10, dob = P.k10_iz_value(value)
        if (k10, dob) in est_u[inn]:
            return
        est_u[inn].add((k10, dob))
        novye.append({'inn': inn, 'value': value, 'person': person or None, 'position': dolzh or '',
                      'fragment': (fr or '')[:400], 'source_url': url,
                      'source': 'страница сайта · разбор подписей 08.10 (fixC): ' + pochemu,
                      'ishod_id': ishod})
        zhurnal['новый: ' + pochemu.split(':')[0]] += 1

    for kid, k in sorted(kont.items()):
        if k['kind'] != 'phone':
            continue
        r = podp.get(kid) or {}
        k10, dob_db = P.k10_iz_value(k['value'])
        polya, pochemu = {}, []
        url0 = ([u for u in (k['source_url'] or '').replace(';', ' ').split() if u.startswith('http')] or [''])[0]
        variants = r.get('varianty') or []
        v = vybrat(variants, okrest_fragmenta(k['fragment'], k10), dob_db, P.rol_kontakta(k)['vid'])

        # --- 1. подпись: ФИО и должность со страницы, только в пустые поля
        if v and not v['fio'] and menyu(v['podp']):
            v = dict(v, dolzh='')          # «Партнеры / Лицензии / Закупки» – пункты меню, не подпись
        if v:
            if v['fio'] and not (k['person'] or '').strip():
                polya['person'] = v['fio']
                pochemu.append('ФИО со страницы')
            dolzh_tek = (k['position'] or '').strip()
            if v['dolzh'] and (dolzh_tek in PUSTYE_DOLZH or (
                    dolzh_tek.lower() in KANON and P.vid_po_tekstu(v['dolzh'])
                    and P.vid_po_tekstu(v['dolzh']) != P.rol_kontakta({'position': dolzh_tek, 'role': k['role']})['vid'])):
                polya['position'] = v['dolzh'][:120]
                pochemu.append('должность со страницы' + (' (была «%s»)' % dolzh_tek if dolzh_tek else ''))
            elif dolzh_tek == 'мобильный с сайта, без подписи':
                polya['position'] = ''
                pochemu.append('«мобильный с сайта, без подписи» – не должность')
            # --- 6. потерянный добавочный: у городского номера на странице есть «доб.»
            if v['dob'] and not dob_db and not k10.startswith('9') and not k10.startswith('800'):
                polya['value'] = k['value'].strip() + ' доб. ' + v['dob']
                pochemu.append('добавочный со страницы')
                est_u[k['inn']].add((k10, v['dob']))
        elif (k['position'] or '').strip() == 'мобильный с сайта, без подписи':
            polya['position'] = ''
            pochemu.append('«мобильный с сайта, без подписи» – не должность')

        # --- 5. вид номера и мусор
        vid = P.vid_nomera_po_cifram(polya.get('value', k['value']))
        vid_poch = ''
        okr = ' '.join(x['okrest'] for x in variants) if variants else (k['fragment'] or '')
        d10 = k10 or ''
        if r.get('tolko_v_kommentarii'):
            vid, vid_poch = 'не номер компании', 'номер есть только в закомментированном (скрытом) HTML страницы, на странице его не видно'
        elif d10 and shablonnyy(d10):
            vid, vid_poch = 'не номер компании', 'шаблонный номер вёрстки сайта'
        elif d10 and okr and any(_MUSOR_PERED.search(okr[:m.start()][-25:]) for kus in (d10, d10[-7:])
                                 for m in re.finditer(r'[\s\-().]*'.join(kus), okr)):
            vid, vid_poch = 'не номер компании', 'не телефон: цифры артикула, ТУ или реквизита'
        elif v and _SHABLON_TEKST.search(v['podp'] or ''):
            vid, vid_poch = 'не номер компании', 'номер из шаблона сайта («%s»)' % _SHABLON_TEKST.search(v['podp']).group(0)
        elif r.get('tolko_tel') and r.get('vidimyy_ryadom') and len(R.cifry(r['vidimyy_ryadom'])) == 11:
            vis = r['vidimyy_ryadom']
            vd = R.cifry(vis)
            vk10 = R.klyuch10(vd)
            if vk10 and vk10 != k10:
                # ссылка tel: без одной цифры («tel:7872764164» вместо 78172764164): видимый
                # номер получается из ссылки вставкой одной цифры – ссылка битая
                bez_cifry = any(vd[:i] + vd[i + 1:] in (k10, '7' + k10[:-1], '8' + k10[:-1]) or vd[:i] + vd[i + 1:] == k10
                                for i in range(len(vd)))
                vid = 'битый номер' if (bez_cifry or k10.startswith('7')) else 'номер только в ссылке tel:'
                vid_poch = ('в ссылке tel: не хватает цифры, на странице виден %s' % vis) if vid == 'битый номер' else (
                    'номер есть только в ссылке tel:, на странице рядом виден другой: %s' % vis)
                # видимый номер – отдельным контактом с той же подписью
                vv = '+7 %s %s-%s-%s' % (vk10[:3], vk10[3:6], vk10[6:8], vk10[8:])
                novyy(k['inn'], vv, polya.get('person', k['person']), polya.get('position', k['position'] or ''),
                      k['fragment'], url0, 'видимый номер рядом с битой ссылкой tel:', kid)
        if vid == 'Казахстан' and d10:
            # «+7 7xx» из ссылки tel: в 10 цифр (без кода страны) – цифры не хватает, это не Казахстан.
            # Настоящий казахстанский номер виден на странице с кодом +7 7xx полностью.
            vidim = [x for x in variants if re.search(r'\+\s?7[\s(-]*7\d\d', x['okrest'])]
            if not vidim or r.get('tolko_tel'):
                vid, vid_poch = 'битый номер', 'в ссылке tel: не хватает цифры (получилось «+7 7…», как у Казахстана)'
        if d10 and vid in ('рабочий', 'рабочий с добавочным') and d10[:3] not in VALID3:
            vid, vid_poch = 'битый номер', 'несуществующий код города %s' % d10[:3]
        # армянский/иной международный номер, ставший «+7 …»
        tekst374 = ' '.join([v['okrest']] if v else []) + ' ' + (k['fragment'] or '') + ' ' + ' '.join(
            (tekst(u) or {}).get('t', '') for u in [url0] if u)
        if d10.startswith('745') and re.search(r'\+\s?374', tekst374):
            m = re.search(r'\+\s?374[\d\s\-()]{6,14}\d', tekst374)
            if m:
                d374 = R.cifry(m.group(0))[3:]
                polya['value'] = '+374 %s %s-%s' % (d374[:2], d374[2:5], d374[5:]) if len(d374) == 8 else m.group(0)
                vid, vid_poch = 'международный', 'армянский номер (+374), разбор дописал «+7»'
        if vid != (k['phone_type'] or '') or vid_poch:
            polya['vid_nomera'] = vid
            if vid in ('8-800', 'международный', 'Казахстан', 'битый номер', 'не номер компании',
                       'номер только в ссылке tel:'):
                polya['phone_type'] = vid if vid in ('8-800', 'международный', 'Казахстан') else k['phone_type']
            if vid_poch:
                polya['vid_pochemu'] = vid_poch
            pochemu.append('вид: ' + vid + (' – ' + vid_poch if vid_poch else ''))
        # --- 2. роль по смыслу страницы: номер со страницы вакансий – кадры
        if url0 and STRANICA_VAKANSIY.search(urlsplit(url0).path or '') and not v:
            pass
        if url0 and STRANICA_VAKANSIY.search(urlsplit(url0).path or ''):
            rk = P.rol_kontakta({**k, **polya})
            if rk['vid'] in ('без подписи', 'общий номер', 'другая должность'):
                polya['rol_vruchnuyu'] = 'кадры'
                pochemu.append('номер со страницы вакансий (%s) – кадры' % urlsplit(url0).path)
        if polya:
            if v:
                polya['podpis_stranicy'] = (v['podp'] or '')[-200:]
            obnov.append({'id': kid, 'inn': k['inn'], 'value': k['value'], 'polya': polya,
                          'bylo': {f: k.get(f) for f in polya if f in k}, 'pochemu': '; '.join(pochemu)})
            zhurnal['обновлено контактов'] += 1
            for p in pochemu:
                zhurnal[p.split(' (')[0].split(' – ')[0][:40]] += 1

        # --- 7/6. другие вхождения того же номера с ДРУГИМ добавочным и подписью (общий
        # номер, у каждого человека свой добавочный) – отдельными контактами
        if variants and not k10.startswith('9') and not (k.get('chuzhoy_istochnik') or '').strip():
            for w in variants:
                if w is v or not w['dob'] or w['dob'] == dob_db or w['dob'] == polya.get('value', '')[-len(w['dob']):]:
                    continue
                if not (w['fio'] or P.vid_po_tekstu(w['dolzh'] or '')):
                    continue
                novyy(k['inn'], re.sub(r'\s*доб\..*$', '', k['value']).strip() + ' доб. ' + w['dob'],
                      w['fio'], w['dolzh'], w['okrest'], url0, 'тот же номер, другой добавочный: %s' % (
                          w['fio'] or w['dolzh']), kid)

    # --- 7. страницы с кодом «(341-41)»: подписанные номера, которых нет в каталоге
    po_url = collections.defaultdict(set)
    for k in kont.values():
        for u in (k['source_url'] or '').replace(';', ' ').split():
            po_url[u].add(k['inn'])
    for u, inns in po_url.items():
        m = meta.get(u)
        if not m or not m.get('fajl') or len(inns) != 1:
            continue
        h = R.dekodirovat(open(os.path.join(papka, m['fajl']), 'rb').read(), m.get('ct', ''))
        if not re.search(r'\(\s*\d{3,4}-\d{1,2}\s*\)\s*\d', h):
            continue
        inn = next(iter(inns))
        if any((x.get('chuzhoy_istochnik') or '').strip() for x in kont.values() if x['inn'] == inn and u in (x['source_url'] or '')):
            continue
        st = tekst(u)
        for i, x in enumerate(st['vh']):
            if x['tel'] or not x['k10']:
                continue
            p_, kak = st['rm'].get(i) or R.podpis(st['t'], st['vh'], i)
            fio, dolzh = R.fio_i_dolzhnost(p_)
            if not (fio or P.vid_po_tekstu(dolzh or '')):
                continue
            if CHUZHAYA_ORG.search(dolzh or ''):
                continue          # «Директор ООО «Элеватор»» – человек другого юрлица группы
            val = '+7 %s %s-%s-%s' % (x['k10'][:3], x['k10'][3:6], x['k10'][6:8], x['k10'][8:]) + (
                ' доб. ' + x['dob'] if x['dob'] else '')
            novyy(inn, val, fio, dolzh, st['t'][max(0, x['nach'] - 200):x['kon'] + 100], u,
                  'пропущенный номер формата «(341-41)»: %s' % (fio or dolzh))

    # --- 3. люди со страницы-источника (запись «должность + ФИО + контакты»):
    #   * ЛПР с личным номером, которого нет в каталоге – новый контакт;
    #   * ЛПР без номера (или только с общим 8-800 / местным номером без кода) –
    #     «спросить у приёмной: ФИО, должность» (в person, без телефона).
    bez_tel = []
    fio_s_nomerom = collections.defaultdict(set)

    def kl_fio(f):
        """Ключ человека: фамилия + первая буква имени («Соловей Е.В.» = «Евгений Соловей»)."""
        w = [x for x in re.sub(r'[^А-Яа-яЁё ]', ' ', f or '').replace('ё', 'е').replace('Ё', 'Е').split()]
        dl = [x for x in w if len(x) > 1]
        fam = [x for x in dl if not R._imya_li(x) and not R._OTCH.match(x)]
        imya = [x for x in w if R._imya_li(x) or len(x) == 1]
        if not fam:
            return ' '.join(sorted(x.lower() for x in w))
        return fam[0].lower() + ' ' + (imya[0][0].lower() if imya else '')
    for k in kont.values():
        if k['person']:
            fio_s_nomerom[k['inn']].add(kl_fio(k['person']))
    for o in obnov:
        if o['polya'].get('person'):
            fio_s_nomerom[o['inn']].add(kl_fio(o['polya']['person']))
    for n_ in novye:
        if n_['person']:
            fio_s_nomerom[n_['inn']].add(kl_fio(n_['person']))
    for p in lyudi:
        if p['person'] and (p['phone'] or '').strip():
            fio_s_nomerom[p['inn']].add(kl_fio(p['person']))
    obshchie = collections.defaultdict(set)      # 8-800 и номера приёмной/общие – не личные
    for k in kont.values():
        k10, _ = P.k10_iz_value(k['value'])
        if k10.startswith('800') or P.rol_kontakta(k)['vid'] in ('приёмная', 'общий номер'):
            obshchie[k['inn']].add(k10)
    uzhe_bez = set()
    for u, inns in sorted(po_url.items()):
        if len(inns) != 1 or not u.startswith('http') or STRANICA_VAKANSIY.search(urlsplit(u).path or ''):
            continue
        inn = next(iter(inns))
        if any((x.get('chuzhoy_istochnik') or '').strip() for x in kont.values() if x['inn'] == inn and u in (x['source_url'] or '')):
            continue
        st = tekst(u)
        if not st:
            continue
        for z in R.lyudi_stranicy(st['t']):
            if not z['fio'] or not z['dolzh'] or z['otzyv'] or CHUZHAYA_ORG.search(z['dolzh']) or len(z['fio'].split()) < 2:
                continue
            rk = P.rol_kontakta({'position': z['dolzh']})
            if not rk['lpr']:
                continue
            # общий номер: 8-800, номер приёмной, или основной номер, который в каталоге уже
            # есть с ДРУГИМИ добавочными (коммутатор)
            obshch = lambda x, d: (not d and x in obshchie[inn]) or x.startswith('800')  # noqa: E731
            lichnye = [(x, d) for x, d in dict.fromkeys(z['nomera'])
                       if not obshch(x, d) and (x, d) not in est_u[inn]
                       and not (not d and (x, '*') in est_u[inn])]
            for x, d in lichnye:
                val = '+7 %s %s-%s-%s' % (x[:3], x[3:6], x[6:8], x[8:]) + (' доб. ' + d if d else '')
                novyy(inn, val, z['fio'], z['dolzh'][:120], z['tekst'], u,
                      'человек со страницы-источника, номера не было в каталоге: %s' % z['fio'])
            if lichnye or any((x, d) in est_u[inn] for x, d in z['nomera'] if not obshch(x, d)):
                fio_s_nomerom[inn].add(kl_fio(z['fio']))
                continue
            kf = kl_fio(z['fio'])
            if kf in fio_s_nomerom[inn] or (inn, kf) in uzhe_bez:
                continue
            uzhe_bez.add((inn, kf))
            primech = []
            if z['korotkie']:
                primech.append('на странице местный номер без кода: ' + ', '.join(dict.fromkeys(z['korotkie'])))
            if z['nomera']:
                primech.append('на странице у него только общий номер')
            if z['pochta']:
                primech.append('почта: ' + ', '.join(dict.fromkeys(z['pochta'])))
            bez_tel.append({'inn': inn, 'person': z['fio'], 'position': z['dolzh'][:120], 'source_url': u,
                            'fragment': z['tekst'], 'vid': rk['vid'], 'primechanie': '; '.join(primech)})

    plan = {'obnovit': obnov, 'novye': novye, 'lpr_bez_telefona': bez_tel, 'zhurnal': dict(zhurnal)}
    json.dump(plan, open(vyhod, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('обновить %d, новых номеров %d, ЛПР без телефона %d' % (len(obnov), len(novye), len(bez_tel)))
    for k_, n_ in sorted(zhurnal.items(), key=lambda x: -x[1]):
        print('   %4d  %s' % (n_, k_))


VALID3 = set('''301 302 341 342 343 345 346 347 349 351 352 353 365 381 382 383 384 385 388 390 391 394 395
401 411 413 415 416 421 423 424 426 427 471 472 473 474 475 481 482 483 484 485 486 487 491 492 493 494
495 496 498 499 800 811 812 813 814 815 816 817 818 820 821 831 833 834 835 836 841 842 843 844 845 846
847 848 851 855 856 857 861 862 863 865 866 867 869 871 872 873 877 878 879'''.split())

if __name__ == '__main__':
    main()
