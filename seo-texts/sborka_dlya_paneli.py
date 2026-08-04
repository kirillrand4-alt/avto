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
# Контактные лица закупок ТЭК-Торга. Файл лежал в сборе с самого начала и читался ТОЛЬКО как
# перечень организаций: имя, телефон и почта из него в панель не попадали никогда — ни одна
# строка кода, кроме `svod_tri_sostoyaniya.py`, этот файл не открывала. Замер 03.08: 253
# контакта, 113 из них на предприятиях моей очереди, 12 с личным мобильным (8 разных людей).
# Оговорка, которую продавец должен видеть: это контакт ЗАКУПКИ, чаще всего специалист отдела
# снабжения, а не главный энергетик. Роль не назначаю — пусть её назначит общий разборщик
# должностей, как всем остальным.
TEKTORG_LICA = os.path.join(L, 'centro', 'tektorg-kontakty-centro.csv')
# ЛЮДИ С КАРТОЧЕК ЗАКУПОК — самый крупный источник телефонов, какой у нас есть, и до 04.08
# он в панель НЕ ВЛИВАЛСЯ ВОВСЕ: 1 029 человек и 88 личных мобильных лежали в файлах мимо
# сборки. Нашлось при осмотре панели глазами по просьбе владельца.
# Замер отдачи по площадкам (выборка равномерно по предприятиям): ЭТП ГПБ 16 % карточек несут
# личный мобильный, Росэлторг 7 %, Портал 4 %. Должности площадки не публикуют ни одна.
LICA_KARTOCHEK = [
    (os.path.join(L, 'centro', 'etpgpb-lica-s-kartochek.csv'), 'ЭТП ГПБ'),
    (os.path.join(L, 'centro', 'roseltorg-lica-s-kartochek.csv'), 'Росэлторг'),
    (os.path.join(L, 'centro', 'tektorg-lica-s-kartochek.csv'), 'ТЭК-Торг'),
    (os.path.join(L, 'centro', 'portal-lica-s-kartochek.csv'), 'Портал Москвы'),
    (os.path.join(L, 'centro', 'rts-lica-s-kartochek.csv'), 'РТС-тендер'),
    (os.path.join(L, 'centro', 'rts-lica-iz-slovarnogo.csv'), 'РТС-тендер, словарный обход'),
]
OBRATNYY = os.path.join(L, 'centro', 'DLYA-VSEH-3s-OBRATNYY-HOD-NOMERA.csv')
KARTA = os.path.join(RAB, 'eis-zakupka-inn-karta.csv')
VYHOD = os.path.join(L, 'VOZDUSHNYE-CENTROBEZHNIKI-s-LPR.csv')

# Нижние границы, ниже которых вход считается битым, а не «просто маленьким».
MINIMUM = {OCHERED: 300, FAKTY: 50000, PRED: 10000, LPR: 500, KONTAKTY: 100,
           VLOZH: 100, KARTA: 20, LICA_SAJTY: 100, TP_LYUDI: 300, LICA_SSYL: 300,
           TP_SYROY: 1000, TP_INN: 100, TEKTORG_LICA: 100}
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
    # ДЕСЯТЬ ЗНАКОВ БЕЗ ПРЕФИКСА — тоже мобильный, и это найдено проверкой первой сессии.
    # Соседние своды хранят номер как `9022045044`, без ведущей 7/8. Требование ровно
    # одиннадцати знаков отвергало 78 НАСТОЯЩИХ мобильных, то есть главная мера была
    # ЗАНИЖЕНА. Городской в десять знаков начинается не с девятки (`8352304224` —
    # чебоксарский код 8352), поэтому признак «первая цифра 9» их не пускает.
    if len(d) == 10:
        return d[0] == '9'
    return len(d) == 11 and d[0] in '78' and d[1] == '9'


# ТЕХНИЧЕСКИЕ РОЛИ. Один канон на весь модуль: до этого «технический ли человек» считалось
# по-разному в замерах и в сборке, и числа расходились.
TEHNICHESKAYA = re.compile(r'энергетик|механик|технич|главн\w+ инженер|КИП|АСУ|эксплуатац', re.I)


