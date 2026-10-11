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


def разбор(h, почты=True, обфуск=True):
    """(почты {адрес: (контекст, как)}, номера {ключ: (номер, доб, контекст)}) страницы."""
    h = KK.без_длинного(h)
    текст = KK.MP.в_текст(h) + KK.json_текст(h)
    п, н = {}, {}
    if почты:
        for x in KP.почты(h, текст):
            п.setdefault(x['почта'].lower(), (x.get('контекст') or '', ''))
    if почты and обфуск:
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
    # 11.10: WhatsApp в подвале — метка на каждой странице сайта; 8 мин на 1000 компаний -> свои страницы с меткой,
    # контакты/реквизиты/главная первыми, не больше 6; обфускацию почт (PI.найти) уже доизвлекали — без неё
    стр_ = [x for x in кэш_с_меткой(з['inn']) if x.get('html') and МЕТКА.search(x['html']) and
            ((x.get('url') or '') in свои_стр or MN.домен(x.get('url') or '') == сайт_дом)]
    стр_.sort(key=lambda x: (not re.search(r'(?i)kontakt|contact|контакт|svyaz|rekviz', x.get('url') or ''),
                             len((x.get('url') or '').rstrip('/').split('/'))))
    for стр in стр_[:6]:
        u, h = стр.get('url') or '', стр.get('html') or ''
        р = TI.раскрыть(h)
        п1, н1 = разбор(р, обфуск=False)
        п0, н0 = разбор(h, почты=False) if р != h else (п1, н1)
        # почты — против записи (доизвлечение почт уже прошло тем же разбором; новое — раскрытое и «mailto:%20адрес»),
        # номера — ещё и против разбора без раскрытия (лишние номера страницы доизвлечение отсекло пределом)
        for e, (кт, как) in п1.items():
            if e in есть_п or e in нов or not PI.годный(e):
                continue
            нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '',
                      'скрытые': как or ('js-коды/mailto' if р != h else 'mailto/повтор разбора')}
        for к, (номер, доб, кт) in н1.items():
            if к in н0 or к in есть_н or (not доб and к.split('|')[0] in есть_ц) or к in нов:
                continue
            нов[к] = {'номер': номер, 'доб': доб, 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '',
                      'скрытые': 'мессенджер' if re.search(r'WhatsApp|Viber', кт[150:]) else 'js-коды'}
    return list(нов.values())[:30]


ДОЛЯ = os.environ.get('KC_SKRYTYE_DOLYA', '')  # «k/N» — отдельный процесс на долю ИНН, запись в свой файл (слияние потом)
if ДОЛЯ:
    ВЫХОД_ЗАП = os.path.join(DIR, НАБОР + '-skrytye-dolya-%s.jsonl' % ДОЛЯ.split('/')[0])
    СДЕЛАНО_ЗАП = СДЕЛАНО + '.' + ДОЛЯ.split('/')[0]
else:
    ВЫХОД_ЗАП, СДЕЛАНО_ЗАП = ВЫХОД, СДЕЛАНО
РЕЖИМ = os.environ.get('KC_SKRYTYE_REZHIM', '')  # 'zenka' — разбор страниц, которые принесла Зенка
СУРРОГАТ = os.path.join(DIR, НАБОР + '-zenno-surrogat.json')


