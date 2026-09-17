# -*- coding: utf-8 -*-
"""Правка `C:\\sender\\server\\news_scan.py`: убрать молчание в `extract_event`.

ЧТО СЕЙЧАС. Классификатор кончается голым перехватом:

    try:
        out = VC._provider_call_stdlib(prompt)
        m = re.search(r'\\{.*\\}', out or '', re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None

а единственное место вызова (строка 1685, внутри `enrich_ev`, который крутится в
`ThreadPoolExecutor` на 12 потоков) читает результат так:

    ev = extract_event(it.get('full_text') or it['title'], it.get('source', ''))
    if not ev or not ev.get('is_capex'):
        return None

Значит ЛЮБОЙ сбой - оборванное соединение, пустой ответ шлюза, битый JSON - превращается
в «не капекс» и материал молча исчезает. Замер 17.09: пока с сервера был выбран мёртвый
адрес шлюза, `extract_event` давал 6 NULL из 6 - и на явных капекс-событиях, и на
заведомо пустом контроле «погода в Москве». Отличить одно от другого было НЕЧЕМ, поэтому
месяц без единого события никого не насторожил: свежая запись в signals от 15 августа.

ЧТО ДЕЛАЕТ ПРАВКА. Разводит три исхода, которые голый except склеивал в один:

    1) разобранный JSON        -> вердикт; ТОЛЬКО он голосует «капекс / не капекс»;
    2) исключение при вызове   -> ОТКАЗ: считается и печатается, материал не осуждён;
    3) 200 без JSON или пусто  -> тоже ОТКАЗ, а не «событий нет».

Отказы копятся в `OTKAZY_PROVAJDERA` (счётчик потокобезопасный) и попадают в отчёт
прогона рядом с `raw_items`/`capex_events`, то есть становятся ВИДНЫ в том же месте, где
владелец смотрит числа.

ЧТО ЭТО СЛОМАЕТ - честно:
  - `extract_event` при сбое возвращает теперь СЛОВАРЬ `{'is_capex': None, '_otkaz': ...}`
    вместо `None`. Словарь ИСТИННЫЙ, поэтому старая проверка `if not ev or not
    ev.get('is_capex')` ведёт себя точно так же (материал отбрасывается) - поведение
    конвейера не меняется даже без правки места вызова. Если где-то появится код,
    пишущий `ev` в базу без проверки `is_capex`, он запишет отказ как запись: такой код
    обязан сперва смотреть `_otkaz`.
  - Место вызова в news_scan одно (проверено перебором всех вхождений `extract_event` в
    файле: определение 1059, два комментария 1647 и 1789, вызов 1685).
  - Счётчик живёт в процессе раннера, поэтому правка обнуляет его в начале прогона,
    рядом с `VC._PROVIDER_MODEL = ...`. Иначе числа накапливались бы между прогонами.
  - Печать отказов ограничена: первые пять и далее каждый двадцать пятый, чтобы не залить
    хвост вывода задания.

ПРАВКА НЕ ЛЕЧИТ САМ ШЛЮЗ. Причина обрывов - мёртвый адрес имени `router.cheap` с этого
сервера, см. `SHLYUZ-PROVAJDERA-OPIS.md`. Здесь чинится только молчание.

Использование:
    python3 seo-texts/zapusk_na_servere.py pravka_extract_event.py --zamer
    python3 seo-texts/zapusk_na_servere.py pravka_extract_event.py --proverit
    python3 seo-texts/zapusk_na_servere.py pravka_extract_event.py --primenit --zamer
    python3 seo-texts/zapusk_na_servere.py pravka_extract_event.py --otkatit <файл.bak>
"""
import os
import py_compile
import shutil
import sys
import time

CEL = os.environ.get('NEWS_SCAN_PATH', r'C:\sender\server\news_scan.py')

# ------------------------------------------------------------------ якоря
# A0: счётчик и помощник кладутся ПЕРЕД определением классификатора.
A0_YAKOR = 'def extract_event(title, source):'
A0_NOVOE = '''# --- видимый отказ провайдера (правка 17.09.2026) ---------------------------------
# Голый `except Exception: return None` ниже склеивал две разные вещи: «модель сказала, что
# события нет» и «до модели не доехали». Вторая молчала месяц. Здесь отказ становится
# СЧИТАЕМЫМ, а голосовать «не капекс» ему больше нечем.
OTKAZY_PROVAJDERA = {'vsego': 0, 'prichiny': {}}
# threading берём точечно, чтобы не трогать блок импортов файла
_OTKAZ_ZAMOK = __import__('threading').Lock()


def _otkaz_provajdera(prichina):
    """Записать отказ и вернуть пометку вместо вердикта.

    Возвращается СЛОВАРЬ, а не None: словарь истинный, поэтому старые проверки вида
    `if not ev or not ev.get('is_capex')` продолжают отбрасывать материал ровно как
    раньше, а новый код может отличить отказ по ключу `_otkaz`.
    """
    kl = str(prichina).split(':')[0][:44]
    with _OTKAZ_ZAMOK:
        OTKAZY_PROVAJDERA['vsego'] += 1
        OTKAZY_PROVAJDERA['prichiny'][kl] = OTKAZY_PROVAJDERA['prichiny'].get(kl, 0) + 1
        n = OTKAZY_PROVAJDERA['vsego']
    if n <= 5 or n % 25 == 0:
        print('[extract_event] ОТКАЗ ПРОВАЙДЕРА #%d: %s' % (n, str(prichina)[:160]),
              flush=True)
    return {'is_capex': None, '_otkaz': str(prichina)[:200]}


'''

