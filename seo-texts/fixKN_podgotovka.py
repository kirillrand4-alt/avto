# -*- coding: utf-8 -*-
r"""fixKN (22.10): пакет замены контактов и меток Битрикса для компаний «КО» панели КЦ – из файлов владельца.

Запускается В ПЕСОЧНИЦЕ (не на сервере): читает два xlsx владельца и пишет JSON-пакет; пакет (в нём номера) – только на
дроп, в git его не класть. Применяет пакет fixKN_primenit.py.

    python3 -I fixKN_podgotovka.py KO-OBOGASHCHENIE-21-10_2.xlsx kontakty_b2b_KO_2026-10-21.xlsx KN-paket.json

Что берётся:
  * «Обогащение», лист «Контакты» – все строки (контакты с сайта компании и с площадок, где компания – заказчик); номер
    без добавочного (добавочный – в phone_type: «рабочий, доб. 101»), мобильный – phone_type «мобильный»; источник – колонка
    «Источник», ссылка – «Ссылка на источник»; порядок в карточке – по листу «Прозвон по лесенке» (ступень, очерёдность);
  * B2B-Center, лист «Контакты» – номера (через запятую – по одному) и почты; источник «B2B-Center: лот от <дата>
    (<где найдено>)», ссылка – на лот; тип «технический» / «закупки» – флаги карточки;
  * НЕ берутся листы «Снято», «Спорные», «Контакты сайта группы» – их отбраковал сам автор файла.
Флаги: закупки – роль «Закупки / снабжение» (B2B: тип «закупки»); технический ЛПР – «ЛПР по оборудованию» = да при роли
техдиректор / механик-энергетик / производство / технолог / обогащение / качество (B2B: тип «технический»). Роль «Общий номер /
приёмная» пишется как «общий контакт» (панель не считает её ролью), «Прочее» – без роли.
Один и тот же контакт (ИНН, вид, значение, ФИО) из двух мест – одна строка, источники и ссылки накапливаются через « ; ».
Замена – у ВСЕХ 523 компаний «КО» (лист «Работа»): у 106, для которых в файлах нет контактов, старые тоже уходят (владелец 22.10:
«у 106 «КО» убрать все старые»).

Метки Битрикса (лист «Работа», колонки «Битрикс КЦ/СЦ», «Битрикс Meyer»), решение владельца 22.10:
  красная – идёт сделка в воронке КЦ; белая – идёт только «Общая воронка» («сам не знаю, что это значит»); зелёная – в
  Битриксе есть сделки, но не идёт ни КЦ, ни «Общая воронка» (идёт СЦ / Meyer, или сделки провалены / прошли); без метки –
  сделок нет. Текст метки – какие сделки идут; полная строка из файла – подсказкой.
"""
import json
import re
import sys

import openpyxl

TEH_ROLI = {'Техдиректор / главный инженер', 'Механик / энергетик / ремонт', 'Производство', 'Технолог',
            'Обогащение / горное', 'Качество / лаборатория'}


def list_(put, sh):
    ws = openpyxl.load_workbook(put, read_only=True, data_only=True)[sh]
    rows = list(ws.iter_rows(values_only=True))
    h = [str(x or '').strip() for x in rows[0]]
    return [dict(zip(h, r)) for r in rows[1:] if any(v not in (None, '') for v in r)]


def s(v):
    return '' if v is None else str(v).strip()


def nomer(raw):
    """«+7 900 000-00-00 доб. 101» -> («+79000000000», «101»). Нормализация – как normalize_phone панели."""
    t = s(raw)
    m = re.search(r'\s*доб\.?\s*(\d+)\s*$', t)
    dob = m.group(1) if m else ''
    if m:
        t = t[:m.start()]
    d = re.sub(r'\D', '', t)
    if len(d) == 11 and d[0] in '78':
        d = '7' + d[1:]
    elif len(d) == 10:
        d = '7' + d
    return ('+' + d if 10 <= len(d) <= 15 else ''), dob


def klyuch_nomera(v):
    d = re.sub(r'\D', '', v)
    return d[-10:]


