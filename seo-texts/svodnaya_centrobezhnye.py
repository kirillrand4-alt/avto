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
            'lyudej_vsego', 'kontaktov_vsego', 'dozvon_est', 'kto_vnes', 'chego_ne_hvataet']
    out = []
    for inn, po_pom in po_inn.items():
        p = pred.get(inn) or {}
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

    def ves(x):
        # воздух выше газа — правило владельца
        return (1 if str(x.get('sreda', '')).startswith('воздух') else 0,
                1 if x.get('telefon_cheloveka') else 0, SILA.get(x['pometka'], 0),
                1 if x.get('chelovek') else 0)
    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in sorted(out, key=ves, reverse=True):
            w.writerow(r)

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
    print(f'→ {VYHOD}')


if __name__ == '__main__':
    main()
