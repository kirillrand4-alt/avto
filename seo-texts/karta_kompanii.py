# -*- coding: utf-8 -*-
"""Вбил ИНН или название — получил всё, что о компании известно. Один читатель поверх готовых CSV.

Задача владельца дословно: «Я вбиваю компанию либо ИНН, и по ней ищется вся информация на
тендерах, контактные лица, новости, и в итоге у меня максимально возможная информация о компании
оказывается».

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ МАЛЕНЬКИЙ МОДУЛЬ, А НЕ ПЕРЕДЕЛКА ДЕВЯТИ БОЛЬШИХ. Разбор всех 127 модулей
показал: 86 из них нельзя запустить по одному ИНН, они работают обходом всей базы. Но за этим
выводом пряталась вторая половина правды: **вся база УЖЕ проиндексирована по ИНН** — колонка `inn`
есть в каждом выходном файле цепочки. Значит вопрос «что мы знаем про эту компанию» не требует
переделки ничего: это чтение шести готовых файлов по ключу, доли секунды.

Переделка модулей нужна для ДРУГОГО вопроса — «вбить НОВЫЙ ИНН, которого в базе нет, и досбрать
по нему данные из источников». Это отдельная работа, и её объём честно назван в карточках модулей.
Здесь же закрывается то, что можно закрыть сегодня.

Что показывает:
  * реквизиты из ЕГРЮЛ и базы владельца: регион, ОКВЭД, статус, директор, выручка, сайт, телефоны;
  * доказательство машины: тип, среда, марки, состояние (есть / покупает / планирует), с цитатой,
    датой, пометкой что это за дата и ссылкой на первоисточник по каждому факту;
  * характеристики машин, разобранные по обозначению серии;
  * ЛЮДЕЙ: имя, должность как в источнике, роль, личный номер и номера предприятия, у каждого
    свой источник и своя ссылка;
  * место в очереди обзвона и приоритет с расшифровкой, почему он такой;
  * если предприятие ОТСЕЯНО — прямо говорит, по какой причине, а не молчит.

Использование:
    python3 karta_kompanii.py 7414003633
    python3 karta_kompanii.py "Магнитогорский металлургический"
    python3 karta_kompanii.py 7414003633 --json          # для встраивания в панель
    python3 karta_kompanii.py --spisok inn.txt --csv karty.csv
"""
import csv
import json
import os
import re
import sys

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
C = os.path.join(L, 'centro')

ISTOCHNIKI = {
    'fakty': os.path.join(L, 'SVOD-tri-sostoyaniya.csv'),
    'predpriyatie': os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv'),
    'ochered': os.path.join(L, 'OCHERED-centrobezhnye.csv'),
    'sreda_neizvestna': os.path.join(L, 'OCHERED-sreda-neizvestna.csv'),
    'otsev_gaz': os.path.join(L, 'OTSEV-gaz.csv'),
    'vitrina': os.path.join(L, 'SVODNAYA-centrobezhnye.csv'),
    'panel': os.path.join(L, 'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv'),
    'harakteristiki': os.path.join(L, 'HARAKTERISTIKI-mashin-po-predpriyatiyam.csv'),
    'egrul': os.path.join(C, 'ochered-egrul.csv'),
}
NASH = {'центробежная', 'центробежная по серии', 'центробежная, вид по слову'}


def chitat(put):
    if not os.path.exists(put):
        return []
    return list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))


def najti_inn(zapros, fakty):
    """ИНН по строке запроса: сам ИНН, либо поиск по названию среди известных предприятий."""
    z = zapros.strip()
    if re.fullmatch(r'\d{10}|\d{12}', z):
        return [z], ''
    slova = [w for w in re.split(r'[\s"«»,\.]+', z.lower()) if len(w) > 3]
    if not slova:
        return [], 'запрос слишком короткий: нужен ИНН или название от четырёх букв'
    nashli = {}
    for x in fakty:
        n = (x.get('predpriyatie') or '').lower()
        if all(w in n for w in slova):
            nashli.setdefault(x['inn'], x.get('predpriyatie') or '')
    if not nashli:
        return [], f'по запросу «{zapros}» в базе ничего не найдено'
    return list(nashli), ''


