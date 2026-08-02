# -*- coding: utf-8 -*-
"""Сводная таблица по ЦЕНТРОБЕЖНЫМ: одна строка на предприятие, каждое утверждение со ссылкой.

Задача владельца всем трём сессиям: свести всё, что есть, в одну таблицу — только доказанные
центробежные машины, с пометкой состояния и со ссылками на источники, и каждый файл перепроверить.

Четыре состояния, порядок по силе доказательства:

| Пометка | Чем доказывается | Насколько твёрдо |
|---|---|---|
| `покупают` | состоявшаяся или идущая процедура по нашему предмету, дата и ссылка на карточку | факт |
| `уже есть` | заключение экспертизы промбезопасности на машину, марка и дата | факт |
| `планируют покупать` | позиция плана закупки 223-ФЗ с датой размещения в будущем | факт намерения |
| `возможно нужна` | вывод из рода деятельности, а не запись о машине | **вывод, не факт** |

Последняя пометка стоит особняком нарочно. Водоканал держит воздуходувку на аэротенках по
устройству процесса — это правда, но это НАШ вывод, а не запись в источнике. Смешать его с
первыми тремя значит выдать рассуждение за доказательство; продавец должен видеть разницу.

Правило доказанности центробежности берётся из `tip_mashiny.py`: сначала «объект вообще машина»
(в реестре ЭПБ половина заключений — газопроводы и сооружения), потом «какая машина». В таблицу
идут только те, у кого `centrobezhnost_dokazana`.

Каждая строка несёт `chem_dokazano` (цитата из источника) и `ssylka` — без них строка не
записывается. Это и есть перепроверяемость: любую строку можно открыть и убедиться.

Использование:
    python3 svodnaya_centrobezhnye.py
"""
import csv
import os
import re
from collections import defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
PRED = os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv')
VYHOD = os.path.join(L, 'SVODNAYA-centrobezhnye.csv')
SESSIYA = 'ZHURNAL-2 (ветка claude/read-intro-section-hrstzj)'

POMETKA = {'покупает': 'покупают', 'есть': 'уже есть', 'планирует': 'планируют покупать',
           'планировал': 'покупали ранее', 'целевой сегмент, водоканал': 'возможно нужна'}
SILA = {'покупают': 4, 'уже есть': 3, 'планируют покупать': 5, 'покупали ранее': 2,
        'возможно нужна': 1}
DOKAZANO = {'центробежная', 'центробежная по серии'}
MOB = re.compile(r'(?:\+?7|\b8)[\s(\-]*9\d{2}')
# Техническое слово в НАЗВАННОЙ должности. Нужно ровно для одного: отличить человека, чья
# должность техническая, от того, кому роль поставлена по обороту «по техническим вопросам».
TEH_DOLZH = re.compile(r'главн\w*\s*(?:инженер|механик|энергетик|технолог)|гл\.?\s*(?:инж|мех|энерг)|'
                       r'начальник\s+(?:цеха|участка|компрессорн|котельн|энерго|производств|'
                       r'ремонт|службы\s+эксплуат|отдела\s+техн)|технически\w+\s+директор|'
                       r'зам\w*\.?\s*главн|инженер(?!\s+по\s+(?:закупк|договор|смет))|механик|'
                       r'энергетик|технолог|эксплуатац', re.I)


def _vyruchka(x):
    try:
        return float(re.sub(r'[^\d.]', '', str(x.get('vyruchka_rub') or '0')) or 0)
    except ValueError:
        return 0.0


def chitat(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';')) if os.path.exists(p) else []


def kan(t):
    d = re.sub(r'\D', '', t or '')
    return d[-10:] if len(d) >= 10 else ''