# A1: хвост самой функции.
A1_STAROE = """    try:
        out = VC._provider_call_stdlib(prompt)
        m = re.search(r'\\{.*\\}', out or '', re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:  # noqa: BLE001
        return None"""
A1_NOVOE = """    # Три исхода вместо двух: вердикт, отказ по исключению, отказ по пустому ответу.
    # Голосовать «капекс / не капекс» имеет право ТОЛЬКО разобранный JSON.
    try:
        out = VC._provider_call_stdlib(prompt)
    except Exception as ex:  # noqa: BLE001
        return _otkaz_provajdera('%s: %s' % (type(ex).__name__, str(ex)[:130]))
    m = re.search(r'\\{.*\\}', out or '', re.S)
    if not m:
        # 200 OK с пустым текстом - тоже отказ. У шлюза это бывает при исчерпанном
        # бюджете размышления: ошибки в панели нет, а текста нет тоже.
        return _otkaz_provajdera('ответ без JSON, знаков в ответе: %d' % len(out or ''))
    try:
        return json.loads(m.group(0))
    except Exception as ex:  # noqa: BLE001
        return _otkaz_provajdera('JSON не разобрался: %s' % str(ex)[:90])"""

# A2: место вызова - делаем намерение явным (поведение то же).
A2_STAROE = """        ev = extract_event(it.get('full_text') or it['title'], it.get('source', ''))
        if not ev or not ev.get('is_capex'):
            return None"""
A2_NOVOE = """        ev = extract_event(it.get('full_text') or it['title'], it.get('source', ''))
        if ev and ev.get('_otkaz'):
            # Провайдер не ответил: материал НЕ разобран. Это не «не капекс» - голосовать
            # нечем. Отказ уже посчитан в OTKAZY_PROVAJDERA и попадёт в отчёт прогона.
            return None
        if not ev or not ev.get('is_capex'):
            return None"""

# A3: отчёт прогона - туда же, где владелец смотрит числа.
A3_STAROE = "'raw_items': len(raw), 'capex_events': len(events),"
A3_NOVOE = ("'raw_items': len(raw), 'capex_events': len(events),\n"
            "                           'provider_otkazov': OTKAZY_PROVAJDERA['vsego'],\n"
            "                           'provider_otkazy': dict(OTKAZY_PROVAJDERA['prichiny']),")

# A4: обнуление счётчика в начале прогона.
A4_STAROE = "    VC._PROVIDER_MODEL = args.get('extract_model', 'claude-fable-5')"
A4_NOVOE = ("    VC._PROVIDER_MODEL = args.get('extract_model', 'claude-fable-5')\n"
            "    # счётчик отказов - за ЭТОТ прогон, а не за всю жизнь процесса раннера\n"
            "    OTKAZY_PROVAJDERA['vsego'] = 0\n"
            "    OTKAZY_PROVAJDERA['prichiny'] = {}")

PRAVKI = [('A0 счётчик и помощник', A0_YAKOR, A0_NOVOE + A0_YAKOR, True),
          ('A1 хвост extract_event', A1_STAROE, A1_NOVOE, False),
          ('A2 место вызова', A2_STAROE, A2_NOVOE, False),
          ('A3 отчёт прогона', A3_STAROE, A3_NOVOE, False),
          ('A4 обнуление счётчика', A4_STAROE, A4_NOVOE, False)]


def proverit(t):
    """Сколько раз каждый якорь встречается. Не один раз - не патчим вовсе."""
    print('### ЯКОРЯ в %s (%d знаков)' % (CEL, len(t)))
    vse_horosho = True
    for imya, staroe, _novoe, _vstavka in PRAVKI:
        n = t.count(staroe)
        uzhe = 'OTKAZY_PROVAJDERA' in t
        print('  %-24s встречается %d раз%s' % (imya, n, '   <- УЖЕ ПРОПАТЧЕНО' if uzhe else ''))
        if n != 1:
            vse_horosho = False
            print('       ЯКОРЬ НЕ ОДИН - правка не будет применена')
            for i, l in enumerate(t.split('\n'), 1):
                if staroe.split('\n')[0].strip() and staroe.split('\n')[0].strip() in l:
                    print('       похоже на строке %d: %s' % (i, l[:100]))
    return vse_horosho