def chto_delat(stroka):
    """Что продавцу делать с этой строкой ПРЯМО СЕЙЧАС. Отдельная колонка, а не догадка по
    пустым полям.

    Поставлено по замеру первой сессии: «мы полгода ищем имена, а имена в основном уже есть,
    не хватает телефона к известному человеку». На моих данных дыра другая по размеру (564
    предприятия без человека против 98 с именем и без номера), но их довод верен в другом:
    **98 закрываются дешевле всех прочих**, потому что искать надо не кого-то, а НАЗВАННОГО
    человека, и у 308 строк из 409 телефон предприятия УЖЕ есть.

    Без этой колонки такая строка читается как «звонить некому»: имя стоит, а поле личного
    номера пусто, и продавец проходит мимо готовой цели. Приёмная плюс фамилия — это один
    звонок, а не поиск.
    """
    chelovek = (stroka.get('chelovek') or '').strip()
    lichnyy = (stroka.get('lichnyy_nomer') or '').strip()
    obshchiy = (stroka.get('nomera_predpriyatiya') or '').strip()
    teh = bool(TEHNICHESKAYA.search((stroka.get('dolzhnost') or '') + ' '
                                    + (stroka.get('rol') or '')))
    if lichnyy:
        return 'звонить напрямую' + (' — ТЕХНИЧЕСКИЙ' if teh else '')
    if chelovek and obshchiy:
        return ('СПРОСИТЬ ПО ФАМИЛИИ в приёмной — технический'
                if teh else 'спросить по фамилии в приёмной')
    if chelovek:
        return 'человек известен, номера нет вовсе — искать номер по фамилии'
    if obshchiy:
        return 'только приёмная, имени нет — спрашивать главного энергетика'
    return 'ни человека, ни номера'


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


# Садовая воздуходувка называется тем же словом, что промышленная, и приезжала в факты как
# доказательство воздушной машины. В фиде это выглядело так: у ООО «Газпром бурение»
# доказательством стояло «Бензопилы и воздуходувки», у ГБУЗ ККБ № 2 — «Поставка садового
# оборудования (воздуходувка, бензопила)». Из такого не следует, что на предприятии есть
# центробежник, — а это ровно определение мусора, данное владельцем.
#
# Заслон нарочно узкий: ловим не слово «воздуходувка», а её СОСЕДЕЙ по предмету — бензопилу,
# триммер, мотокосу, ранцевое исполнение, марки садового инструмента. Широкий вариант
# («воздуходувка без слова „промышленная"») выкинул бы и настоящие закупки.
SADOVAYA = re.compile(
    r'бензинов|бензокос|бензотрим|бензопил|триммер|мотокос|газонокосилк|садов\w*\s*оборуд|'
    r'ранцев|husqvarna|stihl|makita|patriot|снегоуборщ|воздуходувк\w*-измельчител|'
    r'мойк\w* высокого давления|высоторез|мотопомп', re.I)


def sadovyy_inventar(x):
    """Факт про садовый инструмент, а не про машину предприятия."""
    t = (x.get('tekst') or x.get('citata') or '')
    return bool(SADOVAYA.search(t)) and 'воздуходув' in t.lower()


# «А.В. Чугайнов» вместо «Чугайнов А.В.» — так подписывают документы, и так оно приезжает
# с карточек и вложений. Выглядит мелочью, а ломает главное: везде, где мы сшиваем людей,
# ключом стоит ПЕРВОЕ СЛОВО имени. У такой записи первое слово — «А.В.», то есть:
#   * один человек живёт двумя записями и не склеивается;
#   * правило 1-й сессии «ИНН + фамилия» по нему не работает;
#   * продавец не может спросить «А.В.» у секретаря.
# Класс нашла 3-я сессия у себя (913 записей) — проверил у себя, нашлось 117, и почти все
# технические: техдиректор, главный инженер, главный механик.
INICIALY_VPEREDI = re.compile(
    r'^\s*((?:[А-ЯЁ]\.\s*){1,2})([А-ЯЁ][а-яё\-]{2,}(?:\s+[А-ЯЁ][а-яё]+){0,2})\s*$')


