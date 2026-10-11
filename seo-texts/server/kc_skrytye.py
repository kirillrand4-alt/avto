# -*- coding: utf-8 -*-
r"""Спрятанные контакты из кэша страниц (ревизия 2-05, 11.10).

1) Сайты группы «Доминант» (зао-усз.рф, оао-сзл.рф и др.): телефоны и почты в JS-массивах кодов символов
   (var c={c2:{t:[43,55,...]}} + String.fromCharCode.apply) за кнопкой «Показать телефон» — разбор их не видел
   (в_текст выбрасывает <script>), у 6 заводов (≈20 млрд выручки) в Excel 0 номеров и 0 почт.
2) Номера только в ссылках мессенджеров (wa.me, api.whatsapp.com, whatsapp://, viber://) — у 12 компаний без номеров
   это был бы первый номер, у 86 с одним номером — второй (обычно мобильный менеджера).
3) (2-04) eval(unescape('%64%6f…')) / decodeURI — document.write с mailto целиком в %-кодировке (mdok.ru, zkdm.ru),
   emailriddler (массив кодов с целой ссылкой), «mailto:%20адрес» (выбрасывался целиком, ~1% компаний).

По компаниям с открывшимся сайтом: страницы кэша с fromCharCode / wa.me / whatsapp / viber, разбор после
telefony_izvlech.раскрыть; новое = найденное после раскрытия минус найденное без него и минус уже записанное.
Новое — строкой в <набор>-kontakty.jsonl (копия последней записи + контакты без роли: роль — kc_dorazmetka, «чей» —
kc_audit), прочие — отметкой в <набор>-skrytye-sdelano.txt. Стоп — при старте шагов после агентов.

    KC_NABOR=<набор> python kc_skrytye.py            (KC_SKRYTYE_PROBA=1 — только счёт и примеры)
"""
import io
import json
import os
import re
import shutil
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import kc_pochty as KP  # noqa: E402
import kc_zakupki_dobor as KZ  # noqa: E402  (пора_стоп)
import meyer_nalichie as MN  # noqa: E402
import pochty_izvlech as PI  # noqa: E402
import telefony_izvlech as TI  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
СДЕЛАНО = os.path.join(DIR, НАБОР + '-skrytye-sdelano.txt')
ПРОБА = os.environ.get('KC_SKRYTYE_PROBA') == '1'
МЕТКА = re.compile(r'fromCharCode|wa\.me/|whatsapp|viber://|unescape\(|decodeURI|mailto:%', re.I)
МЕТКИ_Б = (b'fromcharcode', b'wa.me/', b'whatsapp', b'viber://', b'unescape(', b'decodeuri', b'mailto:%')


def кэш_с_меткой(ключ):
    """Страницы кэша, только если в файле есть метка (проба: полный разбор JSON 16 тыс. файлов — 65 мин)."""
    п = os.path.join(KK.КЭШ_СТРАНИЦ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', ключ or ''))
    try:
        with open(п, 'rb') as f:
            б = zlib.decompress(f.read(), 47)  # одним вызовом (gzip.open читает кусками по 8 КБ — 4,5 мин на 1000 файлов)
    except Exception:  # noqa: BLE001
        return []
    н = б.lower()
    if not any(x in н for x in МЕТКИ_Б):
        return []
    try:
        return (json.loads(б.decode('utf-8', 'replace')) or {}).get('pages') or []
    except ValueError:
        return []


def ключ_н(номер, доб=''):
    ц = re.sub(r'\D', '', номер or '')
    return (ц[-9:] if ц.startswith('375') else ц[-10:]) + '|' + (доб or '')


def разбор(h):
    """(почты {адрес: (контекст, как)}, номера {ключ: (номер, доб, контекст)}) страницы."""
    h = KK.без_длинного(h)
    текст = KK.MP.в_текст(h) + KK.json_текст(h)
    п, н = {}, {}
    for x in KP.почты(h, текст):
        п.setdefault(x['почта'].lower(), (x.get('контекст') or '', ''))
    for e, как, поз in PI.найти(h):
        п.setdefault(e.lower(), (PI.видимый(h[max(0, (поз if поз >= 0 else 0) - 4000):max(поз, 0)])[-220:], как))
    for номер, доб, поз in TI.извлечь_номера(текст):
        н.setdefault(ключ_н(номер, доб), (номер, доб, re.sub(r'\s+', ' ', текст[max(0, поз - 200):поз + len(номер) + 60])))
    return п, н


def одна(з):
    сайт_дом = MN.домен(з.get('сайт') or '')
    свои_стр = {u for u, ст in з.get('страницы') or [] if ст in ('ok', 'кэш')}
    есть_п = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта')}
    есть_н = {ключ_н(x.get('номер'), x.get('доб')) for x in з.get('номера') or [] if x.get('номер')}
    есть_ц = {к.split('|')[0] for к in есть_н}
    нов = {}
    for стр in кэш_с_меткой(з['inn']):
        u, h = стр.get('url') or '', стр.get('html') or ''
        if not h or not МЕТКА.search(h) or (u not in свои_стр and MN.домен(u) != сайт_дом):
            continue
        р = TI.раскрыть(h)
        п1, н1 = разбор(р)
        п0, н0 = разбор(h) if р != h else (п1, н1)
        # почты — против записи (доизвлечение почт уже прошло тем же разбором; новое — раскрытое и «mailto:%20адрес»),
        # номера — ещё и против разбора без раскрытия (лишние номера страницы доизвлечение отсекло пределом)
        for e, (кт, как) in п1.items():
            if e in есть_п or e in нов or not PI.годный(e):
                continue
            нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '',
                      'скрытые': как or ('js-коды' if e not in п0 else 'mailto/повтор разбора')}
        for к, (номер, доб, кт) in н1.items():
            if к in н0 or к in есть_н or (not доб and к.split('|')[0] in есть_ц) or к in нов:
                continue
            нов[к] = {'номер': номер, 'доб': доб, 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '',
                      'скрытые': 'мессенджер' if re.search(r'WhatsApp|Viber', кт[150:]) else 'js-коды'}
    return list(нов.values())[:30]