def karta(inn, dannye):
    """Всё, что известно про один ИНН. Пустое поле означает «у нас этого нет», а не «нет вовсе»."""
    fakty = [x for x in dannye['fakty'] if x.get('inn') == inn]
    p = next((x for x in dannye['predpriyatie'] if x.get('inn') == inn), {})
    eg = next((x for x in dannye['egrul'] if x.get('inn') == inn), {})
    v_ocheredi = next((x for x in dannye['ochered'] if x.get('inn') == inn), None)
    v_sreda_neizv = any(x.get('inn') == inn for x in dannye['sreda_neizvestna'])
    v_gaz = next((x for x in dannye['otsev_gaz'] if x.get('inn') == inn), None)
    vitrina = [x for x in dannye['vitrina'] if x.get('inn') == inn]
    panel = [x for x in dannye['panel'] if x.get('inn') == inn]
    harak = [x for x in dannye['harakteristiki'] if x.get('inn') == inn]

    nashi = [x for x in fakty if x.get('tip_mashiny') in NASH]
    vozdush = [x for x in nashi if str(x.get('sreda_mashiny') or '').startswith('воздух')]

    # люди: собираем из витрины и панели, дедуп по имени, провенанс сохраняем
    lyudi, vid = [], set()
    for x in panel:
        imya = (x.get('chelovek') or '').strip()
        if not imya or imya.lower() in vid:
            continue
        vid.add(imya.lower())
        lyudi.append({'imya': imya, 'dolzhnost': x.get('dolzhnost') or '',
                      'rol': x.get('rol') or '', 'lichnyy_nomer': x.get('lichnyy_nomer') or '',
                      'vid_nomera': x.get('vid_lichnogo') or '',
                      'nomera_predpriyatiya': x.get('nomera_predpriyatiya') or '',
                      'istochnik': x.get('istochnik_cheloveka') or '',
                      'ssylka': x.get('ssylka_na_cheloveka') or ''})
    lyudi.sort(key=lambda c: (0 if c['lichnyy_nomer'] else 1,
                              0 if 'техн' in (c['rol'] or '').lower() else 1))

    sostoyanie = 'в очереди обзвона' if v_ocheredi else (
        'отсеяно: газ или иная среда' if v_gaz else
        'среда не установлена, доузнаётся' if v_sreda_neizv else
        'не в очереди' if nashi else 'центробежная машина не доказана')

    return {
        'inn': inn,
        'predpriyatie': (p.get('predpriyatie') or eg.get('nazvanie_egrul')
                         or (fakty[0].get('predpriyatie') if fakty else '')),
        'sostoyanie_v_rabote': sostoyanie,
        'prioritet': (vitrina[0].get('prioritet') if vitrina else ''),
        'prioritet_pochemu': (vitrina[0].get('prioritet_pochemu') if vitrina else ''),
        'rekvizity': {
            'region': p.get('region') or eg.get('region') or '',
            'okved': p.get('okved') or eg.get('okved') or '',
            'status_egrul': p.get('status_egrul') or eg.get('status') or '',
            'direktor': p.get('direktor') or eg.get('rukovoditel') or '',
            'dolzhnost_direktora': eg.get('dolzhnost') or '',
            'vyruchka_rub': p.get('vyruchka_rub') or '',
            'adres': p.get('adres') or '',
            'sayt': p.get('sayt') or '',
            'telefony_predpriyatiya': p.get('telefony_predpriyatiya') or '',
            'luchshaya_pochta': p.get('luchshaya_pochta') or '',
        },
        'mashina': {
            'faktov_vsego': len(fakty),
            'nashih_centrobezhnyh': len(nashi),
            'vozdushnyh': len(vozdush),
            'tipy': sorted({x.get('tip_mashiny') or '' for x in nashi}),
            'marki': sorted({m.strip() for x in nashi for m in (x.get('marki') or '').split('|')
                             if m.strip()})[:24],
            'srok_sluzhby': p.get('srok_sluzhby') or '',
            'vyvod_ekspertizy': p.get('vyvod_ekspertizy') or '',
        },
        'harakteristiki': [{'marka': h.get('marka'), 'seriya': h.get('seriya'),
                            'chto_eto': h.get('chto_eto'),
                            'proizvoditelnost_m3min': h.get('proizvoditelnost_m3min'),
                            'davlenie': h.get('davlenie'), 'moshchnost': h.get('moshchnost'),
                            'chem_menyaem': h.get('chem_menyaem')} for h in harak],
        'dokazatelstva': [{'sostoyanie': x.get('sostoyanie'), 'tip': x.get('tip_mashiny'),
                           'sreda': x.get('sreda_mashiny'),
                           'kak_uznali_sredu': x.get('sreda_otkuda') or '',
                           'marki': x.get('marki'), 'data': x.get('data'),
                           'chto_za_data': x.get('chto_za_data'),
                           'chem_dokazano': x.get('chem_dokazano'),
                           'citata': (x.get('tekst') or '')[:300],
                           'ssylka': x.get('ssylka'), 'istochnik': x.get('istochnik'),
                           'ogovorka': x.get('ogovorka') or ''}
                          for x in sorted(nashi, key=lambda y: y.get('data') or '', reverse=True)],
        'lyudi': lyudi,
        'chego_ne_hvataet': p.get('chego_ne_hvataet') or '',
    }