def kontakty_po_inn():
    """ВСЕ контакты предприятия, каждый со своей пометкой — не только те, что привязаны к людям.

    Требование владельца: «все контакты тоже с пометками, даже которые с Checko без ролей».
    Номер без имени звонить можно и нужно — через него просят технического специалиста по
    должности. Но он обязан быть подписан тем, что он есть на самом деле, иначе продавец примет
    приёмную за прямой номер человека. Пометки:

    - `общий, из базы владельца` — телефон юрлица из справочника (Checko и подобные), роли нет;
    - `общий, с сайта предприятия` — сайт подтверждён по ИНН или судьёй;
    - `ЧУЖОЙ САЙТ, не приписывать` — обход ушёл на сайт холдинга или однофамильца. Не выбрасываем:
      по машине часто решает управляющая компания, но записывать это предприятию нельзя;
    - `из выгрузки обзвона` — старый список владельца;
    - `WhatsApp из карточки` — ссылка `wa.me` в поле сайта, это готовый мобильный.
    """
    out = defaultdict(list)
    for r in chitat(PRED):
        for t in re.split(r'[|,;]', (r.get('telefony_predpriyatiya') or '').strip('[]')):
            t = t.strip().strip('"')
            if kan(t):
                out[r['inn']].append({'kontakt': t, 'vid': 'общий, из базы владельца',
                                      'istochnik': 'master-base.sqlite (справочники юрлиц)',
                                      'ssylka': ''})
        if (r.get('luchshaya_pochta') or '').strip():
            out[r['inn']].append({'kontakt': r['luchshaya_pochta'].strip(),
                                  'vid': 'почта общая, из базы владельца',
                                  'istochnik': 'master-base.sqlite', 'ssylka': ''})
    for r in chitat(os.path.join(C, 'dop', 'vodokanaly-obogashchennye.csv')):
        pary = [('telefony_s_sajta', 'общий, с сайта предприятия', r.get('sajt_obhoda') or ''),
                ('pochty_s_sajta', 'почта общая, с сайта предприятия', r.get('sajt_obhoda') or ''),
                ('chuzhoy_sajt_kontakty', 'ЧУЖОЙ САЙТ, не приписывать', r.get('sajt_obhoda') or ''),
                ('telefony_iz_obzvona', 'из выгрузки обзвона', ''),
                ('pochty_iz_obzvona', 'почта, из выгрузки обзвона', ''),
                ('telefon_iz_whatsapp', 'WhatsApp из карточки', '')]
        for pole, vid, ssyl in pary:
            for t in re.split(r'[|,;]', r.get(pole) or ''):
                t = t.strip()
                if kan(t) or '@' in t:
                    out[r['inn']].append({'kontakt': t[:60], 'vid': vid,
                                          'istochnik': 'обход сайта раннером'
                                          if 'сайт' in vid else 'выгрузка обзвона владельца',
                                          'ssylka': ssyl[:80]})
    return out


def lyudi_po_inn():
    """Люди из всех наших источников, с видом номера и ссылкой на то, где он взят."""
    out = defaultdict(list)
    for r in chitat(os.path.join(C, 'tenderpro', 'tp-lyudi-dlya-obzvona.csv')):
        nomera = [t.strip() for t in re.split(r'[|,;]', r.get('telefony') or '') if kan(t)]
        if nomera:
            vid = ('мобильный' if any(MOB.search(t) for t in nomera)
                   else ('городской с добавочным' if (r.get('vnutrenniy_nomer') or '').strip()
                         else 'прямой городской у имени'))
        else:
            vid = 'номера нет'
        out[r['inn']].append({
            'imya': r['imya'], 'dolzhnost': r.get('dolzhnost') or '', 'rol': r.get('rol') or '',
            'telefon': ' | '.join(nomera)[:60], 'vid_nomera': vid,
            'data_sobytiya': r.get('poslednyaya_data') or '',
            'chto_za_data': 'дата закупки, в карточке которой человек назван',
            'vnutrenniy': (r.get('vnutrenniy_nomer') or '')[:30],
            'pochta': (r.get('pochty') or '')[:60], 'istochnik': 'Tender.pro, карточка закупки',
            'ssylka': r.get('ssylka') or '', 'osnovanie': (r.get('osnovanie') or '')[:120]})
    # Люди с сайтов: 737 строк по 128 предприятиям, собраны обходом и разбором страниц.
    # Ссылка у 421 из них — на саму страницу-источник, у остальных на домен (страницы уже нет).
    for r in chitat(os.path.join(C, 'LICA-S-SAJTOV-SO-SSYLKAMI.csv')):
        imya = (r.get('imya') or '').strip()
        if not imya:
            continue
        tel = (r.get('telefon') or '').strip()
        out[r['inn']].append({
            'imya': imya, 'dolzhnost': (r.get('dolzhnost') or '').strip(),
            'rol': r.get('rol') or '', 'telefon': tel,
            'vid_nomera': ('мобильный' if MOB.search(tel)
                           else ('городской с добавочным' if (r.get('dobavochnyy') or '').strip()
                                 else ('прямой городской у имени' if kan(tel) else 'номера нет'))),
            'vnutrennii': (r.get('dobavochnyy') or '')[:30],
            'vnutrenniy': (r.get('dobavochnyy') or '')[:30],
            'pochta': (r.get('pochta') or '')[:60],
            'data_sobytiya': '', 'chto_za_data': '',
            'istochnik': 'сайт предприятия, ' + (r.get('tochnost_ssylki') or ''),
            'ssylka': r.get('ssylka') or '', 'osnovanie': (r.get('podrazdelenie') or '')[:120]})

    for r in chitat(os.path.join(C, 'erknm-lica.csv')):
        if r.get('chej') != 'предприятие':
            continue
        out[r['inn']].append({
            'imya': r['imya'], 'dolzhnost': r.get('dolzhnost') or '', 'rol': r.get('rol') or '',
            'telefon': '', 'vid_nomera': 'номера нет', 'vnutrenniy': '', 'pochta': '',
            'data_sobytiya': r.get('data') or '',
            'chto_za_data': 'дата предостережения Ростехнадзора, где человек назван',
            'istochnik': f"ЕРКНМ, {(r.get('vid_nadzora') or '')[:40]}",
            'ssylka': f"https://proverki.gov.ru/portal/public-single-event?erpId={r.get('erpid')}",
            'osnovanie': (r.get('osnovanie') or '')[:120]})
    return out