def data_ru(iso):
    m = re.match(r'(\d{4})-(\d\d)-(\d\d)', iso or '')
    return '%s.%s.%s' % (m.group(3), m.group(2), m.group(1)) if m else (iso or '')


def aktivnye(stroka):
    m = re.search(r'АКТИВНАЯ: (.*?)(?: \| |$)', s(stroka))
    out = []
    for kus in (m.group(1).split('; ') if m else []):
        z = re.match(r'№(\d+) (.+?) / (.*?) \((\d{4}-\d\d-\d\d)\)\s*$', kus.strip())
        if z:
            out.append({'nomer': z.group(1), 'voronka': z.group(2).strip(), 'etap': z.group(3).strip(), 'data': z.group(4)})
    return out


def schet(stroka, slovo):
    m = re.search(r'%s (\d+)' % slovo, s(stroka))
    return int(m.group(1)) if m else 0


def metka(r):
    kc, mey = s(r.get('Битрикс КЦ/СЦ')), s(r.get('Битрикс Meyer'))
    if not (kc or mey):
        return None
    akt = aktivnye(kc) + aktivnye(mey)
    vor = [a['voronka'] for a in akt]
    if any(v.startswith('КЦ') for v in vor):
        cvet = 'krasnaya'
    elif 'Общая воронка' in vor:
        cvet = 'belaya'
    else:
        cvet = 'zelenaya'
    if akt:
        chasti = ['%s (%s, %s)' % (a['voronka'], a['etap'], data_ru(a['data'])) for a in akt]
        tekst = 'Битрикс: %s %s' % ('идёт' if len(akt) == 1 else 'идут', '; '.join(chasti))
    else:
        sd = schet(kc, 'сделок') + schet(mey, 'сделок')
        pr = schet(kc, 'провалено') + schet(mey, 'провалено')
        us = schet(kc, 'успешных') + schet(mey, 'успешных')
        tekst = 'Битрикс: активных нет · сделок %d (%s)' % (sd, ', '.join(
            x for x in ('успешных %d' % us if us else '', 'провалено %d' % pr if pr else '') if x) or 'без итога')
    podrobno = '\n'.join(x for x in ('Битрикс КЦ/СЦ: ' + kc if kc else '', 'Битрикс Meyer: ' + mey if mey else '') if x)
    return {'metka': cvet, 'tekst': tekst, 'podrobno': podrobno + '\n(файл «КО-обогащение» 21.10, лист «Работа»)'}


