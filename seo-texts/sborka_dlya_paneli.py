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
import re
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
# Люди, разобранные провайдером со страниц «Руководство»/«Контакты» подтверждённых сайтов —
# единственный канал, где рядом с именем стоит должность И прямой телефон. Прогон 03.08:
# 519 страниц → 395 человек, 76 технических, 34 технических с номером, сбоев 0.
LICA_SAJTY = os.path.join(L, 'centro', 'lica-s-sajtov.csv')
# Люди из вложений закупок ЕИС — корпус третьей сессии: 1 355 файлов, 1 083 с текстом,
# 271 человек, из них 134 технических. По моей воздушной очереди резолвится 100 человек на
# 13 предприятиях (60 технических). Пересечение мало и это ожидаемо: их корпус от закупок
# Tender.pro и ЕИС, мой от реестра ЭПБ — источники дополняют друг друга, а не дублируют.
# Честная оговорка первой сессии, которую надо держать в голове: личных мобильных вложения
# почти не дают (один на 678 файлов) — в документах печатают телефон отдела, а не сотовый.
VLOZH = os.path.join(RAB, 'vlozheniya-lica.csv')
# Tender.pro напрямую. НАЙДЕНО ПРОВЕРКОЙ ПО ПУНКТУ 16, и это была самая дорогая потеря: из 554
# человек этого файла с ИНН нашей очереди в панель доезжали 117, а 437 терялись — среди них
# 37 связок «техническая роль + личный мобильный» по 12 предприятиям (Магнезит, главный
# энергетик шахты «Магнезитовая» с мобильным; Химпром Новочебоксарск, шесть человек; Черкизово,
# трое). Причина: люди Tender.pro попадали сюда только через TEHLPR соседней сессии, а там их
# всего 82 строки из 833. Замер каналов показал, что Tender.pro — ЕДИНСТВЕННЫЙ источник с
# настоящим выходом личных мобильных (46-65% людей канала против 0-3% у остальных) и что на нём
# держится 84 из 105 личных номеров проекта. Терять его на склейке было нельзя.
TP_LYUDI = os.path.join(L, 'centro', 'tenderpro', 'tp-lyudi-dlya-obzvona.csv')
# Люди с сайтов со ссылками: 369 с ИНН очереди, доезжали 66. Тот же класс потери.
LICA_SSYL = os.path.join(L, 'centro', 'LICA-S-SAJTOV-SO-SSYLKAMI.csv')
# Сырой разбор карточек Tender.pro. Витрина tp-lyudi-dlya-obzvona.csv строится ИЗ него и уже
# подключена, поэтому почти все эти люди в панели есть. Замер 03.08: из 3 614 строк по ИНН нашей
# очереди новых для панели всего 48, из них с личным мобильным 10. Мало, но десять мобильных
# стоят десяти минут работы, а ИНН достраивается по company_id через tp-inn.csv.
TP_SYROY = os.path.join(L, 'centro', 'tenderpro', 'tp-lica.csv')
TP_INN = os.path.join(L, 'centro', 'tenderpro', 'tp-inn.csv')
KARTA = os.path.join(RAB, 'eis-zakupka-inn-karta.csv')
VYHOD = os.path.join(L, 'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv')

# Нижние границы, ниже которых вход считается битым, а не «просто маленьким».
MINIMUM = {OCHERED: 300, FAKTY: 50000, PRED: 10000, LPR: 500, KONTAKTY: 100,
           VLOZH: 100, KARTA: 20, LICA_SAJTY: 100, TP_LYUDI: 300, LICA_SSYL: 300,
           TP_SYROY: 1000, TP_INN: 100}
NASH = {'центробежная', 'центробежная по серии', 'центробежная, вид по слову'}
SILA = {'покупает': 0, 'планирует': 1, 'есть': 2, 'планировал': 3, 'есть на площадке': 4}


