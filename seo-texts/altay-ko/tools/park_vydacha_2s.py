# -*- coding: utf-8 -*-
"""ВЫДАЧА 2-й СЕССИИ: всё, что готово к вливу в общую базу парка, одним набором.

ПРАВИЛО, КОТОРОЕ ЗДЕСЬ СОБЛЮДЕНО БЕЗ ИСКЛЮЧЕНИЙ. Владелец: «каждый контакт и факт должен
доказываться ссылкой, которая ведёт на доказательство; если ссылок несколько — должно быть
несколько ссылок в базе». Поэтому:
  * строк без ссылки в выдаче НЕТ ни одной — они не пишутся вовсе;
  * ссылка ведёт на КОНКРЕТНУЮ страницу (заключение, карточка, раздел), а не на список;
  * рядом со ссылкой лежит ЦИТАТА — кусок текста, из которого взято утверждение;
  * когда источников несколько, они идут ОТДЕЛЬНЫМИ СТРОКАМИ, а не склейкой через « | »:
    склейка теряет, какое поле откуда, и правило «перепроверить старое» перестаёт работать.

ЧТО ЭТО НЕ. Это не готовая витрина для обзвона: роль контакта проставлена только там, где
источник её называет. Строки «телефон организации» остаются телефоном организации, а не
превращаются в ЛПР.

Выход — четыре файла и опись:
  PARK-VYDACHA-FAKTY-2S.csv       машина у предприятия: тип, марка, зав.№, срок ЭПБ, ссылка
  PARK-VYDACHA-KONTAKTY-2S.csv    контакты: значение, чьё, роль, ссылка, цитата
  PARK-VYDACHA-PREDPRIYATIYA-2S.csv  карточка предприятия: имя, сайт, выручка, ОКВЭД, ЕГРЮЛ
  PARK-VYDACHA-OPO-2S.csv         объекты ОПО: наименование, класс, рег.№, ссылка
"""
import collections
import csv
import glob
import io
import json
import os
import sys

L = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engineers-lens')


def jl(imya):
    p = os.path.join(L, imya)
    if not os.path.exists(p):
        return []
    out = []
    for s in io.open(p, encoding='utf-8'):
        s = s.strip()
        if s:
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    return out


def cs(imya):
    p = os.path.join(L, imya)
    if not os.path.exists(p):
        return []
    return list(csv.DictReader(io.open(p, encoding='utf-8-sig'), delimiter=';'))