def imya_v_poryadok(imya):
    """«А.В. Чугайнов» → «Чугайнов А.В.». Не трогает всё остальное."""
    m = INICIALY_VPEREDI.match((imya or '').strip())
    if not m:
        return (imya or '').strip()
    inic = re.sub(r'\s+', '', m.group(1))
    return m.group(2).strip() + ' ' + inic


# Дом культуры, МФЦ, поликлиника, администрация района — воздушного центробежника у них нет.
# Владелец показал карточку МАУК «ЦКИ» города Кашира: ОКВЭД 90.04.3 «клубы, дворцы и дома
# культуры», важность 750, состояние «покупает». Доказательство — мой факт с Портала Москвы
# «Приобретение воздуходувки», то есть почти наверняка садовая, для парка.
#
# ОТВЕТ НА ВОПРОС «мы же отсекали таких, кто вернул»: НИКТО не возвращал. Их отсекали РУКАМИ,
# карточка за карточкой (1-я сессия скрыла 216, из них 6 «культура и спорт»), а правила не
# было — и мой конвейер подавал их заново при каждой пересборке. Ручная чистка против
# автоматической подачи всегда проигрывает.
#
# Заслон требует ДВУХ признаков сразу: непроизводственное название И ни одной марки машины.
# Одного названия мало: у МГУ стоит ТВ80-1.4, у ГБУЗ ККБ № 2 — C15L, у «Псковавтодора» —
# AB 100/515; это настоящие машины в котельных и на очистных, и выкидывать их нельзя.
NEPROIZVODSTVO = re.compile(
    r'\bМАУК\b|\bМБУК\b|\bГБУК\b|\bМАУ\b|\bМБУ\b|\bГБУ\b(?!З)|\bГАУК\b|\bГАУ\b|дом(?:а)? культур|'
    r'дворец культур|центр культур|библиотек|музе[йя]|театр|филармони|цирк|парк культур|'
    r'\bГБУЗ\b|\bГАУЗ\b|\bМБУЗ\b|больниц|поликлин|госпитал|диспансер|'
    r'школ|лице[йя]|гимнази|детск\w+ сад|\bДОУ\b|\bСОШ\b|институт культур|колледж|'
    r'\bМФЦ\b|многофункциональн\w+ центр|администраци|комитет|'
    r'спортивн|стадион|бассейн|физкультур|\bДЮСШ\b|санатори|турист', re.I)


def neproizvodstvo(p):
    return bool(NEPROIZVODSTVO.search(p.get('predpriyatie') or '')) \
        and not (p.get('marki') or '').strip()