def main():
    obog, b2b, vyhod = sys.argv[1:4]
    # порядок по лесенке: (ИНН, ключ контакта) -> (ступень, очерёдность)
    lesenka = {}
    for r in list_(obog, 'Прозвон по лесенке'):
        inn = s(r['ИНН'])
        m = re.match(r'(\d+)', s(r['Ступень лесенки']))
        por = (int(m.group(1)) if m else 50, int(r['Очерёдность в компании'] or 0) if str(r['Очерёдность в компании'] or '').isdigit() else 0)
        if r['Телефон']:
            lesenka.setdefault((inn, 'phone', klyuch_nomera(nomer(r['Телефон'])[0])), por)
        if r['E-mail']:
            lesenka.setdefault((inn, 'email', s(r['E-mail']).lower()), por)
    kontakty, po_klyuchu = [], {}

    def dobavit(k):
        kl = (k['inn'], k['kind'], k['value'].lower(), k['person'].lower())
        if kl in po_klyuchu:        # тот же контакт из второго места – источники накапливаются
            b = po_klyuchu[kl]
            for pole in ('source', 'source_url'):
                if k[pole] and k[pole] not in b[pole].split(' ; '):
                    b[pole] = (b[pole] + ' ; ' + k[pole]) if b[pole] else k[pole]
            for f in ('is_purchaser', 'is_tech', 'has_role'):
                b[f] = max(b[f], k[f])
            b['poryadok'] = min(b['poryadok'], k['poryadok'])
            return
        po_klyuchu[kl] = k
        kontakty.append(k)

    for r in list_(obog, 'Контакты'):
        inn, rol = s(r['ИНН / УНП']), s(r['Роль'])
        zakup = int(rol == 'Закупки / снабжение')
        teh = int(s(r['ЛПР по оборудованию']).lower() == 'да' and rol in TEH_ROLI)
        rol_v = 'общий контакт' if rol == 'Общий номер / приёмная' else ('' if rol in ('Прочее', '') else rol)
        obshch = {'source': s(r['Источник']), 'source_url': s(r['Ссылка на источник']), 'person': s(r['ФИО']),
                  'position': s(r['Должность (как на сайте)']), 'role': rol_v, 'is_purchaser': zakup, 'is_tech': teh,
                  'has_role': int(bool(zakup or teh or (rol_v and rol_v != 'общий контакт'))), 'is_unknown_owner': 0,
                  'nomer_ne_lichnyy': 'общий номер / приёмная' if rol == 'Общий номер / приёмная' else ''}
        for pole, vid in (('Мобильный', 'мобильный'), ('Рабочий', 'рабочий')):
            if r[pole]:
                v, dob = nomer(r[pole])
                if not v:
                    continue
                dob = dob or s(r.get('Добавочный'))
                k = dict(obshch, inn=inn, kind='phone', value=v, phone_type=vid + (', доб. ' + dob if dob else ''))
                k['poryadok'] = list(lesenka.get((inn, 'phone', klyuch_nomera(v)), (50, 0)))
                dobavit(k)
        if r['E-mail']:
            v = s(r['E-mail'])
            k = dict(obshch, inn=inn, kind='email', value=v, phone_type='')
            k['poryadok'] = list(lesenka.get((inn, 'email', v.lower()), (50, 0)))
            dobavit(k)
    for r in list_(b2b, 'Контакты'):
        inn, tip = s(r['ИНН']), s(r['Тип контакта'])
        obshch = {'source': 'B2B-Center: лот от %s (%s)' % (s(r['Дата лота']), s(r['Где найдено']).lower()),
                  'source_url': s(r['Ссылка на лот']), 'person': s(r['ФИО']), 'position': s(r['Должность / роль']),
                  'role': {'технический': 'технический', 'закупки': 'закупки'}.get(tip, ''),
                  'is_purchaser': int(tip == 'закупки'), 'is_tech': int(tip == 'технический'),
                  'has_role': int(tip in ('закупки', 'технический')), 'is_unknown_owner': 0, 'nomer_ne_lichnyy': ''}
        por = [{'технический': 1, 'закупки': 5}.get(tip, 9), 99]
        for kus in re.split(r',\s*(?=\+?\d)', s(r['Телефон'])):
            v, dob = nomer(kus)
            if v:
                dobavit(dict(obshch, inn=inn, kind='phone', value=v, phone_type='доб. ' + dob if dob else '', poryadok=por))
        for v in re.split(r'[;,\s]+', s(r['Email'])):
            if '@' in v:
                dobavit(dict(obshch, inn=inn, kind='email', value=v, phone_type='', poryadok=por))
    kontakty.sort(key=lambda k: (k['inn'], k['poryadok'], 0 if k['kind'] == 'phone' else 1))
    metki = {}
    for r in list_(obog, 'Работа'):
        m = metka(r)
        if m:
            metki[s(r['ИНН'])] = m
    # владелец 22.10: старое убрать у ВСЕХ компаний «КО» – и у тех, для кого в файлах нет ни одного контакта (останутся пустыми)
    inn_zamena = sorted(s(r['ИНН']) for r in list_(obog, 'Работа'))
    paket = {'istochnik': [obog.split('/')[-1], b2b.split('/')[-1]], 'inn_zamena': inn_zamena, 'kontakty': kontakty,
             'metki': metki, 'inn_ko': sorted(s(r['ИНН']) for r in list_(obog, 'Работа'))}
    with open(vyhod, 'w', encoding='utf-8') as f:
        json.dump(paket, f, ensure_ascii=False)
    import collections
    print('компаний с заменой %d, контактов %d (%s); меток %d (%s); всего КО %d' % (
        len(inn_zamena), len(kontakty), dict(collections.Counter(k['kind'] for k in kontakty)), len(metki),
        dict(collections.Counter(m['metka'] for m in metki.values())), len(paket['inn_ko'])))


if __name__ == '__main__':
    main()
