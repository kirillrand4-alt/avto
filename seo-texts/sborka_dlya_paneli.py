# -*- coding: utf-8 -*-
"""Итоговый файл для панели обзвона: воздушные центробежники + все их ЛПР.

Пункт 14 владельца: «заливаем все данные в панель для продажников, сообщаем друг другу какие
данные есть, перепроверяем друг за другом и вливаем». Этот файл — то, что вливаю я.

Собирается из трёх источников:
  OCHERED-centrobezhnye.csv          — предприятия, где доказана ВОЗДУШНАЯ центробежная машина;
  SVOD-tri-sostoyaniya.csv           — сами факты с цитатой, датой и ссылкой на первоисточник;
  TEHLPR-VSE-s-provenansom.csv       — люди от соседней сессии, с провенансом.

ПОЧЕМУ ЗДЕСЬ ЖЁСТКАЯ ПРОВЕРКА ВХОДОВ. Первая сборка этого файла после перезапуска контейнера
дала «людей 0» вместо 448 и не сказала ни слова: файл соседей лежал во временном каталоге,
каталог стёрло вместе с контейнером, а сборщик проверял `os.path.exists` и молча шёл дальше.
Ноль выглядел как ответ. Теперь отсутствие или усыхание любого входа — это остановка с
сообщением, а не тихий пропуск.

Использование:
    python3 sborka_dlya_paneli.py
"""
import csv
import os
import subprocess
import sys
from collections import Counter, defaultdict

csv.field_size_limit(10 ** 7)
BAZA = os.path.dirname(os.path.abspath(__file__))
L = os.path.join(BAZA, 'engineers-lens')
RAB = '/tmp/claude-0/-home-user-avto/520847fd-7699-5483-869b-cf6d49851f67/scratchpad'
OCHERED = os.path.join(L, 'OCHERED-centrobezhnye.csv')
FAKTY = os.path.join(L, 'SVOD-tri-sostoyaniya.csv')
PRED = os.path.join(L, 'SVOD-POLNYY-po-predpriyatiyam.csv')
LPR = os.path.join(RAB, 'TEHLPR-VSE-s-provenansom.csv')
# Контакты с обхода сайтов третьей сессии: 700 строк, каждая с видом и ссылкой на страницу.
# По моей воздушной очереди попадают 443 контакта на 37 предприятий, и у 31 из них телефона
# не было вовсе — это прямой удар по узкому месту, поэтому источник обязательный.
KONTAKTY = os.path.join(RAB, 'OBHOD-kontakty-3s.csv')
VYHOD = os.path.join(L, 'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv')

# Нижние границы, ниже которых вход считается битым, а не «просто маленьким».
MINIMUM = {OCHERED: 300, FAKTY: 50000, PRED: 10000, LPR: 500, KONTAKTY: 100}
NASH = {'центробежная', 'центробежная по серии'}
SILA = {'покупает': 0, 'планирует': 1, 'есть': 2, 'планировал': 3, 'есть на площадке': 4}


def chitat(put):
    """Прочитать вход и убедиться, что он на месте и не усох."""
    if not os.path.exists(put):
        sys.exit(f'ОСТАНОВКА: нет входного файла {put}.\n'
                 f'  Скачайте его с дропа: bash server/drop_client.sh down {os.path.basename(put)}\n'
                 f'  Собирать без него нельзя: получится тихий ноль вместо данных.')
    rows = list(csv.DictReader(open(put, encoding='utf-8-sig'), delimiter=';'))
    porog = MINIMUM.get(put, 1)
    if len(rows) < porog:
        sys.exit(f'ОСТАНОВКА: в {os.path.basename(put)} всего {len(rows)} строк, ожидалось '
                 f'не меньше {porog}. Похоже, файл обрезан или скачался не полностью.')
    return rows