def main():
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    сделано = set(io.open(СДЕЛАНО, encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО) else set()
    задачи = [з for з in последняя.values() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('скрытые')
              and з['inn'] not in сделано]
    print('компаний с открывшимся сайтом', len(задачи), 'проба' if ПРОБА else '', flush=True)
    сч = {'компаний_с_новыми': 0, 'новых_почт': 0, 'новых_номеров': 0, 'из_мессенджеров': 0, 'было_без_номеров': 0,
          'было_без_почт': 0}
    примеры = []
    t0, t0_iso, проверено = time.time(), time.strftime('%Y-%m-%dT%H:%M:%S'), time.time()
    стоп = [False]

    def найти_(з):
        if стоп[0]:
            return з, None
        try:
            return з, одна(з)
        except Exception as e:  # noqa: BLE001
            print('сбой', з['inn'], repr(e)[:100], flush=True)
            return з, None
    with ThreadPoolExecutor(int(os.environ.get('KC_SKRYTYE_POTOKOV', '8'))) as ex:
        for n, (з, нов) in enumerate(ex.map(найти_, задачи), 1):
            if not ПРОБА and time.time() - проверено > 60:
                проверено = time.time()
                if KZ.пора_стоп(t0_iso):
                    стоп[0] = True
                    print('оркестратор начал шаги после агентов — стоп (резюм по отметке)', flush=True)
            if нов is None:
                continue
            if нов:
                сч['компаний_с_новыми'] += 1
                сч['новых_почт'] += sum(1 for x in нов if x.get('почта'))
                сч['новых_номеров'] += sum(1 for x in нов if x.get('номер'))
                сч['из_мессенджеров'] += sum(1 for x in нов if x.get('скрытые') == 'мессенджер')
                сч['было_без_номеров'] += not any(x.get('номер') for x in з.get('номера') or []) and any(x.get('номер') for x in нов)
                сч['было_без_почт'] += not any(x.get('почта') for x in з.get('номера') or []) and any(x.get('почта') for x in нов)
                if len(примеры) < 40:
                    примеры.append((з['inn'], нов[0].get('номер') or нов[0].get('почта'), нов[0]['скрытые'],
                                    нов[0]['контекст'][-120:]))
                    print('  пример', примеры[-1], flush=True)
            if not ПРОБА:
                if нов:
                    with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов, скрытые=time.strftime('%Y-%m-%d %H:%M')),
                                           ensure_ascii=False) + '\n')
                        f.flush()
                        os.fsync(f.fileno())
                else:
                    with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f:
                        f.write(з['inn'] + '\n')
                        f.flush()
                        os.fsync(f.fileno())
            if n % 1000 == 0:
                print('готово %d/%d за %d мин' % (n, len(задачи), (time.time() - t0) / 60), json.dumps(сч, ensure_ascii=False),
                      flush=True)
    if not ПРОБА:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