def _кэш_файла(ключ):
    п = os.path.join(KK.КЭШ_СТРАНИЦ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', ключ or ''))
    try:
        with open(п, 'rb') as f:
            return json.loads(zlib.decompress(f.read(), 47).decode('utf-8', 'replace')) or {}
    except Exception:  # noqa: BLE001
        return {}


def одна_зенка(з, суррогаты):
    """11.10: приёмник Зенки (zenno_most.priyom) кладёт страницы в кэш и только — в обход meyer7 они не попадают
    (обход уже отметил компанию). Страницы своего домена из кэша компании (если его писала Зенка) и из кэша
    суррогатного ключа («САЙТ:»/BY — приёмник берёт только цифровые ключи) -> почты и номера против записи."""
    сайт_дом = MN.домен(з.get('сайт') or '')
    стр = []
    д = _кэш_файла(з['inn'])
    if д.get('istochnik') == 'zenno':
        стр += д.get('pages') or []
    for кл in суррогаты:
        стр += _кэш_файла(кл).get('pages') or []
    есть_п = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта')}
    есть_н = {ключ_н(x.get('номер'), x.get('доб')) for x in з.get('номера') or [] if x.get('номер')}
    есть_ц = {к.split('|')[0] for к in есть_н}
    нов, свои = {}, {}
    for x in стр:
        u, h = x.get('url') or '', x.get('html') or ''
        if not h or MN.домен(u) != сайт_дом:
            continue
        свои[u] = h
        п1, н1 = разбор(TI.раскрыть(h))
        for e, (кт, как) in п1.items():
            if e not in есть_п and e not in нов and PI.годный(e):
                нов[e] = {'почта': e, 'доб': '', 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '', 'зенка': 1}
        for к, (номер, доб, кт) in н1.items():
            if к not in есть_н and not (not доб and к.split('|')[0] in есть_ц) and к not in нов:
                нов[к] = {'номер': номер, 'доб': доб, 'страницы': [u], 'контекст': кт, 'фио': '', 'должность': '', 'зенка': 1}
    if свои and суррогаты:
        try:  # страницы суррогата — в кэш самой компании (паспорт, проверка сайта, ревизии их видят)
            KK.в_кэш(з['inn'], свои, сайт=з.get('сайт') or '')
        except Exception:  # noqa: BLE001
            pass
    return list(нов.values())[:40], list(свои)


def main_зенка():
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    карта = json.load(io.open(СУРРОГАТ, encoding='utf-8')) if os.path.exists(СУРРОГАТ) else {}
    сур = {}
    for кл, i in карта.items():
        сур.setdefault(i, []).append(кл)
    сделано = set(io.open(СДЕЛАНО + '.zenka', encoding='utf-8').read().split()) if os.path.exists(СДЕЛАНО + '.zenka') else set()
    кандидаты = [з for з in последняя.values() if з.get('сайт') and not з.get('зенка_разбор') and з['inn'] not in сделано]

    def зенкин(з):  # кэш писала Зенка — метка в конце файла (после страниц), проверка без разбора JSON
        if з['inn'] in сур:
            return True
        п = os.path.join(KK.КЭШ_СТРАНИЦ, '%s.json.gz' % re.sub(r'[^\w.-]', '_', з['inn']))
        try:
            with open(п, 'rb') as f:
                return b'"istochnik": "zenno"' in zlib.decompress(f.read(), 47)[-3000:]
        except Exception:  # noqa: BLE001
            return False
    with ThreadPoolExecutor(8) as ex:
        задачи = [з for з, да in zip(кандидаты, ex.map(зенкин, кандидаты)) if да]
    print('компаний со страницами Зенки', len(задачи), 'из них суррогатных', sum(1 for з in задачи if з['inn'] in сур), flush=True)
    сч = {'компаний_с_новыми': 0, 'новых_почт': 0, 'новых_номеров': 0, 'было_без_номеров': 0, 'было_без_почт': 0,
          'итог_был_не_ok': 0}
    t0 = time.time()
    for n, з in enumerate(задачи, 1):
        try:
            нов, свои = одна_зенка(з, сур.get(з['inn'], []))
        except Exception as e:  # noqa: BLE001
            print('сбой', з['inn'], repr(e)[:100], flush=True)
            continue
        if нов:
            сч['компаний_с_новыми'] += 1
            сч['новых_почт'] += sum(1 for x in нов if x.get('почта'))
            сч['новых_номеров'] += sum(1 for x in нов if x.get('номер'))
            сч['было_без_номеров'] += not any(x.get('номер') for x in з.get('номера') or []) and any(x.get('номер') for x in нов)
            сч['было_без_почт'] += not any(x.get('почта') for x in з.get('номера') or []) and any(x.get('почта') for x in нов)
            сч['итог_был_не_ok'] += з.get('итог') != 'ok'
            if n <= 400 and сч['компаний_с_новыми'] <= 15:
                print('  пример', з['inn'], (нов[0].get('номер') or нов[0].get('почта')), нов[0]['контекст'][-100:], flush=True)
            if not ПРОБА:
                доп = {'итог': 'ok', 'итог_был': з.get('итог')} if з.get('итог') != 'ok' else {}
                with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов, зенка_разбор=time.strftime('%Y-%m-%d %H:%M'),
                                            страницы=(з.get('страницы') or []) + [[u, 'зенка'] for u in свои[:20]], **доп),
                                       ensure_ascii=False) + '\n')
                    f.flush()
                    os.fsync(f.fileno())
        elif not ПРОБА:
            with io.open(СДЕЛАНО + '.zenka', 'a', encoding='utf-8') as f:
                f.write(з['inn'] + '\n')
                f.flush()
                os.fsync(f.fileno())
    if not ПРОБА:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