def pechat(k):
    r, m = k['rekvizity'], k['mashina']
    print('=' * 92)
    print(f"{k['predpriyatie']}   ИНН {k['inn']}")
    print('=' * 92)
    print(f"  состояние: {k['sostoyanie_v_rabote']}"
          + (f"   приоритет {k['prioritet']}" if k['prioritet'] else ''))
    if k['prioritet_pochemu']:
        print(f"  почему: {k['prioritet_pochemu'][:150]}")
    print()
    print(f"  регион: {r['region'] or '—'}   ОКВЭД: {r['okved'] or '—'}   "
          f"статус: {r['status_egrul'] or '—'}")
    print(f"  директор: {r['direktor'] or '—'} {('(' + r['dolzhnost_direktora'] + ')') if r['dolzhnost_direktora'] else ''}")
    print(f"  выручка: {r['vyruchka_rub'] or '—'}   сайт: {r['sayt'] or '—'}")
    print(f"  телефоны предприятия: {(r['telefony_predpriyatiya'] or '—')[:80]}")
    print(f"  почта: {r['luchshaya_pochta'] or '—'}")
    print()
    print(f"  МАШИНА: фактов всего {m['faktov_vsego']}, наших центробежных {m['nashih_centrobezhnyh']}, "
          f"воздушных {m['vozdushnyh']}")
    if m['tipy']:
        print(f"  типы: {', '.join(m['tipy'])}")
    if m['marki']:
        print(f"  марки: {' | '.join(m['marki'][:14])}")
    if m['srok_sluzhby'] or m['vyvod_ekspertizy']:
        print(f"  срок службы: {m['srok_sluzhby'] or '—'}   вывод экспертизы: {m['vyvod_ekspertizy'] or '—'}")
    if k['harakteristiki']:
        print()
        print('  ХАРАКТЕРИСТИКИ МАШИН:')
        for h in k['harakteristiki'][:8]:
            print(f"    {h['marka']:<20} {(h['chto_eto'] or '')[:34]:<36} "
                  f"{h['proizvoditelnost_m3min'] or ''} {h['davlenie'] or ''} {h['moshchnost'] or ''}")
    if k['lyudi']:
        print()
        print(f"  ЛЮДИ ({len(k['lyudi'])}):")
        for c in k['lyudi'][:20]:
            print(f"    {c['imya'][:26]:<28} {c['dolzhnost'][:32]:<34} "
                  f"{c['lichnyy_nomer'] or c['nomera_predpriyatiya'][:20] or '—'}")
            print(f"      роль: {c['rol'] or '—'}   источник: {c['istochnik'][:40]}")
            if c['ssylka']:
                print(f"      ссылка: {c['ssylka'][:88]}")
    else:
        print()
        print('  ЛЮДИ: никого не знаем')
    print()
    print(f"  ДОКАЗАТЕЛЬСТВА ({len(k['dokazatelstva'])}):")
    for d in k['dokazatelstva'][:12]:
        print(f"    [{d['sostoyanie']:<16}] {d['data'] or '—':<12} {d['tip'][:26]:<28} "
              f"{(d['marki'] or '—')[:22]}")
        print(f"      {d['citata'][:110]}")
        print(f"      основание: {(d['chem_dokazano'] or '—')[:70]}")
        if d['ssylka']:
            print(f"      ссылка: {d['ssylka'][:88]}")
        if d['ogovorka']:
            print(f"      оговорка: {d['ogovorka'][:80]}")
    if len(k['dokazatelstva']) > 12:
        print(f"    …и ещё {len(k['dokazatelstva']) - 12} фактов")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dannye = {k: chitat(v) for k, v in ISTOCHNIKI.items()}
    nety = [k for k, v in dannye.items() if not v]
    if nety:
        print(f'ВНИМАНИЕ: нет данных из {", ".join(nety)} — эти разделы будут пустыми',
              file=sys.stderr)

    zaprosy = []
    if '--spisok' in sys.argv:
        put = sys.argv[sys.argv.index('--spisok') + 1]
        zaprosy = [x.strip() for x in open(put, encoding='utf-8') if x.strip()]
    elif args:
        zaprosy = [' '.join(args)]
    else:
        sys.exit(__doc__)

    karty = []
    for z in zaprosy:
        inny, err = najti_inn(z, dannye['fakty'])
        if err:
            print(err, file=sys.stderr)
            continue
        if len(inny) > 1 and '--spisok' not in sys.argv:
            print(f'по запросу «{z}» найдено {len(inny)} предприятий:', file=sys.stderr)
            for i in inny[:12]:
                nazv = next((x.get('predpriyatie') for x in dannye['fakty']
                             if x.get('inn') == i), '')
                print(f'   {i}  {nazv[:60]}', file=sys.stderr)
            print('уточните ИНН', file=sys.stderr)
            continue
        for i in inny:
            karty.append(karta(i, dannye))

    if '--json' in sys.argv:
        print(json.dumps(karty if len(karty) != 1 else karty[0], ensure_ascii=False, indent=1))
        return
    if '--csv' in sys.argv:
        put = sys.argv[sys.argv.index('--csv') + 1]
        ploskie = []
        for k in karty:
            osnova = {'inn': k['inn'], 'predpriyatie': k['predpriyatie'],
                      'sostoyanie': k['sostoyanie_v_rabote'], 'prioritet': k['prioritet'],
                      **{f'rekv_{a}': b for a, b in k['rekvizity'].items()},
                      'marki': ' | '.join(k['mashina']['marki'][:10]),
                      'faktov_vozdushnyh': k['mashina']['vozdushnyh']}
            if not k['lyudi']:
                ploskie.append({**osnova, 'chelovek': '', 'dolzhnost': '', 'lichnyy_nomer': '',
                                'istochnik_cheloveka': '', 'ssylka_na_cheloveka': ''})
            for c in k['lyudi']:
                ploskie.append({**osnova, 'chelovek': c['imya'], 'dolzhnost': c['dolzhnost'],
                                'lichnyy_nomer': c['lichnyy_nomer'],
                                'istochnik_cheloveka': c['istochnik'],
                                'ssylka_na_cheloveka': c['ssylka']})
        if ploskie:
            with open(put, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(ploskie[0].keys()), delimiter=';',
                                   extrasaction='ignore')
                w.writeheader()
                for r in ploskie:
                    w.writerow(r)
            print(f'карточек {len(karty)}, строк {len(ploskie)} → {put}', file=sys.stderr)
        return
    for k in karty:
        pechat(k)


if __name__ == '__main__':
    main()