def main():
    och = chitat(OCHERED)
    fakty = chitat(FAKTY)
    pred = {r['inn']: r for r in chitat(PRED)}
    lpr = chitat(LPR)
    kont = chitat(KONTAKTY)

    po_inn = defaultdict(list)
    for x in fakty:
        po_inn[x['inn']].append(x)
    lyudi = defaultdict(list)
    for r in lpr:
        lyudi[r['inn']].append(r)
    kontakty = defaultdict(list)
    for r in kont:
        kontakty[r['inn']].append(r)

    out = []
    for p_ in och:
        i = p_['inn']
        p = pred.get(i) or {}
        v = [x for x in po_inn.get(i, [])
             if x['tip_mashiny'] in NASH and str(x['sreda_mashiny']).startswith('воздух')]
        v.sort(key=lambda x: (SILA.get(x['sostoyanie'], 9), x.get('data') or ''))
        x = v[0] if v else {}
        ob = {'inn': i, 'predpriyatie': p_.get('predpriyatie') or '', 'region': p.get('region') or '',
              'sostoyanie': x.get('sostoyanie') or '', 'tip_mashiny': x.get('tip_mashiny') or '',
              'sreda': x.get('sreda_mashiny') or '',
              'kak_uznali_sredu': x.get('sreda_otkuda') or 'сказано прямо в тексте',
              'marki': (x.get('marki') or '')[:70], 'data_fakta': x.get('data') or '',
              'chto_za_data': x.get('chto_za_data') or '',
              'chem_dokazano': (x.get('chem_dokazano') or '')[:170],
              'citata': (x.get('tekst') or '')[:260], 'ssylka_na_istochnik': x.get('ssylka') or '',
              'istochnik': x.get('istochnik') or '', 'ogovorka': x.get('ogovorka') or '',
              'srok_sluzhby': p.get('srok_sluzhby') or '',
              'vyvod_ekspertizy': p.get('vyvod_ekspertizy') or '', 'sayt': p.get('sayt') or '',
              'telefony_predpriyatiya': (p.get('telefony_predpriyatiya') or '')[:70],
              'faktov_vozdushnyh': len(v)}
        spisok = lyudi.get(i) or []
        if not spisok:
            out.append({**ob, 'chelovek': '', 'dolzhnost': '', 'rol': '', 'lichnyy_nomer': '',
                        'vid_lichnogo': '', 'nomera_predpriyatiya': '', 'istochnik_cheloveka': '',
                        'ssylka_na_cheloveka': '', 'data_nablyudeniya': '',
                        'chego_ne_hvataet': 'человека нет'})
            continue
        for c in spisok:
            net = ([] if c.get('lichnyy_nomer')
                   else (['личного номера'] if c.get('nomera_predpriyatiya') else ['номера вовсе']))
            out.append({**ob, 'chelovek': c.get('fio') or '',
                        'dolzhnost': (c.get('dolzhnost_kak_v_istochnike') or '')[:70],
                        'rol': c.get('rol') or '', 'lichnyy_nomer': c.get('lichnyy_nomer') or '',
                        'vid_lichnogo': c.get('vid_lichnogo') or '',
                        'nomera_predpriyatiya': (c.get('nomera_predpriyatiya') or '')[:70],
                        'istochnik_cheloveka': c.get('istochnik') or '',
                        'ssylka_na_cheloveka': c.get('ssylka_na_istochnik') or '',
                        'data_nablyudeniya': c.get('data_nablyudeniya') or '',
                        'chego_ne_hvataet': ', '.join(net)})

    # Контакты без имени идут отдельными строками с пометкой вида — правило владельца:
    # номер приёмной звонить можно, но продавец обязан видеть, что это приёмная, а не человек.
    po_inn_out = {r['inn'] for r in out}
    for i in po_inn_out:
        for c in kontakty.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            out.append({**{k: v for k, v in obraz.items()},
                        'chelovek': c.get('chelovek') or '', 'dolzhnost': '', 'rol': '',
                        'lichnyy_nomer': c.get('kontakt') if c.get('vid') == 'мобильный' else '',
                        'vid_lichnogo': c.get('vid') or '',
                        'nomera_predpriyatiya': c.get('kontakt') or '',
                        'istochnik_cheloveka': (c.get('istochnik') or 'обход сайта, 3-я сессия'),
                        'ssylka_na_cheloveka': c.get('ssylka') or '',
                        'data_nablyudeniya': '',
                        'chego_ne_hvataet': f"контакт без имени: {c.get('vid') or ''}"})

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()), delimiter=';',
                           extrasaction='ignore')
        w.writeheader()
        for r in out:
            w.writerow(r)

    # --- числа ИЗ ЗАПИСАННОГО ФАЙЛА, и проверка, что людей не потеряли ---
    pr = list(csv.DictReader(open(VYHOD, encoding='utf-8-sig'), delimiter=';'))
    s_chelovekom = {r['inn'] for r in pr if r['chelovek']}
    if not s_chelovekom:
        sys.exit(f'ОСТАНОВКА: в готовом файле НОЛЬ людей при {len(lpr)} строках на входе. '
                 f'Значит ИНН не сошлись — файл на дроп не выкладываю.')
    print(f'строк {len(pr)}, предприятий {len({r["inn"] for r in pr})}')
    print(f'  людей {sum(1 for r in pr if r["chelovek"])} на {len(s_chelovekom)} предприятиях')
    print(f'  с личным номером {sum(1 for r in pr if r["lichnyy_nomer"])}')
    print(f'  с телефоном предприятия {len({r["inn"] for r in pr if r["telefony_predpriyatiya"]})}')
    print('  состояния:', dict(Counter(r['sostoyanie'] for r in pr).most_common()))
    subprocess.run(['bash', os.path.join(BAZA, 'server', 'drop_client.sh'), 'up', VYHOD],
                   capture_output=True, timeout=900)
    print(f'выложено на дроп → {os.path.basename(VYHOD)}')


if __name__ == '__main__':
    main()