def primenit():
    t = open(CEL, encoding='utf-8').read()
    if 'OTKAZY_PROVAJDERA' in t:
        print('УЖЕ ПРОПАТЧЕНО: OTKAZY_PROVAJDERA в файле есть, второй раз не трогаю')
        return True
    if not proverit(t):
        print('ОТКАЗ: якоря не сошлись, файл не тронут')
        return False
    bak = '%s.bak-%d' % (CEL, int(time.time()))
    shutil.copy2(CEL, bak)
    for imya, staroe, novoe, _v in PRAVKI:
        t = t.replace(staroe, novoe, 1)
        print('  применено: %s' % imya)
    open(CEL, 'w', encoding='utf-8').write(t)
    try:
        py_compile.compile(CEL, doraise=True)
    except Exception as ex:  # noqa: BLE001
        shutil.copy2(bak, CEL)
        print('ОШИБКА КОМПИЛЯЦИИ, откатил из %s: %s' % (bak, ex))
        return False
    print('ГОТОВО. Бэкап: %s' % bak)
    print('Раннер перезапускать НЕ НУЖНО: news_scan импортируется на каждое задание.')
    return True


def otkatit(bak):
    if not os.path.exists(bak):
        print('нет файла %s' % bak)
        return False
    shutil.copy2(bak, CEL)
    py_compile.compile(CEL, doraise=True)
    print('откачено из %s' % bak)
    return True


KONTROL = [
    ('ОАО «Щекиноазот» ввело в эксплуатацию установку по производству метанола, '
     'инвестиции 20 млрд рублей', True),
    ('«Норникель» объявил тендер на поставку центробежных компрессоров для завода', True),
    ('СИБУР начал строительство газоперерабатывающего комплекса в Амурской области', True),
    ('Погода в Москве на выходные: ожидается дождь', False),
    ('Курс доллара вырос на 2 рубля', False),
    ('В Москве прошёл концерт классической музыки', False),
]


def zamer():
    """Замер на контрольной выборке: 3 заведомых капекса и 3 заведомо пустых.

    Половина замера идёт с ИСПРАВНЫМ провайдером, половина - с нарочно сломанным
    (подменяем вызов на бросок исключения). Именно во второй половине и видно разницу:
    до правки сломанный провайдер даёт такой же NULL, как честное «не капекс».
    """
    sys.path.insert(0, r'C:\sender\server')
    import news_scan as NS
    import verify_company as VC
    est_pravka = hasattr(NS, 'OTKAZY_PROVAJDERA')
    print('\n### ЗАМЕР (%s)' % ('ПОСЛЕ правки' if est_pravka else 'ДО правки'))

    print('  -- половина 1: провайдер как есть --')
    verno = nul = 0
    for tekst, zhdem in KONTROL:
        r = NS.extract_event(tekst, 'проба')
        otkaz = isinstance(r, dict) and r.get('_otkaz')
        vydal = (r or {}).get('is_capex') if isinstance(r, dict) else None
        if r is None or otkaz:
            nul += 1
        elif bool(vydal) == zhdem:
            verno += 1
        print('     ждём %-9s -> %s' % ('капекс' if zhdem else 'пусто',
                                        ('ОТКАЗ: ' + str(otkaz)[:60]) if otkaz
                                        else ('NULL' if r is None else
                                              ('капекс' if vydal else 'не капекс'))))
    print('     верных вердиктов %d из %d, без вердикта %d' % (verno, len(KONTROL), nul))

    print('  -- половина 2: провайдер НАРОЧНО сломан (как при мёртвом адресе) --')
    nastoyashchiy = VC._provider_call_stdlib

    def slomannyy(*a, **k):
        raise OSError('[WinError 10054] An existing connection was forcibly closed '
                      'by the remote host (имитация)')

    VC._provider_call_stdlib = slomannyy
    if est_pravka:
        NS.OTKAZY_PROVAJDERA['vsego'] = 0
        NS.OTKAZY_PROVAJDERA['prichiny'] = {}
    golosov_ne_kapeks = otkazov = 0
    try:
        for tekst, zhdem in KONTROL:
            r = NS.extract_event(tekst, 'проба')
            otkaz = isinstance(r, dict) and r.get('_otkaz')
            if otkaz:
                otkazov += 1
                vid = 'ОТКАЗ (посчитан)'
            elif r is None:
                golosov_ne_kapeks += 1
                vid = 'NULL - молча зачтён как «не капекс»'
            else:
                vid = str(r)[:60]
            print('     ждём %-9s -> %s' % ('капекс' if zhdem else 'пусто', vid))
    finally:
        VC._provider_call_stdlib = nastoyashchiy
    print('     отказов ВИДНО: %d | молчаливых NULL: %d' % (otkazov, golosov_ne_kapeks))
    if est_pravka:
        print('     счётчик модуля: %s' % NS.OTKAZY_PROVAJDERA)
    print('  ИТОГ: сломанный провайдер %s'
          % ('виден счётчиком и не голосует' if otkazov == len(KONTROL)
             else 'НЕОТЛИЧИМ от честного «не капекс»'))


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        a = ['--proverit']
    if '--otkatit' in a:
        sys.exit(0 if otkatit(a[a.index('--otkatit') + 1]) else 1)
    if '--proverit' in a:
        proverit(open(CEL, encoding='utf-8').read())
    if '--zamer' in a and '--primenit' not in a:
        zamer()
    if '--primenit' in a:
        if not primenit():
            sys.exit(1)
        if '--zamer' in a:
            zamer()