def main():
    och = chitat(OCHERED)
    nepr = [p for p in och if neproizvodstvo(p)]
    if nepr:
        och = [p for p in och if not neproizvodstvo(p)]
        print(f'  ОТСЕВ НЕПРОИЗВОДСТВА: {len(nepr)} предприятий — дома культуры, МФЦ, '
              f'поликлиники, администрации без единой марки машины '
              f'({", ".join(p["predpriyatie"][:22] for p in nepr[:4])}…)', file=sys.stderr)
    fakty = chitat(FAKTY)
    sadovyh = [x for x in fakty if sadovyy_inventar(x)]
    if sadovyh:
        fakty = [x for x in fakty if not sadovyy_inventar(x)]
        print(f'  ОТСЕВ САДОВОГО: фактов {len(sadovyh)} на '
              f'{len({x["inn"] for x in sadovyh})} предприятиях — бензопилы и триммеры рядом '
              f'с «воздуходувкой»', file=sys.stderr)
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

    # ОДНА ПРОЦЕДУРА — ОДИН ФАКТ. Владелец показал карточку, где закупка ГП130612 стоит
    # ДВАЖДЫ: у одной записи «марка TA-6000, тип не установлен (марка не опознана)», у другой
    # «марка TA-6000, тип центробежная». Источники — «ЭТП ГПБ» и «ЭТП ГПБ, поиск по словам»,
    # то есть оба МОИ: обход по компаниям и обход по словам нашли одну и ту же процедуру.
    # Продавец видит два доказательства там, где документ один, а счётчик «Фактов» врёт.
    #
    # Склеиваем по (ИНН + номер процедуры), оставляя ЛУЧШУЮ запись: у которой назван тип,
    # потом марка, потом среда. Источники складываем — провенанс накапливается, а не
    # заменяется (правило владельца).
    NOMER_PROC = re.compile(r'(?:процедура|№)\s*([A-ZА-Я]{0,3}\d{5,})', re.I)

    def sila_fakta(x):
        t = (x.get('tipy_mashin') or x.get('tip') or '')
        return (0 if 'не установлен' in t or not t.strip() else 1,
                1 if (x.get('marki') or '').strip() else 0,
                1 if (x.get('sreda') or '').strip() else 0)

    po_proc, prochie, sklejeno = {}, [], 0
    for x in fakty:
        m = NOMER_PROC.search(x.get('chem_dokazano') or '')
        if not m:
            prochie.append(x)
            continue
        k = (x['inn'], m.group(1))
        if k not in po_proc:
            po_proc[k] = x
            continue
        sklejeno += 1
        luchshiy = max(po_proc[k], x, key=sila_fakta)
        drugoy = x if luchshiy is po_proc[k] else po_proc[k]
        ist = [s for s in (luchshiy.get('istochnik') or '').split(' | ') if s.strip()]
        d_ist = (drugoy.get('istochnik') or '').strip()
        if d_ist and d_ist not in ist:
            luchshiy['istochnik'] = ' | '.join(ist + [d_ist])[:120]
        po_proc[k] = luchshiy
    if sklejeno:
        fakty = list(po_proc.values()) + prochie
        print(f'  СКЛЕЙКА ДУБЛЕЙ ПРОЦЕДУР: {sklejeno} лишних записей о тех же закупках убрано',
              file=sys.stderr)

    po_inn = defaultdict(list)
    for x in fakty:
        po_inn[x['inn']].append(x)
    # Считаем машины со сроком по САМИМ ФАКТАМ, а не по свёрнутой строке предприятия: в
    # свёртке значения склеены через «|» и число теряется.
    istekshie, istekayut = Counter(), Counter()
    for x in fakty:
        srok = (x.get('srok_sluzhby') or '').upper()
        if 'ИСТЁК' in srok or 'ИСТЕК' in srok:
            istekshie[x['inn']] += 1
        elif 'ИСТЕКАЕТ' in srok:
            istekayut[x['inn']] += 1
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
    tektorg = defaultdict(list)
    for r in chitat(TEKTORG_LICA):
        # ИНН у ТЭК-Торга бывает с хвостом состояния: «3801009466_del» — организация выведена
        # из словаря площадки. Хвост срезаем, сам факт «ликвидирована» на человека не влияет:
        # телефон и почта у него от этого не пропадают, а видно это будет по базе ЕГРЮЛ.
        m = re.fullmatch(r'(\d{10}|\d{12})(?:_\w+)?', (r.get('inn_organizatora') or '').strip())
        if m and (r.get('kontaktnoe_lico') or '').strip():
            tektorg[m.group(1)].append(r)
    s_kartochek = defaultdict(list)
    for put_f, imya_pl in LICA_KARTOCHEK:
        for r in chitat(put_f):
            i_ = (r.get('inn') or '').strip()
            fio_ = (r.get('chelovek') or r.get('imya') or '').strip()
            if i_ and fio_:
                s_kartochek[i_].append(dict(r, _ploshchadka=imya_pl))

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
              # СКОЛЬКО МАШИН С ИСТЁКШЕЙ ЭКСПЕРТИЗОЙ. Сильнейший повод для звонка, какой у нас
              # есть, и он всё это время лежал нечитаемым: колонка срока показывала склейку
              # «any | срок ИСТЁК | срок действует», где «any» — мусорное значение статуса из
              # выгрузки, а ЧИСЛА машин не было вовсе. Продавец не видел, что у НАК «Азот»
              # просрочено 105 машин, а у НЛМК 88.
              # Закупка говорит «они покупали». Истёкшая экспертиза говорит «машина стоит
              # СЕЙЧАС, и решение по ней принимает главный инженер» — тот самый человек,
              # которого мы ищем. Формулировка третьей сессии, замер мой: по моей базе таких
              # предприятий в очереди 173.
              'mashin_ekspertiza_istekla': istekshie.get(i, 0),
              'mashin_ekspertiza_istekaet': istekayut.get(i, 0),
              'vyvod_ekspertizy': p.get('vyvod_ekspertizy') or '', 'sayt': p.get('sayt') or '',
              'telefony_predpriyatiya': (p.get('telefony_predpriyatiya') or '')[:70],
              'faktov_vozdushnyh': len(v), 'pochta': '', 'chto_delat': ''}
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

    # Контактные лица закупок ТЭК-Торга. Единственный источник, где рядом с именем стоит и
    # телефон, и рабочая почта на домене предприятия — почта пригодится, даже когда номер
    # окажется общим. Ставится ПОСЛЕ витрин намеренно: порядок уже стоил нам 456 задвоенных
    # строк, когда сырой источник Tender.pro встал перед своей же витриной.
    for i in po_inn_out:
        for c in tektorg.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefony') or '').strip()
            lich = lichnyy_iz(tel)
            out.append({**obraz, 'chelovek': (c.get('kontaktnoe_lico') or '').strip(),
                        'dolzhnost': '', 'rol': '',
                        'lichnyy_nomer': lich,
                        'vid_lichnogo': ('мобильный из карточки закупки' if lich
                                         else 'городской из карточки' if tel else 'номера нет'),
                        'nomera_predpriyatiya': tel[:70],
                        'istochnik_cheloveka': 'ТЭК-Торг, контактное лицо закупки',
                        'ssylka_na_cheloveka': (c.get('ssylka') or '')[:200],
                        'data_nablyudeniya': (c.get('data_publikacii') or '')[:10],
                        'chego_ne_hvataet': ', '.join(
                            ([] if lich else ['личного номера'] if tel else ['номера вовсе'])
                            + ['должности']),
                        'pochta': (c.get('pochty') or '').strip()[:80]})

        for c in s_kartochek.get(i, []):
            obraz = next(r for r in out if r['inn'] == i)
            tel = (c.get('telefon') or '').strip()
            lich = lichnyy_iz(tel)
            dob = (c.get('dobavochnyy') or '').strip()
            rol_ = (c.get('rol') or '').strip()
            # ДОЛЖНОСТЬ ЭТИХ ЛЮДЕЙ НЕ ДАЁТ НИ ОДНА ПЛОЩАДКА (перебраны все 92 поля карточки
            # ЭТП ГПБ — полей вида position/post нет вовсе). Пустая должность стоит дорого:
            # панель прячет людей без роли за складку, и продавец их не видит.
            # Поэтому ставим то, что ДОКАЗАНО карточкой, и ничего сверх: человек указан
            # контактным лицом закупки. Это не догадка о его месте в заводской иерархии —
            # это его роль в этой закупке, подтверждённая первоисточником по ссылке рядом.
            # Технической роль НЕ становится: в меру владельца («технический ЛПР с личным
            # мобильным») такие люди по-прежнему не идут, и это правильно.
            dolzh_ = (c.get('dolzhnost') or '').strip() or 'контактное лицо закупки'
            if not rol_ and not (c.get('dolzhnost') or '').strip():
                rol_ = 'закупки'
            out.append({**obraz, 'chelovek': (c.get('chelovek') or c.get('imya') or '').strip(),
                        'dolzhnost': dolzh_, 'rol': rol_,
                        'lichnyy_nomer': lich,
                        'vid_lichnogo': ('мобильный из карточки закупки' if lich
                                         else 'городской из карточки' if tel else 'номера нет'),
                        'nomera_predpriyatiya': tel[:70],
                        'istochnik_cheloveka': c['_ploshchadka'] + ', контактное лицо закупки',
                        'ssylka_na_cheloveka': (c.get('ssylka') or '')[:200],
                        'data_nablyudeniya': '',
                        'chego_ne_hvataet': ', '.join(
                            ([] if lich else ['личного номера'] if tel else ['номера вовсе'])
                            + ([] if rol_ else ['роли'])),
                        'pochta': (c.get('pochta') or '').strip()[:80]})

    # Имя приводится к «Фамилия И.О.» ДО сведения — иначе «А.В. Чугайнов» и «Чугайнов А.В.»
    # не склеятся: ключом сведения стоит первое слово имени.
    perevernuto = 0
    for r in out:
        st = (r.get('chelovek') or '').strip()
        nov = imya_v_poryadok(st)
        if nov != st:
            r['chelovek'] = nov
            perevernuto += 1
    if perevernuto:
        print(f'  ИМЯ В ПОРЯДОК: {perevernuto} записей вида «А.В. Чугайнов» → «Чугайнов А.В.»',
              file=sys.stderr)

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

    # ОБРАТНЫЙ ХОД 3-Й СЕССИИ по МОЕМУ списку «ФИО есть, личного номера нет».
    # Дописывается ПОСЛЕ сведения: эти люди уже стоят в фиде (я их и отдавал), новых строк
    # заводить не надо — надо дозаполнить пустые клетки у существующих.
    #
    # Числа честные и их стоит держать перед глазами: 779 строк, из них ЛИЧНЫХ МОБИЛЬНЫХ 16
    # (11 человек), городских 435, почт 328. Счётчик канала показывал «317 телефонов» — это
    # любые номера; после разбора общих осталось 16. Сосед сам поправил свою цифру.
    # Городские не выбрасываю и личными не называю: имя и должность в руках, значит по
    # коммутатору можно спросить конкретного человека — это рабочий ход, просто не прямой.
    obr = chitat(OBRATNYY)
    if obr:
        po_fam = defaultdict(list)
        for r in out:
            im = (r.get('chelovek') or '').strip()
            if im:
                po_fam[(r['inn'], im.split()[0].lower())].append(r)
        sch_o = Counter()
        for x in obr:
            fio = (x.get('fio') or '').strip()
            if not fio:
                continue
            celi = po_fam.get((x.get('inn'), fio.split()[0].lower()))
            if not celi:
                sch_o['человека нет в фиде'] += 1
                continue
            zn = (x.get('znachenie') or '').strip()
            vid = (x.get('vid') or '').strip()
            vyvod = (x.get('vyvod') or '')
            for r in celi:
                if vid == 'почта':
                    if not (r.get('pochta') or '').strip():
                        r['pochta'] = zn[:80]
                        sch_o['почта'] += 1
                elif vid == 'мобильный' and not vyvod.startswith('ОБЩИЙ'):
                    if not (r.get('lichnyy_nomer') or '').strip():
                        r['lichnyy_nomer'] = zn
                        r['vid_lichnogo'] = 'мобильный, обратный ход 3-й сессии'
                        sch_o['ЛИЧНЫЙ МОБИЛЬНЫЙ'] += 1
                else:
                    if zn and zn not in (r.get('nomera_predpriyatiya') or ''):
                        r['nomera_predpriyatiya'] = (
                            ((r.get('nomera_predpriyatiya') or '') + ' | ' + zn).strip(' |'))[:120]
                        sch_o['общий/городской'] += 1
                ist = (x.get('istochnik') or 'обратный ход 3-й сессии')
                bylo = [s for s in (r.get('istochnik_cheloveka') or '').split(' | ') if s.strip()]
                if ist not in bylo:
                    r['istochnik_cheloveka'] = ' | '.join(bylo + [ist])[:400]
                ssyl = (x.get('ssylka') or '').strip()
                if ssyl and ssyl not in (r.get('ssylka_na_cheloveka') or ''):
                    r['ssylka_na_cheloveka'] = (
                        ((r.get('ssylka_na_cheloveka') or '') + ' | ' + ssyl).strip(' |'))[:400]
        print(f'  ОБРАТНЫЙ ХОД 3-й СЕССИИ: {dict(sch_o)}', file=sys.stderr)

    # Колонка «что делать» заполняется ПОСЛЕ сведения дублей: у сведённой строки может
    # оказаться номер, пришедший из другого источника, и действие тогда другое.
    # ПОСТОЯННЫЙ АУДИТ ОБЩИХ НОМЕРОВ. Разовой проверки мало: дефект возвращается с каждым
    # новым источником. Номер, стоящий у ДВУХ и более предприятий, личным не бывает — это
    # приёмная, посредник или 8-800. Найдено первой сессией у себя (72 записи), проверено у
    # меня: 8 номеров на 2+ предприятиях, 12 на 2+ людях.
    # Номер не выбрасывается: он переезжает в телефоны предприятия с явной пометкой, потому
    # что позвонить по нему можно, а выдавать за личный нельзя.
    # Признак «не личный» — РАЗНЫЕ ФАМИЛИИ на одном номере, а не разные ИНН и не разные
    # написания имени. Правило переписано 04.08 по замеру на разметке 3-й сессии:
    #   * «Чикуров В.В.» и «Чикуров Владимир Васильевич» — ОДИН человек, а сравнение строк
    #     целиком объявляет их двумя. Таких ложных тревог у соседа 29 из 153 — 18 %;
    #   * прежнее моё правило «номер у двух ИНН — не личный» снимало и настоящие личные:
    #     Сидиченко Александр Александрович стоит у двух предприятий, но он один человек,
    #     и мобильный у него личный. Один человек у двух работодателей — обычное дело.
    # Поэтому решает фамилия: две и больше разных — номер не личный, одна — личный, даже
    # если предприятий два (это отмечается словами, а не снятием номера).
    def familiya(imya):
        ch = re.sub(r'[^А-Яа-яЁёA-Za-z ]', ' ', imya or '').lower().split()
        return ch[0] if ch else ''

    po_nomeru = defaultdict(lambda: {'inn': set(), 'fam': set()})
    for r in out:
        c = re.sub(r'\D', '', r.get('lichnyy_nomer') or '')
        if len(c) >= 10:
            po_nomeru[c[-10:]]['inn'].add(r['inn'])
            f = familiya(r.get('chelovek'))
            if f:
                po_nomeru[c[-10:]]['fam'].add(f)
    obshchie = {k for k, v in po_nomeru.items() if len(v['fam']) > 1}
    dvoynye = {k for k, v in po_nomeru.items()
               if k not in obshchie and len(v['inn']) > 1}
    snyato = 0
    for r in out:
        c = re.sub(r'\D', '', r.get('lichnyy_nomer') or '')
        if len(c) < 10:
            continue
        if c[-10:] in obshchie:
            r['nomera_predpriyatiya'] = ((r.get('nomera_predpriyatiya') or '') + ' | '
                                         + r['lichnyy_nomer']).strip(' |')[:70]
            r['vid_lichnogo'] = ('номер у разных фамилий — не личный, звонить как в общую '
                                 'линию')
            r['lichnyy_nomer'] = ''
            snyato += 1
        elif c[-10:] in dvoynye:
            # Номер остаётся личным: тот же человек числится у двух предприятий.
            r['vid_lichnogo'] = ((r.get('vid_lichnogo') or '') +
                                 '; тот же человек числится ещё у одного предприятия'
                                 ).strip('; ')[:90]
    if snyato or dvoynye:
        print(f'  АУДИТ: номеров у разных фамилий {len(obshchie)} (снято строк {snyato}), '
              f'номеров одного человека у нескольких предприятий {len(dvoynye)} — '
              'оставлены личными')

    # ГОРОДСКОЙ В КОЛОНКЕ ЛИЧНОГО. Проверка первой сессии нашла 14 таких: номер помечен
    # «городской», а лежит как личный, и продавец звонит в приёмную, думая, что звонит
    # человеку. Номер не теряется — переезжает в телефоны предприятия, где ему и место.
    perenesli = 0
    for r in out:
        t = (r.get('lichnyy_nomer') or '').strip()
        if t and not mobilnyy(t):
            r['nomera_predpriyatiya'] = ((r.get('nomera_predpriyatiya') or '') + ' | ' + t
                                         ).strip(' |')[:70]
            r['lichnyy_nomer'] = ''
            r['vid_lichnogo'] = 'номер не личный, перенесён в телефоны предприятия'
            perenesli += 1
    if perenesli:
        print(f'  городских номеров убрано из колонки личного: {perenesli}')

    for r in out:
        r['chto_delat'] = chto_delat(r)

    with open(VYHOD, 'w', encoding='utf-8-sig', newline='') as fh:
        polya = list(out[0].keys())
        if 'chto_delat' not in polya:
            polya.append('chto_delat')
        if 'istochnikov_cheloveka' not in polya:
            polya.append('istochnikov_cheloveka')
        w = csv.DictWriter(fh, fieldnames=polya, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in out:
            w.writerow(r)

    # --- КОГО ВЫБРОСИЛИ И ПОЧЕМУ ---
    # Сборка идёт обходом очереди, поэтому человек, чьего предприятия в очереди нет, исчезает
    # без единого счётчика. Замер 03.08: из 1 548 строк соседской базы ЛПР доезжают 444, а
    # 1 104 пропадают молча, среди них 38 с личным мобильным и все технических ролей
    # (гл.энергетик 409, нач.цеха 253, гл.инженер 175).
    # Выброс сам по себе правильный — очередь на то и очередь. Неправильно МОЛЧАНИЕ: без этого
    # файла нельзя ни проверить строгость классификатора, ни вернуть человека, если предприятие
    # позже в очередь войдёт. Причина пишется рядом, чтобы её можно было оспорить по одной.
    v_ocheredi = {r['inn'] for r in och}
    prichina_po_inn = {}
    for imya, fajl in (('среда машины не установлена', 'OCHERED-sreda-neizvestna.csv'),
                       ('машина газовая, не воздушная', 'OTSEV-gaz.csv')):
        p = os.path.join(L, fajl)
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'):
                prichina_po_inn.setdefault(r['inn'], imya)
    otsev = []
    for c in lpr:
        if c['inn'] in v_ocheredi:
            continue
        otsev.append({
            'inn': c['inn'], 'predpriyatie': (c.get('predpriyatie') or '')[:120],
            'chelovek': c.get('fio') or '', 'dolzhnost': (c.get('dolzhnost_kak_v_istochnike') or '')[:70],
            'rol': c.get('rol') or '', 'lichnyy_nomer': c.get('lichnyy_nomer') or '',
            'nomera_predpriyatiya': (c.get('nomera_predpriyatiya') or '')[:70],
            'istochnik_cheloveka': c.get('istochnik') or '',
            'pochemu_ne_v_paneli': prichina_po_inn.get(
                c['inn'],
                'предприятие есть в базе, но воздушной центробежной машины у него не доказано'
                if c['inn'] in pred else 'предприятия нет в нашей базе фактов вовсе'),
        })
    OTSEV_LYUDI = os.path.join(L, 'OTSEV-lyudi-vne-ocheredi.csv')
    with open(OTSEV_LYUDI, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(otsev[0].keys()) if otsev else ['inn'],
                           delimiter=';', extrasaction='ignore')
        w.writeheader()
        w.writerows(otsev)
    print(f'  ОТСЕВ: людей вне очереди {len(otsev)}, из них с личным номером '
          f'{sum(1 for r in otsev if r["lichnyy_nomer"])} → {os.path.basename(OTSEV_LYUDI)}')
    print('    ' + ', '.join(f'{k}: {v}' for k, v in
                             Counter(r['pochemu_ne_v_paneli'][:45] for r in otsev).most_common()))

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