def main():
    последняя = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            последняя[з['inn']] = з
    сделано = set()
    for ф in (СДЕЛАНО, СДЕЛАНО_ЗАП):
        if os.path.exists(ф):
            сделано |= set(io.open(ф, encoding='utf-8').read().split())
    if ДОЛЯ and os.path.exists(ВЫХОД_ЗАП):
        for s in io.open(ВЫХОД_ЗАП, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['inn'])
            except (ValueError, KeyError):
                pass
    задачи = [з for з in последняя.values() if з.get('итог') == 'ok' and з.get('сайт') and not з.get('скрытые')
              and з['inn'] not in сделано]
    if ДОЛЯ:
        k, N = (int(x) for x in ДОЛЯ.split('/'))
        задачи = [з for з in задачи if zlib.crc32(з['inn'].encode('utf-8')) % N == k]
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
                    with io.open(ВЫХОД_ЗАП, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + нов, скрытые=time.strftime('%Y-%m-%d %H:%M')),
                                           ensure_ascii=False) + '\n')
                        f.flush()
                        os.fsync(f.fileno())
                else:
                    with io.open(СДЕЛАНО_ЗАП, 'a', encoding='utf-8') as f:
                        f.write(з['inn'] + '\n')
                        f.flush()
                        os.fsync(f.fileno())
            if n % 1000 == 0:
                print('готово %d/%d за %d мин' % (n, len(задачи), (time.time() - t0) / 60), json.dumps(сч, ensure_ascii=False),
                      flush=True)
    if not ПРОБА and not ДОЛЯ:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    сч['минут'] = round((time.time() - t0) / 60, 1)
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


def слить():
    """Находки долей — в файл обхода одним писателем (дозапись из нескольких процессов в один файл на Windows не
    атомарна). Новые контакты (с полем «скрытые») добавляются к ТЕКУЩЕЙ последней записи компании — если после чтения
    долей её успел переписать другой шаг, его изменения не теряются. Запускать, когда файл обхода никто не пишет.
    Слитые файлы долей и отметки — в .slito."""
    посл = {}
    for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        if з.get('inn'):
            посл[з['inn']] = з
    файлы = [ф for ф in sorted(os.listdir(DIR)) if re.fullmatch(re.escape(НАБОР) + r'-skrytye-dolya-\d+\.jsonl', ф)]
    нов_по = {}
    for ф in файлы:
        for s in io.open(os.path.join(DIR, ф), encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            нов_по.setdefault(з['inn'], []).extend(x for x in з.get('номера') or [] if x.get('скрытые'))
    сч = {'компаний': 0, 'контактов': 0}
    with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
        for i, нов in нов_по.items():
            з = посл.get(i)
            if not з:
                continue
            есть = {(x.get('почта') or '').lower() for x in з.get('номера') or [] if x.get('почта')} | \
                   {ключ_н(x.get('номер'), x.get('доб')) for x in з.get('номера') or [] if x.get('номер')}
            доб_ = [x for x in нов if ((x.get('почта') or '').lower() if x.get('почта') else ключ_н(x.get('номер'), x.get('доб')))
                    not in есть]
            if not доб_:
                continue
            f.write(json.dumps(dict(з, номера=(з.get('номера') or []) + доб_, скрытые=time.strftime('%Y-%m-%d %H:%M')),
                               ensure_ascii=False) + '\n')
            сч['компаний'] += 1
            сч['контактов'] += len(доб_)
        f.flush()
        os.fsync(f.fileno())
    for ф in файлы:
        os.replace(os.path.join(DIR, ф), os.path.join(DIR, ф + '.slito'))
    for ф in sorted(os.listdir(DIR)):  # отметки «без находок» долей — в общую
        if re.fullmatch(re.escape(os.path.basename(СДЕЛАНО)) + r'\.\d+', ф):
            with io.open(СДЕЛАНО, 'a', encoding='utf-8') as f:
                f.write(io.open(os.path.join(DIR, ф), encoding='utf-8').read())
                f.flush()
                os.fsync(f.fileno())
            os.replace(os.path.join(DIR, ф), os.path.join(DIR, ф + '.slito'))
    shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', os.path.basename(ВЫХОД)))
    print('===ИТОГ===')
    print('слито', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    {'zenka': main_зенка, 'slit': слить}.get(РЕЖИМ, main)()