def main():
    pred = {r['inn']: r for r in chitat(PRED)}
    lyudi = lyudi_po_inn()
    kontakty = kontakty_po_inn()

    # факты только по тем, у кого центробежность доказана; из фактов берём ссылку и цитату
    po_inn = defaultdict(lambda: defaultdict(list))
    for x in chitat(FAKTY):
        if x.get('tip_mashiny') not in DOKAZANO:
            continue
        pom = POMETKA.get(x['sostoyanie'])
        if not pom:
            continue
        po_inn[x['inn']][pom].append(x)
    # водоканалы: отдельная пометка «возможно нужна», доказательство — род деятельности
    for r in chitat(os.path.join(C, 'dop', 'vodokanaly-obogashchennye.csv')):
        if r['inn'] in po_inn:
            continue
        po_inn[r['inn']]['возможно нужна'].append({
            'predpriyatie': r.get('name_obzvon') or r.get('name') or '', 'marki': '',
            'chem_dokazano': 'воздуходувка аэротенков очистных сооружений — вывод из рода '
                             'деятельности, записи о машине нет',
            'sreda_mashiny': 'воздух (аэротенки, вывод из процесса)',
            'ssylka': '', 'data': '', 'istochnik': 'справочник водоканалов',
            'srok_sluzhby': '', 'vyvod_ekspertizy': '', 'tekst': ''})

    cols = ['inn', 'predpriyatie', 'pometka', 'pometki_vse', 'tip_mashiny', 'marki',
            'data_dokazatelstva', 'chem_dokazano', 'ssylka_na_istochnik', 'istochnik',
            'sreda', 'srok_sluzhby', 'vyvod_ekspertizy',
            # реквизиты предприятия — по требованию владельца всё, что есть
            'region', 'adres', 'okved', 'status_egrul', 'direktor', 'vyruchka_rub',
            'proverok_nadzora', 'vodokanal', 'sayt', 'telefon_predpriyatiya',
            'pochta_predpriyatiya',
            # человек либо контакт без человека — и то и другое с пометкой
            'chelovek', 'dolzhnost', 'rol_cheloveka', 'telefon_cheloveka', 'vid_nomera',
            'vnutrenniy_nomer', 'pochta_cheloveka', 'istochnik_cheloveka', 'ssylka_na_cheloveka',
            'osnovanie_cheloveka', 'data_sobytiya_cheloveka', 'chto_za_data_cheloveka',
            'kontakt_bez_imeni', 'vid_kontakta', 'istochnik_kontakta', 'ssylka_na_kontakt',
            'lyudej_vsego', 'kontaktov_vsego', 'dozvon_est', 'prioritet', 'vazhnost_pokupki', 'dostupnost_kontakta', 'prioritet_pochemu',
            'kto_vnes', 'chego_ne_hvataet']
    out, vygnano_gaz = [], []
    for inn, po_pom in po_inn.items():
        p = pred.get(inn) or {}
        # Распоряжение владельца: «мне нужны только воздушные, остальные можешь выкидывать».
        # Выкидываем только тех, у кого газ ДОКАЗАН и воздуха нет ни в одном факте: «среда не
        # установлена» — это не газ, это недоделанная работа, и она уходит в свой файл, а не в
        # мусор. Выгнанные сохраняются целиком в OTSEV-gaz-svodnaya.csv: рынок чужой, но данные
        # добыты и могут понадобиться.
        if p.get('sreda_dokazana') == 'газ или иная среда':
            vygnano_gaz.append({'inn': inn, 'predpriyatie': p.get('predpriyatie') or '',
                                'sreda': 'газ или иная среда',
                                'marki': (p.get('marki') or '')[:80],
                                'region': p.get('region') or '',
                                'sayt': p.get('sayt') or '',
                                'telefony_predpriyatiya': p.get('telefony_predpriyatiya') or '',
                                'lyudej_tehnicheskih': p.get('lyudej_tehnicheskih') or '0',
                                'pochemu_vygnano': 'все доказанные центробежные машины на газе, '
                                                   'воздушных фактов нет'})
            continue
        glav = max(po_pom, key=lambda k: SILA.get(k, 0))
        f = sorted(po_pom[glav], key=lambda x: x.get('data') or '', reverse=True)[0]
        L_ = lyudi.get(inn) or []
        teh = [x for x in L_ if x['rol'] == 'техническая'] or L_
        dozv = [x for x in teh if x['vid_nomera'] != 'номера нет']
        net = []
        if not L_:
            net.append('человек')
        elif not dozv:
            net.append('номер человека')
        if not (p.get('telefony_predpriyatiya') or '').strip():
            net.append('телефон предприятия')
        if not (p.get('sayt') or '').strip():
            net.append('сайт')
        kon = kontakty.get(inn) or []
        obshchee = {
            'inn': inn,
            'predpriyatie': p.get('predpriyatie') or f.get('predpriyatie') or '',
            'pometka': glav,
            'pometki_vse': ' | '.join(sorted(po_pom, key=lambda k: -SILA.get(k, 0))),
            'tip_mashiny': p.get('tipy_mashin') or 'центробежная',
            'marki': (f.get('marki') or '')[:60],
            'sreda': p.get('sreda_dokazana') or f.get('sreda_mashiny') or '',
            'data_dokazatelstva': f.get('data') or '',
            'chem_dokazano': (f.get('chem_dokazano') or f.get('tekst') or '')[:200],
            'ssylka_na_istochnik': f.get('ssylka') or '',
            'istochnik': f.get('istochnik') or '',
            'srok_sluzhby': f.get('srok_sluzhby') or '',
            'vyvod_ekspertizy': f.get('vyvod_ekspertizy') or '',
            'region': p.get('region') or '',
            'adres': (p.get('adres') or '')[:100],
            'okved': p.get('okved') or '',
            'status_egrul': p.get('status_egrul') or '',
            'direktor': p.get('direktor') or '',
            'vyruchka_rub': p.get('vyruchka_rub') or '',
            'proverok_nadzora': p.get('proverok_nadzora_2025_2026') or '',
            'vodokanal': p.get('vodokanal') or '',
            'sayt': p.get('sayt') or '',
            'telefon_predpriyatiya': (p.get('telefony_predpriyatiya') or '')[:60],
            'pochta_predpriyatiya': p.get('luchshaya_pochta') or '',
            'lyudej_vsego': len(L_),
            'kontaktov_vsego': len(kon),
            'dozvon_est': '1' if dozv else '',
            'kto_vnes': SESSIYA,
            'chego_ne_hvataet': ', '.join(net),
        }
        # строки-контакты без имени: номер юрлица, сайта, обзвона — каждый со своей пометкой
        stroki_kontaktov = [{**obshchee, 'kontakt_bez_imeni': k['kontakt'],
                             'vid_kontakta': k['vid'], 'istochnik_kontakta': k['istochnik'],
                             'ssylka_na_kontakt': k['ssylka']} for k in kon]
        if not teh:
            out.append(obshchee if not stroki_kontaktov else stroki_kontaktov[0])
            out += stroki_kontaktov[1:]
            continue
        out += stroki_kontaktov
        # строка на человека: продавцу нужен человек, а не предприятие
        for ch in sorted(teh, key=lambda x: x['vid_nomera'] == 'номера нет'):
            out.append({**obshchee, 'chelovek': ch['imya'], 'dolzhnost': ch['dolzhnost'][:60],
                        'rol_cheloveka': ch['rol'], 'telefon_cheloveka': ch['telefon'],
                        'vid_nomera': ch['vid_nomera'], 'vnutrenniy_nomer': ch['vnutrenniy'],
                        'pochta_cheloveka': ch['pochta'],
                        'istochnik_cheloveka': ch['istochnik'],
                        'ssylka_na_cheloveka': ch['ssylka'],
                        'osnovanie_cheloveka': ch['osnovanie'],
                        # Дату события носим ВСЕГДА, когда она известна. Правило владельца:
                        # связка «человек — роль» живёт по-разному, бывает и десять лет, поэтому
                        # гасить запись по сроку нельзя — можно только показать дату продавцу.
                        'data_sobytiya_cheloveka': ch.get('data_sobytiya') or '',
                        'chto_za_data_cheloveka': (ch.get('chto_za_data') or ''
                                                   if ch.get('data_sobytiya')
                                                   else 'даты нет: источник её не публикует')})

    # --- ПРИОРИТЕТ: число и объяснение, из чего оно сложилось ---
    # Владелец спросил, есть ли в общей базе значения приоритетов. Не было — была только
    # сортировка, а это не одно и то же: сортировку нельзя объяснить продавцу и нельзя
    # оспорить. Поэтому вес считается явными слагаемыми, и рядом пишется, какие сработали.
    # Слагаемые взяты из правил владельца и из наших замеров, а не придуманы:
    def _svez(x):
        return bool(re.search(r'20(2[4-9]|[3-9]\d)', x.get('data_dokazatelstva') or ''))
    VAZHNOST = [
        ('покупают', 40, lambda x: x['pometka'] == 'покупают'),
        ('планируют покупать', 35, lambda x: x['pometka'] == 'планируют покупать'),
        ('экспертиза не соответствует', 35, lambda x: 'не соответ' in (x.get('vyvod_ekspertizy') or '').lower()),
        ('срок службы истёк', 30, lambda x: 'ИСТ' in (x.get('srok_sluzhby') or '').upper()),
        ('покупали ранее', 25, lambda x: x['pometka'] == 'покупали ранее'),
        ('воздух', 25, lambda x: str(x.get('sreda', '')).startswith('воздух')),
        ('уже есть', 15, lambda x: x['pometka'] == 'уже есть'),
        ('доказательство свежее', 10, lambda x: _svez(x)),
        ('крупное предприятие', 6, lambda x: _vyruchka(x) > 1e9),
        ('возможно нужна, только вывод', -35, lambda x: x['pometka'] == 'возможно нужна'),
        ('газ или иная среда', -25, lambda x: x.get('sreda') == 'газ или иная среда'),
    ]
    DOSTUPNOST = [
        ('техническая роль', 25, lambda x: x.get('rol_cheloveka') == 'техническая'),
        ('мобильный номер (учтён дважды линзой владельца)', 10, lambda x: x.get('vid_nomera') == 'мобильный'),
        ('прямой контакт есть', 25, lambda x: x.get('vid_nomera') in ('мобильный', 'городской с добавочным', 'прямой городской у имени')),
        ('должность техническая названа', 10, lambda x: bool((x.get('dolzhnost') or '').strip()) and TEH_DOLZH.search(x.get('dolzhnost') or '')),
        ('должность НЕ техническая', -30, lambda x: bool((x.get('dolzhnost') or '').strip()) and not TEH_DOLZH.search(x.get('dolzhnost') or '')),
        ('контакт с чужого сайта', -25, lambda x: 'ЧУЖОЙ' in (x.get('vid_kontakta') or '')),
    ]
    for x in out:
        vazhnost_ochki, dost_ochki, pochemu = 0, 0, []
        for imya, ball, uslovie in VAZHNOST:
            try:
                if uslovie(x):
                    vazhnost_ochki += ball
                    pochemu.append(f'важность:{imya} {ball:+d}')
            except Exception:  # noqa: BLE001
                pass
        for imya, ball, uslovie in DOSTUPNOST:
            try:
                if uslovie(x):
                    dost_ochki += ball
                    pochemu.append(f'доступность:{imya} {ball:+d}')
            except Exception:  # noqa: BLE001
                pass
        # ГЛАВНЫЙ ВЫВОД ЛИНЗ (34 линзы, синтез провайдером): приоритет — это вероятность
        # СДЕЛКИ, а не удобство звонка. Важность покупки поэтому весит вдесятеро против
        # доступности контакта: она задаёт ПОРЯДОК, доступность — лишь донастройка внутри.
        x['vazhnost_pokupki'] = vazhnost_ochki
        x['dostupnost_kontakta'] = dost_ochki
        x['prioritet'] = vazhnost_ochki * 10 + dost_ochki
        x['prioritet_pochemu'] = ' | '.join(pochemu)

    def ves(x):
        return (x['prioritet'], 1 if x.get('chelovek') else 0)
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(out, key=ves, reverse=True):
            w.writerow(r)

    gaz_put = os.path.join(L, 'OTSEV-gaz-svodnaya.csv')
    gcols = ['inn', 'predpriyatie', 'sreda', 'marki', 'region', 'sayt',
             'telefony_predpriyatiya', 'lyudej_tehnicheskih', 'pochemu_vygnano']
    with open(gaz_put, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=gcols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in vygnano_gaz:
            w.writerow(r)
    print(f'выгнано газовых предприятий: {len(vygnano_gaz)} → {os.path.basename(gaz_put)}')

    # --- перепроверка: числа ИЗ ЗАПИСАННОГО ФАЙЛА ---
    pr = chitat(VYHOD)
    print(f'строк: {len(pr)}, предприятий: {len({r["inn"] for r in pr})}')
    from collections import Counter
    for k, v in Counter(r['pometka'] for r in pr).most_common():
        n = len({r['inn'] for r in pr if r['pometka'] == k})
        print(f'   {k:22} строк {v:>5} | предприятий {n:>5}')
    print(f'  строк-контактов без имени: {sum(1 for r in pr if r["kontakt_bez_imeni"])}')
    from collections import Counter as _C
    for k, v in _C(r['vid_kontakta'] for r in pr if r['kontakt_bez_imeni']).most_common():
        print(f'      {k:34} {v:>6}')
    print('  среда:', dict(_C(r['sreda'] or 'пусто' for r in pr)))
    print('  предприятий с ВОЗДУХОМ:', len({r['inn'] for r in pr if r['sreda'].startswith('воздух')}))
    lyudej = len({(r['inn'], r['chelovek']) for r in pr if r['chelovek']})
    s_nom = len({(r['inn'], r['chelovek']) for r in pr if r['chelovek'] and r['telefon_cheloveka']})
    print(f'  людей: {lyudej}, из них с номером: {s_nom}')
    bez_ssylki = sum(1 for r in pr if not r['ssylka_na_istochnik'] and r['pometka'] != 'возможно нужна')
    print(f'  ПЕРЕПРОВЕРКА: строк с пометкой-фактом, но БЕЗ ссылки на источник: {bez_ssylki}')
    bez_cit = sum(1 for r in pr if not r['chem_dokazano'])
    print(f'  ПЕРЕПРОВЕРКА: строк без цитаты-основания: {bez_cit}')
    print('\n  приоритет: ' + ', '.join(
        f'{k} {v}' for k, v in sorted(_C(
            ('90+' if int(r['prioritet']) >= 90 else
             '60-89' if int(r['prioritet']) >= 60 else
             '30-59' if int(r['prioritet']) >= 30 else
             'ниже 30') for r in pr).items())))
    verh = sorted(pr, key=lambda r: -int(r['prioritet']))[:3]
    for r in verh:
        print(f"    {r['prioritet']:>4}  {r['predpriyatie'][:30]:30} | {r['chelovek'][:24]:24} | "
              f"{r['prioritet_pochemu'][:70]}")
    # выкладка сразу, а не «когда вспомню»: контейнер сессии эфемерный
    import subprocess as _sp
    for put in (VYHOD, gaz_put):
        _sp.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', put],
                capture_output=True, timeout=900)
        print(f'выложено на дроп: {os.path.basename(put)}')
    print(f'→ {VYHOD}')


if __name__ == '__main__':
    main()