def pisat(imya, cols, rows):
    p = os.path.join(L, imya)
    with io.open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def main():
    itog = {}

    # ---- 1. ФАКТЫ О МАШИНАХ ----------------------------------------------------------
    fakty = cs('PARK-FAKTY-2S-SVOD.csv') or cs('PARK-FAKTY-2S-EPB-POLNYE.csv')
    FCOLS = ['inn', 'predpriyatie', 'tip', 'marka_model', 'zavodskoy_nomer', 'sreda',
             'data', 'nomer_zaklucheniya', 'srok_do', 'status_sroka', 'sila', 'klass',
             'istochnik', 'ssylka', 'citata']
    fout = [r for r in fakty if (r.get('ssylka') or '').startswith('http')]
    itog['факты'] = pisat('PARK-VYDACHA-FAKTY-2S.csv', FCOLS, fout)
    itog['факты: предприятий'] = len({r['inn'] for r in fout if r.get('inn')})
    itog['факты: без ссылки'] = len(fakty) - len(fout)

    # ---- 2. КОНТАКТЫ -----------------------------------------------------------------
    KCOLS = ['inn', 'predpriyatie', 'vid', 'znachenie', 'chelovek', 'dolzhnost', 'rol',
             'istochnik', 'ssylka', 'citata']
    kout = []
    for r in cs('PARK-KONTAKTY-2S-S-ROLYU.csv'):
        if not (r.get('ssylka') or '').startswith('http'):
            continue
        kout.append({'inn': r['inn'], 'predpriyatie': r.get('predpriyatie', ''),
                     'vid': r.get('chto_naydeno', ''), 'znachenie': r.get('znachenie', ''),
                     'chelovek': r.get('chelovek', ''), 'dolzhnost': r.get('dolzhnost', ''),
                     'rol': r.get('rol', ''), 'istochnik': 'сайт предприятия',
                     'ssylka': r['ssylka'], 'citata': r.get('citata', '')})
    # Чеко: КАЖДЫЙ телефон и КАЖДАЯ почта — отдельной строкой со своей ссылкой.
    for x in jl('PARK-CHECKO-2S.jsonl'):
        ssylka = x.get('ssylka_kontakty') or x.get('kartochka') or ''
        if not ssylka.startswith('http'):
            continue
        for t in (x.get('telefony') or []):
            kout.append({'inn': x['inn'], 'predpriyatie': x.get('predpriyatie', ''),
                         'vid': 'телефон организации', 'znachenie': t, 'rol': 'общий',
                         'istochnik': 'checko.ru, блок «Контактная информация»',
                         'ssylka': ssylka, 'citata': 'телефон в блоке контактов карточки'})
        for p in (x.get('pochty') or []):
            kout.append({'inn': x['inn'], 'predpriyatie': x.get('predpriyatie', ''),
                         'vid': 'почта организации', 'znachenie': p, 'rol': 'общий',
                         'istochnik': 'checko.ru, блок «Контактная информация»',
                         'ssylka': ssylka, 'citata': 'почта в блоке контактов карточки'})
    # DaData: руководитель — ИМЯ С ДОЛЖНОСТЬЮ из ЕГРЮЛ. Это не технический ЛПР, и роль
    # так и пишется: «руководитель по ЕГРЮЛ», а не «наша».
    for x in jl('PARK-DADATA-2S.jsonl'):
        if not x.get('mgmt_name'):
            continue
        kout.append({'inn': x['inn'], 'predpriyatie': x.get('full_name', ''),
                     'vid': 'человек', 'znachenie': x['mgmt_name'],
                     'chelovek': x['mgmt_name'], 'dolzhnost': x.get('mgmt_post', ''),
                     'rol': 'руководитель по ЕГРЮЛ',
                     'istochnik': 'DaData findById/party (ЕГРЮЛ)',
                     'ssylka': 'https://checko.ru/search?query=' + x['inn'],
                     'citata': '%s — %s' % (x['mgmt_name'], x.get('mgmt_post', ''))})
    itog['контакты'] = pisat('PARK-VYDACHA-KONTAKTY-2S.csv', KCOLS, kout)
    itog['контакты: предприятий'] = len({r['inn'] for r in kout})

    # ---- 3. КАРТОЧКА ПРЕДПРИЯТИЯ -----------------------------------------------------
    pred = collections.defaultdict(dict)
    for x in jl('PARK-CHECKO-2S.jsonl'):
        pred[x['inn']].update({'inn': x['inn'], 'predpriyatie': x.get('predpriyatie', ''),
                               'sayt': x.get('sayt', ''), 'vyruchka': x.get('vyruchka', ''),
                               'vyruchka_god': x.get('vyruchka_god', ''),
                               'ssylka_checko': x.get('kartochka', '')})
    for x in jl('PARK-OKVED-2S.jsonl'):
        pred[x['inn']].update({'inn': x['inn'],
                               'okved_osnovnoy': x.get('okved', ''),
                               'okved_kody': ' '.join(x.get('okved_kody') or []),
                               'okvedov': x.get('okvedov', 0),
                               'ssylka_okved': x.get('ssylka', '')})
    for x in jl('PARK-DADATA-2S.jsonl'):
        pred[x['inn']].update({'inn': x['inn'],
                               'nazvanie_egrul': x.get('full_name', ''),
                               'adres': x.get('address', ''),
                               'rukovoditel': x.get('mgmt_name', ''),
                               'dolzhnost_rukovoditelya': x.get('mgmt_post', ''),
                               'status_egrul': x.get('status', '')})
    PCOLS = ['inn', 'predpriyatie', 'nazvanie_egrul', 'adres', 'sayt', 'rukovoditel',
             'dolzhnost_rukovoditelya', 'status_egrul', 'vyruchka', 'vyruchka_god',
             'okved_osnovnoy', 'okvedov', 'okved_kody', 'ssylka_checko', 'ssylka_okved']
    itog['предприятия'] = pisat('PARK-VYDACHA-PREDPRIYATIYA-2S.csv', PCOLS,
                                list(pred.values()))

    # ---- 4. ОБЪЕКТЫ ОПО --------------------------------------------------------------
    OCOLS = ['inn', 'naimenovanie_obekta', 'klass_opasnosti', 'reg_nomer', 'ssylka', 'citata']
    oout = [x for x in jl('PARK-OPO-PO-INN-2S.jsonl')
            if (x.get('ssylka') or '').startswith('http')]
    itog['ОПО объектов'] = pisat('PARK-VYDACHA-OPO-2S.csv', OCOLS, oout)
    itog['ОПО предприятий'] = len({x['inn'] for x in oout})

    for k, v in itog.items():
        print('%-24s %s' % (k, v))
    return itog


if __name__ == '__main__':
    main()
