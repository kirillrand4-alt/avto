# -*- coding: utf-8 -*-
"""P25: найти ФИО ЛПР по поиску «предприятие + должность». Вход для обратного хода.

ПОЧЕМУ ЭТО ПЕРВЫЙ ШАГ, А НЕ ОБРАТНЫЙ ХОД. Стартовый файл поручает 3-й сессии обратный ход по
ФИО. Но обратный ход — это ФИО → номер, а у P25 сбор идёт С НУЛЯ: из 491 предприятия 456 без
единого человека. Искать номер некому, пока нет имени. Значит мой канал начинает с того же
поискового пула, но с другим запросом: не «человек → его номер», а «предприятие + должность →
кто это».

ЧТО БЕРУ И ЧЕГО НЕ БЕРУ, чтобы не делать чужую работу. 2-я сессия идёт по закупочным площадкам
и делает первую двадцатку руками. Я беру места с 21-го и ниже и только поисковый канал.
Пересечение с их методом 3 возможно, поэтому строка об этом идёт в журнал ДО прогона.

ОТКУДА ФОРМЫ ЗАПРОСА. Из ТЗ, раздел «Метод 3», плюс проверенное на центробежке: кавычки
обязательны — без них поиск приносит однофамильцев с других заводов; название берётся и из
ЕГРЮЛ, и коротким видом, потому что «АО „КАУСТИК"» и «Каустик Волгоград» дают разную выдачу.

ЗАСЛОНЫ, БЕЗ КОТОРЫХ КАНАЛ ВРЕДЕН — все три оплачены вчера:

  * ПРИНАДЛЕЖНОСТЬ СТРАНИЦЫ (`chuzhaya_stranica`). Случай Юрина: имя нашлось на приветствии
    выставки, и в панель уехал телефон организатора как номер главного инженера. Страница
    засчитывается, только если это сайт предприятия, страница про него на сайте холдинга,
    карточка закупки или в тексте названо само предприятие;
  * ДОЛЖНОСТЬ БЕЗ ПОДРАЗДЕЛЕНИЯ РОЛЬ НЕ ОПРЕДЕЛЯЕТ. «Заместитель главного инженера по
    экологии» — не первый круг, хотя слова совпадают;
  * ДАТА ПРИНАДЛЕЖИТ НАБЛЮДЕНИЮ. Пишется дата из ТЕКСТА страницы, а не день выгрузки; нет
    даты в тексте — поле пустое, и это честнее выдуманной свежести.

Запуск:
    python3 p25_imena_serp.py --polozhit          # положить канал и список на сервер
    python3 p25_imena_serp.py --ot 21 --do 120    # прогон по местам 21..120
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
import run_on_server as R  # noqa: E402

TUT = os.path.dirname(os.path.abspath(__file__))
SPISOK_LOK = ('/tmp/claude-0/-home-user-avto/66783df1-79e2-513f-8bfb-9c49a1f69007/'
              'scratchpad/P25-PREDPRIYATIYA-po-summe.csv')
KANAL = r'C:\sender\_ops\3s_p25_imena.py'
VHOD = r'C:\sender\_ops\3s_p25_predpriyatiya.csv'
POTOK = r'C:\sender\_ops\p25-imena.jsonl'

SCRIPT = r'''
# -*- coding: utf-8 -*-
import csv, json, os, re, sys, threading, time
sys.path.insert(0, r'C:\sender\_ops')
import _3s_lpr_obratnyy as L          # готовый двухдвижковый serp с ретраями
import _3s_chuzhaya_stranica as CH

VHOD = r'C:\sender\_ops\3s_p25_predpriyatiya.csv'
POTOK = r'C:\sender\_ops\p25-imena.jsonl'
OT = int(sys.argv[sys.argv.index('--ot') + 1]) if '--ot' in sys.argv else 21
DO = int(sys.argv[sys.argv.index('--do') + 1]) if '--do' in sys.argv else 120
POT = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 6

# ДОЛЖНОСТИ ПЕРВОГО И ВТОРОГО КРУГА. Третий (закупки) не спрашиваем: по ТЗ он ниже, а канал
# общий и узкий — тратить его на снабженцев, пока не пройдены технические, значит менять
# главную меру на второстепенную.
DOLZHNOSTI = ('главный инженер', 'главный механик', 'главный энергетик',
              'технический директор', 'начальник производства')

FIO = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\s+'
    r'([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\b')
FIO_OBR = re.compile(
    r'\b([А-ЯЁ][а-яё]{2,})\s+([А-ЯЁ][а-яё]{3,}(?:ович|евич|ьевич|инич|овна|евна|ьевна|ична))\s+'
    r'([А-ЯЁ][а-яё]{2,}(?:-[А-ЯЁ][а-яё]{2,})?)\b')          # «Эдуард Юрьевич Еремеев»
# ДАТА ОПРЕДЕЛЯЕТСЯ ЗДЕСЬ, ГДЕ ПОЛНЫЙ ТЕКСТ ЕЩЁ ЕСТЬ. Замечание 1-й сессии по первому
# принятому файлу: 12 строк из 13 ушли без даты и в МЕРУ УСПЕХА не пошли. Первая правка
# добавила разбор даты в выкладку — и упёрлась в то, что в поток кладётся цитата в 300
# знаков, а год стоит обычно вне её: в имени файла сборника, в шапке страницы, в подписи
# протокола. Значит считать дату надо в канале, пока страница под рукой, а не потом.
# Порядок от надёжного к слабому и подписывается, а не теряется.
DATA = re.compile(r'\b(20[0-2]\d)\s*(?:год|г\.)?|\b\d{1,2}\.\d{2}\.(20[0-2]\d)\b')
GOD = re.compile(r'(?<!\d)(20[0-2]\d)(?!\d)')


def data_i_chem(ryad, url, ves_tekst):
    m = GOD.search(ryad or '')
    if m:
        return m.group(1), 'год в тексте рядом с именем и должностью'
    m = GOD.search(url or '')
    if m:
        return m.group(1), 'год в адресе страницы или в имени файла'
    gody = set(GOD.findall(ves_tekst or ''))
    if len(gody) == 1:
        return gody.pop(), 'единственный год на странице'
    if gody:
        # Несколько разных годов и ни одного рядом с именем: выбрать наугад значит выдумать
        # свежесть. Записываем найденные, чтобы человек решил, но в поле даты — пусто.
        return '', 'на странице годы %s, рядом с именем ни одного' % ','.join(sorted(gody))
    return '', 'даты в источнике нет'
# ЗАПРЕЩЁННЫЕ ИСТОЧНИКИ. Найдено глазами на первом же живом прогоне — 66 человек, и среди
# них три породы, которые брать нельзя:
#   * `ural.gosnadzor.ru` (7 человек) — РАСПИСАНИЕ АТТЕСТАЦИИ Ростехнадзора и `complan.pro`
#     (5) — карточки проверок. Прямое правило владельца, перенесённое в P25 целиком: повод
#     для звонка из реестра проверок брать запрещено. Человек назван там потому, что не сдал
#     проверку знаний, а не потому, что он наш ЛПР;
#   * `vyborypro.ru`, `elections.*` — декларации кандидатов на выборах. Место работы там
#     действительно указано, но страница про выборы и несёт дату рождения и сведения о
#     судимости. Такие данные нам не нужны и брать их неуместно;
#   * `inndex.ru` и подобные — агрегаторы выписок. По ТЗ агрегатор сам по себе
#     подтверждением не считается: нужен хотя бы один первоисточник.
ZAPRESHCHENNYY = re.compile(
    r'gosnadzor|rostehnadzor|rostechnadzor|attestac|complan\.pro|proverk[ai]\.|'
    r'vyborypro|elections|izbirkom|vybory|cikrf', re.I)
AGREGATOR = re.compile(r'inndex|rusprofile|list-org|zachestnyibiznes|checko|sbis|'
                       r'kartoteka|audit-it|synapsenet|seldon|kontragent', re.I)

# НЕ ФАМИЛИЯ. «Николай Иванович Главный» — разбор принял слово «Главный» за фамилию, ровно
# как вчера «Подписал Э.Ю.». Список тот же, что в `imya_porcha`.
NE_FAMILIYA = re.compile(
    r'^(?:главн|начальн|заместител|директор|инженер|механик|энергетик|технич|исполняющ|'
    r'руководител|специалист|ведущ|старш|представител|контакт|телефон|адрес|общест|'
    r'акционерн|компани|организац|предприят|управлен|отдел|служб|цех|участок|'
    # «Уважаемый Сергей Владимирович!» — обращение из письма, разобранное как ФИО с
    # фамилией «Уважаемый». Поймано глазами: строка уехала в выкладку с должностью
    # главного механика, которая на той же странице принадлежит Софронову Н. М.
    r'уважаем|многоуважаем|дорог|глубокоуважаем)', re.I)

# Слова, отменяющие первый круг: должность есть, а зона не наша.
NE_NASH_KRUG = re.compile(r'по\s+эколог|эколог|охран\w+\s+труд|промышленн\w+\s+безопасн|'
                          r'по\s+кадр|по\s+персонал|по\s+социальн|по\s+режим|'
                          r'по\s+граждан\w+\s+оборон|по\s+связям', re.I)


def korotkoe(imya):
    """«ООО "КОМПРЕССОР-ТЕХЦЕНТР"» → «КОМПРЕССОР-ТЕХЦЕНТР»."""
    v = re.sub(r'^\s*(ООО|ОАО|ЗАО|ПАО|АО|НАО|ФГУП|ГУП|МУП|ФКП|ИП)\s+', '', (imya or '').strip())
    return v.strip('"«» ')


# Должность целиком, с русскими окончаниями: «главный инженер» → «главн\w* инженер\w*».
# Собирается один раз на должность и кэшируется — вызывается на каждое найденное имя.
_DOLZH_KESH = {}


def _dolzhnost_rx(dolzh):
    rx = _DOLZH_KESH.get(dolzh)
    if rx is None:
        chasti = []
        for sl in dolzh.split():
            koren = sl[:-2] if len(sl) > 6 else sl
            chasti.append(re.escape(koren) + r'\w*')
        rx = re.compile(r'\b' + r'[\s\-]+'.join(chasti), re.I)
        _DOLZH_KESH[dolzh] = rx
    return rx


def razobrat(docs, predpr, dolzh):
    """Из выдачи — люди с должностью, ссылкой и датой из текста."""
    out = []
    for d in docs:
        url = (d.get('url') or '').strip()
        # ИМЯ ПОЛЯ НЕ УГАДЫВАЕТСЯ. Первый прогон дал 95 запросов, выдачу от 1 до 14
        # документов, СБОЕВ НОЛЬ — и ноль людей. Причина: я читал `title`/`passage`/
        # `snippet`/`text`, а документ несёт ровно два ключа — `url` и `tekst`. Ноль при
        # нуле сбоев — признак сломанного прибора, а не пустого источника; правило
        # «источник ненадёжен запрещён» сработало ровно так, как задумано.
        # Теперь берём ВСЕ строковые поля кроме адреса — тогда переименование поля в
        # источнике канал не сломает.
        tekst = ' '.join(v for k, v in d.items() if k != 'url' and isinstance(v, str))
        if not tekst.strip():
            continue
        # ЗАСЛОН ПРИНАДЛЕЖНОСТИ — до разбора, а не после: иначе имя уже «найдено».
        if ZAPRESHCHENNYY.search(url):
            out.append({'fio': '', 'dolzhnost': dolzh, 'krug': 'ИСТОЧНИК ЗАПРЕЩЁН',
                        'ssylka': url, 'podtverzhdena': False,
                        'pochemu': 'реестр проверок, аттестация или выборы — повод и данные '
                                   'оттуда брать нельзя', 'citata': '', 'data_iz_teksta': ''})
            continue
        # СТРОГИЙ РЕЖИМ — требование ТЗ P25: подтверждает только первоисточник. Мягкое
        # «имя предприятия названо в тексте» пропускало все агрегаторы разом, потому что
        # называть предприятие — их работа.
        est, poch = CH.stranica_podtverzhdaet(url, '', predpr, tekst, strogo=True)
        if est and AGREGATOR.search(url):
            est, poch = False, 'агрегатор выписок — не первоисточник, нужен ещё один источник'
        okno = tekst
        # ОДНО ИМЯ НА ОКНО. В выдаче inndex две фамилии стояли в одном абзаце, и обеим
        # досталась одна и та же должность из одной цитаты: «Ларин Максим Валерьевич —
        # главный инженер» и рядом «Смирнов Вячеслав Владимирович», которому эта должность
        # не принадлежит. Близость не доказывает принадлежность — то же правило, третий раз.
        zanyato = []
        for m in list(FIO.finditer(okno)) + list(FIO_OBR.finditer(okno)):
            fio = m.group(0)
            if NE_FAMILIYA.match(m.group(1)) or NE_FAMILIYA.match(m.group(3)):
                continue
            # Должность рядом: окно ±120 знаков, иначе имя со страницы «наши люди» получит
            # чужую должность из соседнего абзаца.
            ryad = okno[max(0, m.start() - 120):m.end() + 120]
            # ДОЛЖНОСТЬ ИЩЕТСЯ ЦЕЛИКОМ, А НЕ ПО ПОСЛЕДНЕМУ СЛОВУ. Прежняя строка брала
            # `dolzh.split()[-1][:6]` — для «технический директор» это «директ», и в окно
            # попадало ЛЮБОЕ слово с этим корнем. Проверка глазами по десяти случайным
            # строкам выложенного файла поймала цену ошибки: у трёх человек в цитате прямо
            # написано «Генеральный директор», а в моей колонке стоит «технический
            # директор» — и роль «1 круг», то есть они уехали в главную меру как технические
            # ЛПР. Должность бралась ИЗ ЗАПРОСА, а страница только «не возражала».
            #
            # То же и с «начальник производства»: корень «произв» ловил соседнюю строку
            # «Начальник производства — Стрыгин Яков», и должность доставалась Баранову,
            # который на той же странице назван руководителем.
            if not _dolzhnost_rx(dolzh).search(ryad):
                continue
            poz_dolzh = _dolzhnost_rx(dolzh).search(ryad).start() + max(0, m.start() - 120)
            if poz_dolzh in zanyato:
                continue
            zanyato.append(poz_dolzh)
            if NE_NASH_KRUG.search(ryad):
                out.append({'fio': fio, 'dolzhnost': dolzh, 'krug': 'мимо: зона не наша',
                            'ssylka': url, 'podtverzhdena': est, 'pochemu': poch[:110],
                            'citata': ryad[:300], 'data_iz_teksta': ''})
                continue
            god, chem = data_i_chem(ryad, url, tekst)
            out.append({'fio': fio, 'dolzhnost': dolzh,
                        'krug': '1-2 круг' if est else 'страница не подтверждает',
                        'ssylka': url, 'podtverzhdena': est, 'pochemu': poch[:110],
                        'citata': ryad[:300],
                        'data_iz_teksta': god, 'chem_data': chem})
    return out


stroki = [r for r in csv.DictReader(open(VHOD, encoding='utf-8-sig'))
          if OT <= int(r['mesto']) <= DO and r.get('tip') != 'ИП']
gotovo = set()
if os.path.exists(POTOK):
    for ln in open(POTOK, encoding='utf-8'):
        try:
            z = json.loads(ln)
        except Exception:
            continue
        if not z.get('err'):
            gotovo.add((z['inn'], z['dolzhnost']))

zad = [(r, d) for r in stroki for d in DOLZHNOSTI if (r['inn'], d) not in gotovo]
print('предприятий %d, запросов к обходу %d, потоков %d' % (len(stroki), len(zad), POT),
      file=sys.stderr, flush=True)

f = open(POTOK, 'a', encoding='utf-8')
lock = threading.Lock()
sch = {'n': 0, 'sboev': 0, 'lyudey': 0, 'podtv': 0}


def odin(z):
    r, dolzh = z
    polnoe, kratko = r['naimenovanie'].strip('"'), korotkoe(r['naimenovanie'])
    zapros = '"%s" "%s"' % (kratko, dolzh)
    docs, err = L.serp(zapros)
    if err and not docs:
        zapis = {'inn': r['inn'], 'predpriyatie': polnoe, 'dolzhnost': dolzh, 'err': err}
    else:
        lyudi = razobrat(docs, polnoe, dolzh)
        zapis = {'inn': r['inn'], 'predpriyatie': polnoe, 'dolzhnost': dolzh,
                 'zapros': zapros, 'naydeno': len(docs), 'lyudi': lyudi}
    with lock:
        f.write(json.dumps(zapis, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())          # правило долговечности: результат переживает откат
        sch['n'] += 1
        if zapis.get('err'):
            sch['sboev'] += 1
        else:
            sch['lyudey'] += len(zapis['lyudi'])
            sch['podtv'] += len([x for x in zapis['lyudi'] if x['podtverzhdena']])
        if sch['n'] % 25 == 0:
            print('  %d/%d запросов, людей %d (подтверждённой страницей %d), сбоев %d'
                  % (sch['n'], len(zad), sch['lyudey'], sch['podtv'], sch['sboev']),
                  file=sys.stderr, flush=True)


potoki = []
for z in zad:
    while len([t for t in potoki if t.is_alive()]) >= POT:
        time.sleep(0.15)
    t = threading.Thread(target=odin, args=(z,), daemon=True)
    t.start(); potoki.append(t)
for t in potoki:
    t.join()
f.close()
print('готово: запросов %d, ЛЮДЕЙ %d, из них страница подтверждает %d, СБОЕВ %d '
      '(сбой это не ноль) -> %s' % (sch['n'], sch['lyudey'], sch['podtv'], sch['sboev'], POTOK),
      file=sys.stderr, flush=True)
'''


def main():
    if '--polozhit' in sys.argv:
        fajly = [
            {'dest': r'C:\sender\_ops\_3s_lpr_obratnyy.py',
             'b64': base64.b64encode(open(os.path.join(TUT, 'lpr_obratnyy.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': r'C:\sender\_ops\_3s_chuzhaya_stranica.py',
             'b64': base64.b64encode(open(os.path.join(TUT, 'chuzhaya_stranica.py'),
                                          encoding='utf-8').read().encode()).decode()},
            {'dest': VHOD, 'b64': base64.b64encode(open(SPISOK_LOK, 'rb').read()).decode()},
            {'dest': KANAL, 'b64': base64.b64encode(SCRIPT.encode()).decode()},
        ]
        R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': fajly}, timeout=300)
        print('положено', file=sys.stderr)
        return
    argv = []
    for k in ('--ot', '--do', '--potokov'):
        if k in sys.argv:
            argv += [k, sys.argv[sys.argv.index(k) + 1]]
    r = R.submit('enrich_contacts',
                 {'op': 'panel_py', 'script': KANAL, 'argv': argv, 'timeout': 1700},
                 timeout=1800)
    d = r.get('data') or {}
    print((d.get('stdout_tail') or '')[-1500:])
    print('--- ход ---\n' + (d.get('stderr_tail') or '')[-2500:], file=sys.stderr)


if __name__ == '__main__':
    main()