def mobilnyy(tel):
    """Мобильный ли номер. Разбор 03.08 нашёл здесь две ошибки, обе тихие.

    Прежняя проверка снимала только пробелы и дефисы, а СКОБКИ оставляла: у номера
    «+7 (915) 898 24 67» после очистки оставалось «+7(915)8982467», и `lstrip('+78')` упирался в
    открывающую скобку. В `lica-s-sajtov.csv` 132 телефона из 137 записаны со скобками, и из
    девяти настоящих мобильных код признал три.

    Вторая ошибка тоньше и опаснее: `lstrip('+78')` снимает не префикс, а ЛЮБЫЕ символы из
    набора. У пятигорского городского «+7 8792 XX-XX-XX» он проест «+», «7», «8», «7» и упрётся
    в «9» — городской будет объявлен личным мобильным, и продавец позвонит в приёмную, думая,
    что звонит человеку. В нынешних данных таких срабатываний нет, но ловушка стояла.

    Правильный признак российского мобильного: одиннадцать цифр, первая 7 или 8, вторая 9.
    """
    d = re.sub(r'\D', '', tel or '')
    return len(d) == 11 and d[0] in '78' and d[1] == '9'


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
    vlozh = chitat(VLOZH)
    lica_sajty = chitat(LICA_SAJTY)
    tp_lyudi = chitat(TP_LYUDI)
    lica_ssyl = chitat(LICA_SSYL)
    tp_syroy = chitat(TP_SYROY)
    tp_po_cid = {r['company_id']: r.get('inn') or '' for r in chitat(TP_INN)
                 if (r.get('inn') or '').strip()}
    karta = {r['zakupka']: r for r in chitat(KARTA)}

    po_inn = defaultdict(list)
    for x in fakty:
        po_inn[x['inn']].append(x)
    lyudi = defaultdict(list)
    for r in lpr:
        lyudi[r['inn']].append(r)
    kontakty = defaultdict(list)
    for r in kont:
        kontakty[r['inn']].append(r)
    tp_po_inn = defaultdict(list)
    for r in tp_lyudi:
        if (r.get('imya') or '').strip():
            tp_po_inn[r['inn']].append(r)
    syroy_po_inn = defaultdict(list)
    for r in tp_syroy:
        i = (r.get('inn') or '').strip() or tp_po_cid.get((r.get('company_id') or '').strip(), '')
        if i and (r.get('imya') or '').strip():
            syroy_po_inn[i].append(r)
    ssyl_po_inn = defaultdict(list)
    for r in lica_ssyl:
        if (r.get('imya') or '').strip():
            ssyl_po_inn[r['inn']].append(r)
    s_sajtov = defaultdict(list)
    for r in lica_sajty:
        if (r.get('imya') or '').strip():
            s_sajtov[r['inn']].append(r)
    iz_vlozheniy = defaultdict(list)
    for r in vlozh:
        k = karta.get(r['zakupka'])
        if k and (r.get('imya') or '').strip():      # без имени строка для обзвона бесполезна
            iz_vlozheniy[k['inn']].append(r)

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

    # Люди Tender.pro: карточка закупки называет человека, его должность и часто ЛИЧНЫЙ номер.
    # Мобильный распознаётся по коду 9xx после приведения к десяти цифрам; колонка mobilnyy в
    # исходнике это флаг, а не номер, сами номера лежат в telefony.
    def lichnyy_iz(stroka):
        for t in re.split(r'[|,;]', stroka or ''):
            if mobilnyy(t):
                return t.strip()
        return ''

    for i in po_inn_out:
        for c in tp_po_inn.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefony') or '').strip()
            lich = lichnyy_iz(tel)
            out.append({**obraz, 'chelovek': c.get('imya') or '',
                        'dolzhnost': (c.get('dolzhnost') or '')[:70], 'rol': c.get('rol') or '',
                        'lichnyy_nomer': lich,
                        'vid_lichnogo': ('мобильный из карточки закупки' if lich
                                         else 'городской из карточки' if tel else 'номера нет'),
                        'nomera_predpriyatiya': (c.get('telefon_predpriyatiya_ne_lichnyy') or tel)[:70],
                        'istochnik_cheloveka': 'Tender.pro, карточка закупки',
                        'ssylka_na_cheloveka': (c.get('ssylka') or '')[:200],
                        'data_nablyudeniya': (c.get('poslednyaya_data') or '')[:10],
                        'chego_ne_hvataet': '' if lich else ('личного номера' if tel else 'номера вовсе')})
        for c in ssyl_po_inn.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefon') or '').strip()
            lich = lichnyy_iz(tel)
            out.append({**obraz, 'chelovek': c.get('imya') or '',
                        'dolzhnost': (c.get('dolzhnost') or '')[:70], 'rol': c.get('rol') or '',
                        'lichnyy_nomer': lich,
                        'vid_lichnogo': ('мобильный со страницы' if lich
                                         else 'прямой городской' if tel else 'номера нет'),
                        'nomera_predpriyatiya': tel[:70],
                        'istochnik_cheloveka': (c.get('istochnik') or 'страница сайта')[:60],
                        'ssylka_na_cheloveka': (c.get('ssylka') or c.get('sajt') or '')[:200],
                        'data_nablyudeniya': '',
                        'chego_ne_hvataet': '' if tel else 'номера'})

    # Дедуп по фамилии: витрина Tender.pro уже подключена, и без этого те же люди задвоятся.
    uzhe = {(r['inn'], (r.get('chelovek') or '').split()[0].lower())
            for r in out if (r.get('chelovek') or '').strip()}
    for i in po_inn_out:
        for c in syroy_po_inn.get(i, []):
            imya = (c.get('imya') or '').strip()
            if not imya or (i, imya.split()[0].lower()) in uzhe:
                continue
            uzhe.add((i, imya.split()[0].lower()))
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefon') or '').strip()
            out.append({**obraz, 'chelovek': imya,
                        'dolzhnost': (c.get('dolzhnost') or '')[:70], 'rol': c.get('rol') or '',
                        'lichnyy_nomer': tel if mobilnyy(tel) else '',
                        'vid_lichnogo': ('мобильный из карточки закупки' if mobilnyy(tel)
                                         else 'городской из карточки' if tel else 'номера нет'),
                        'nomera_predpriyatiya': tel[:70],
                        'istochnik_cheloveka': 'Tender.pro, карточка закупки (сырой разбор)',
                        'ssylka_na_cheloveka':
                            f"https://www.tender.pro/api/tender/{c.get('tender_id')}/view_public",
                        'data_nablyudeniya': (c.get('sozdan') or '')[:10],
                        'chego_ne_hvataet': '' if tel else 'номера'})
    # Люди со страниц сайтов: должность и прямой телефон со страницы-источника.
    for i in po_inn_out:
        for c in s_sajtov.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefon') or '').strip()
            lichnyy = tel if mobilnyy(tel) else ''
            out.append({**obraz, 'chelovek': c.get('imya') or '',
                        'dolzhnost': (c.get('dolzhnost') or '')[:70], 'rol': c.get('rol') or '',
                        'lichnyy_nomer': lichnyy,
                        'vid_lichnogo': ('мобильный со страницы' if lichnyy else
                                         'прямой городской' if tel else 'номера нет'),
                        'nomera_predpriyatiya': tel[:70],
                        'istochnik_cheloveka': 'страница сайта, разбор провайдером',
                        'ssylka_na_cheloveka': (c.get('sajt') or '')[:200],
                        'data_nablyudeniya': '',
                        'chego_ne_hvataet': '' if tel else 'номера'})

    # Люди из вложений закупок: имя и должность есть, личного мобильного почти никогда нет.
    for i in po_inn_out:
        for c in iz_vlozheniy.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            out.append({**obraz, 'chelovek': c.get('imya') or '',
                        'dolzhnost': (c.get('dolzhnost') or '')[:70], 'rol': c.get('rol') or '',
                        'lichnyy_nomer': '', 'vid_lichnogo': 'из вложения закупки',
                        'nomera_predpriyatiya': (c.get('telefon') or '')[:70],
                        'istochnik_cheloveka': f"вложение закупки ЕИС {c.get('zakupka','')}",
                        'ssylka_na_cheloveka': '', 'data_nablyudeniya': '',
                        'chego_ne_hvataet': ('личного номера' if c.get('telefon')
                                             else 'номера вовсе')})

    # СВЕДЕНИЕ ОДНОГО ЧЕЛОВЕКА, ПРИШЕДШЕГО НЕСКОЛЬКИМИ ПУТЯМИ.
    # Правило владельца: «провенанс накапливать, а не заменять». Если человек найден и у меня, и
    # у соседа, в записи должны стоять ОБА источника и их число, а не последний победивший.
    # Замер до сведения: 1 837 строк с человеком, уникальных по (ИНН, фамилия) 1 470, то есть
    # 295 ключей приходят дважды и чаще. Пример: Степанов на одном предприятии лежал четырьмя
    # строками — «tender.pro» от соседа, «people; Тендер.Про» от него же и две мои «карточка
    # закупки». Продавец видел четырёх Степановых и не понимал, кому звонить.
    # Сводим в одну строку, выбирая лучшее значение каждого поля отдельно: личный номер важнее
    # пустого, названная должность важнее пустой, а источники складываются через запятую.
    svedeno, po_cheloveku = [], {}
    for r in out:
        imya = (r.get('chelovek') or '').strip()
        if not imya:
            svedeno.append(r)
            continue
        klyuch = (r['inn'], imya.split()[0].lower(), (r.get('lichnyy_nomer') or '').strip())
        # ключ включает личный номер: два РАЗНЫХ номера у одной фамилии это два разных
        # наблюдения, и склеивать их нельзя — можно потерять живой номер
        if klyuch not in po_cheloveku:
            r = dict(r)
            r['istochnikov_cheloveka'] = '1'
            po_cheloveku[klyuch] = r
            svedeno.append(r)
            continue
        b = po_cheloveku[klyuch]
        for pole in ('dolzhnost', 'rol', 'lichnyy_nomer', 'nomera_predpriyatiya',
                     'vid_lichnogo', 'data_nablyudeniya'):
            if not (b.get(pole) or '').strip() and (r.get(pole) or '').strip():
                b[pole] = r[pole]
        for pole in ('istochnik_cheloveka', 'ssylka_na_cheloveka'):
            bylo = [x for x in (b.get(pole) or '').split(' | ') if x.strip()]
            novoe = (r.get(pole) or '').strip()
            if novoe and novoe not in bylo:
                b[pole] = ' | '.join(bylo + [novoe])[:400]
        b['istochnikov_cheloveka'] = str(int(b.get('istochnikov_cheloveka') or 1) + 1)
        # чем полнее имя, тем лучше: «Степанов С. В.» уступает «Степанов Сергей Владимирович»
        if len(imya) > len(b.get('chelovek') or ''):
            b['chelovek'] = imya
    out = svedeno

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        polya = list(out[0].keys())
        if 'istochnikov_cheloveka' not in polya:
            polya.append('istochnikov_cheloveka')
        w = csv.DictWriter(fh, fieldnames=polya, delimiter=';', extrasaction='ignore')
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
