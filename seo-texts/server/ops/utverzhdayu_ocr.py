# -*- coding: utf-8 -*-
r"""ПЕРЕМЕР грифа «УТВЕРЖДАЮ» починенным инструментом (способ А5, замер 3).

Почему меряем в третий раз.
  * Замер 1 (29.07, `utverzhdayu_stream.jsonl`): 49 находок в потоке, 29 человек
    в базе, 1 технарь. ОТМЕНЁН — тогда PDF не читались вовсе, а техзадание в
    ЕИС выкладывают в PDF чаще, чем в Word. Мерили не источник, а свою слепоту.
  * Замер 2 (`utv_pdf.jsonl` 436 ИНН, `utv_tech.jsonl` 555, `utv_subj.jsonl`
    419) — уже с чтением PDF, и все три дали РОВНО НОЛЬ людей. Ноль на полутора
    тысячах компаний после починки, которая должна была прибавить, — это не
    ответ источника, это признак дефекта. Потоки хранят только `inn` и
    `людей`, так что где потерялось — по ним не сказать вообще.

Отсюда главное требование к этому прогону: НЕ «сколько нашли», а ГДЕ ТЕРЯЕМ.
Пишем воронку целиком, шаг за шагом: RSS -> карточки -> привязка по ИНН ->
документы -> формат файла -> текстовый слой -> скан -> OCR -> анкер грифа ->
ФИО и должность -> запись. Ноль на любом шаге сразу виден как ноль ИМЕННО
этого шага, а не как «источник пуст».

Что нового по сравнению с замерами 1-2:
  * сканы читаются (`ocr_lib`, tesseract 5.5.3 + rus, рендер PyMuPDF);
  * страницы, где подпись от руки съела слово «УТВЕРЖДАЮ», уходят на второй
    распознаватель — провайдерскую модель (правило владельца: тяжёлое через
    провайдерский API);
  * карточки без ИНН на странице отбрасываются (рубеж привязки закрыт);
  * предмет закупки НЕ ФИЛЬТРУЕТ, а СОРТИРУЕТ: технические закупки читаем
    первыми, но остальные не выбрасываем — иначе повторим замер 2, где отбор
    мог съесть всю выборку молча.

Долговечность: enrich.db (add_person) И поток с fsync. Возвращаемый JSON —
не хранилище: песочница при рестарте откатывается.

Резюмируемо по ИНН из потока. Запуск:
    python utverzhdayu_ocr.py [бюджет_сек] [потоков] [--apply] [--inn ИНН]
"""
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
sys.path.insert(0, r'C:\sender\_ocrlibs')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402
import ocr_lib as OL             # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 330.0
ПОТОКОВ = int(_поз[1]) if len(_поз) > 1 else 4
ПРИМЕНИТЬ = '--apply' in sys.argv
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
ПОТОК = r'C:\seostat\drop\utv_ocr_stream.jsonl'
ДОКИ = r'C:\seostat\drop\utv_ocr_docs.jsonl'
НАЧАЛО = time.time()

КАРТОЧЕК = int(os.environ.get('UTV_CARDS', '2'))     # карточек на компанию
ФАЙЛОВ = int(os.environ.get('UTV_FILES', '3'))       # файлов на карточку
СКАН_RSS = int(os.environ.get('UTV_SCAN', '6'))      # карточек из RSS открыть
ПРОВАЙДЕР = os.environ.get('UTV_PROVIDER', '1') != '0'

db = EDB.EnrichDB()
e = db.cx


def цели():
    из, было = [], set()
    БАЗА = json.load(open(r'C:\sender\_ops\sales_base.json', encoding='utf-8'))
    for строки in БАЗА.values():
        for x in строки:
            i = str(x.get('inn') or '').strip()
            if i and i not in было:
                было.add(i)
                из.append(i)
    return из


сделано = set()
if os.path.exists(ПОТОК):
    for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
        try:
            j = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        # в резюм попадают и компании с ошибкой RSS: иначе прогон вечно топчется
        # на одних и тех же недоступных, а до остальных очередь не доходит
        if j.get('inn'):
            сделано.add(str(j['inn']))
todo = [ОДИН] if ОДИН else [i for i in цели() if i not in сделано]

замок = threading.Lock()
ф = io.open(ПОТОК, 'a', encoding='utf-8')
фд = io.open(ДОКИ, 'a', encoding='utf-8')

СЧ = {
    'компаний': 0, 'rss_ошибка': 0, 'rss_пусто': 0, 'карточек_из_rss': 0,
    'карточек_привязка_ок': 0, 'карточек_привязка_нет': 0,
    'карточек_технических': 0, 'карточек_открыто': 0,
    'док_ссылок': 0, 'док_годных_форматов': 0, 'док_скачано': 0,
    'док_ноль_байт': 0, 'док_ошибка_сети': 0,
    'pdf': 0, 'docx': 0, 'rtf': 0, 'txt': 0, 'прочее': 0,
    'pdf_со_слоем': 0, 'pdf_скан': 0, 'скан_ocr_дал_текст': 0,
    'скан_ocr_пусто': 0, 'провайдер_вызовов': 0, 'провайдер_нашёл': 0,
    'анкер_есть': 0, 'грифов_разобрано': 0, 'людей_с_фио': 0,
    'записано': 0, 'техЛПР': 0, 'ошибок': 0,
}


def плюс(k, n=1):
    with замок:
        СЧ[k] = СЧ.get(k, 0) + n


def печать(метка):
    with замок:
        print(json.dumps({'метка': метка, 'секунд': round(time.time() - НАЧАЛО),
                          'осталось_целей': len(todo), **СЧ},
                         ensure_ascii=False))
        sys.stdout.flush()


_ГОДЕН = re.compile(r'\.(docx?|rtf|txt|pdf)(?:\W|$)', re.I)


def _вес(имя):
    """Техзадание и документация раньше извещения: гриф ставят на всех, но
    в ТЗ подписант — профильный руководитель, а в извещении контрактный."""
    н = (имя or '').lower()
    if 'техническ' in н or re.search(r'\bтз\b', н):
        return 0
    if 'документац' in н or 'требован' in н:
        return 1
    if 'извещен' in н:
        return 3
    return 2


def разобрать_гриф(текст, скан, png_шапки, зап):
    """[{person, post, движок}] — общий разбор для слоя, OCR и провайдера."""
    из = []
    # 1. текст как есть (текстовый слой)
    гр = EC.utverzhdayu(текст or '')
    if гр:
        плюс('анкер_есть')
        for x in гр:
            x['движок'] = 'слой' if not скан else 'ocr:tesseract'
        из += гр
    elif скан:
        # 2. OCR потрепал анкер — чиним слово и пробуем тем же разбором
        т2 = OL.починить_анкер(текст or '')
        гр = EC.utverzhdayu(т2)
        if гр:
            плюс('анкер_есть')
            for x in гр:
                x['движок'] = 'ocr:анкер-починен'
            из += гр
    зап['анкер'] = bool(из)
    # 3. Скан без анкера — второй распознаватель. Подпись от руки идёт ПОВЕРХ
    #    слова «УТВЕРЖДАЮ», tesseract его теряет, а человек читает свободно.
    if not из and скан and ПРОВАЙДЕР and png_шапки:
        плюс('провайдер_вызовов')
        отв = OL.гриф_провайдером(png_шапки)
        зап['провайдер'] = отв
        if отв.get('есть') and (отв.get('фио') or отв.get('должность')):
            плюс('провайдер_нашёл')
            из.append({'person': (отв.get('фио') or '').strip(),
                       'post': (отв.get('должность') or '').strip(),
                       'движок': 'провайдер'})
    return из


def работа(inn):
    if time.time() - НАЧАЛО > БЮДЖЕТ:
        return
    итог = {'inn': inn, 'ts': int(time.time()), 'карточек': 0, 'файлов': 0,
            'сканов': 0, 'людей': 0, 'техЛПР': 0, 'люди': []}
    try:
        z = EC.find_zakupki_contacts(inn, max_cards=СКАН_RSS)
        if not z:
            итог['err'] = 'find_zakupki_contacts вернул None'
            плюс('rss_ошибка')
        elif z.get('error'):
            итог['err'] = str(z['error'])[:110]
            плюс('rss_ошибка')
        else:
            карточки = list(z.get('cards') or [])
            итог['rss_items'] = z.get('rss_items')
            плюс('карточек_из_rss', len(карточки))
            if not карточки:
                плюс('rss_пусто')
            # рубеж привязки: ИНН обязан стоять НА СТРАНИЦЕ карточки
            годные = [c for c in карточки if c.get('inn_на_странице')]
            плюс('карточек_привязка_ок', len(годные))
            плюс('карточек_привязка_нет', len(карточки) - len(годные))
            итог['карточек_годных'] = len(годные)

            def тех(c):
                s = (c.get('title') or '') + ' ' + (c.get('subject') or '')
                return bool(EC._ЗАКУПКА_ТЕХНИЧЕСКАЯ.search(s))

            плюс('карточек_технических', sum(1 for c in годные if тех(c)))
            # СОРТИРУЕМ, а не фильтруем: технические первыми, но если их нет —
            # читаем что есть. Замер 2 мог умереть именно на жёстком отборе.
            годные.sort(key=lambda c: (0 if тех(c) else 1))
            for c in годные[:КАРТОЧЕК]:
                if time.time() - НАЧАЛО > БЮДЖЕТ:
                    break
                плюс('карточек_открыто')
                итог['карточек'] += 1
                time.sleep(0.8)
                файлы = EC.eis_documents(c.get('url') or '')
                плюс('док_ссылок', len(файлы))
                файлы = [f for f in файлы if _ГОДЕН.search(f[0] or '')]
                плюс('док_годных_форматов', len(файлы))
                файлы.sort(key=lambda f: _вес(f[0]))
                for имя, url in файлы[:ФАЙЛОВ]:
                    if time.time() - НАЧАЛО > БЮДЖЕТ:
                        break
                    итог['файлов'] += 1
                    зап = {'inn': inn, 'имя': имя, 'url': url[:250],
                           'карточка': (c.get('url') or '')[:150],
                           'предмет': (c.get('subject') or '')[:120],
                           'техническая': тех(c)}
                    try:
                        time.sleep(0.7)
                        blob = EC._eis_get(url, raw=True)
                    except Exception as ex:  # noqa: BLE001
                        зап['err'] = f'{type(ex).__name__} {str(ex)[:70]}'
                        плюс('док_ошибка_сети')
                        сброс(фд, зап)
                        continue
                    зап['байт'] = len(blob or b'')
                    if not blob:
                        плюс('док_ноль_байт')
                        зап['err'] = 'ноль байт'
                        сброс(фд, зап)
                        continue
                    плюс('док_скачано')
                    текст, скан, png = '', False, None
                    if blob[:4] == b'%PDF':
                        плюс('pdf')
                        слой = EC._pdf_text(blob)
                        р = OL.разбор_pdf(blob, слой=слой, страниц=2)
                        зап.update({k: v for k, v in р.items() if k != 'текст'})
                        текст, скан = р.get('текст') or '', bool(р.get('скан'))
                        if скан:
                            плюс('pdf_скан')
                            итог['сканов'] += 1
                            if len(текст.strip()) > 100:
                                плюс('скан_ocr_дал_текст')
                            else:
                                плюс('скан_ocr_пусто')
                            стр = OL.страницы_pdf(blob, сколько=1, dpi=190,
                                                  шапка=0.34)
                            png = стр[0][1] if стр else None
                        else:
                            плюс('pdf_со_слоем')
                    elif blob[:2] == b'PK':
                        плюс('docx')
                        текст = EC._docx_text(blob)
                    elif blob[:5] == b'{\\rtf':
                        плюс('rtf')
                        текст = EC._rtf_text(blob)
                    else:
                        проба = blob[:3000].decode('cp1251', 'replace')
                        печ = sum(1 for ch in проба
                                  if ch.isprintable() or ch in '\n\r\t')
                        if проба and печ / len(проба) >= 0.85:
                            плюс('txt')
                            текст = проба
                        else:
                            плюс('прочее')
                            зап['голова'] = repr(blob[:10])
                    зап['симв'] = len(текст or '')
                    гр = разобрать_гриф(текст, скан, png, зап)
                    зап['грифы'] = гр
                    if гр:
                        плюс('грифов_разобрано', len(гр))
                    for ч in гр:
                        if not (ч.get('person') or '').strip():
                            continue
                        плюс('людей_с_фио')
                        роль = EDB.EnrichDB._canon_role(ч.get('post') or '')
                        тех_ли = роль in EDB.EnrichDB.TECH_ROLES
                        итог['люди'].append(
                            {'фио': ч['person'], 'должность': ч.get('post'),
                             'роль': роль, 'тех': тех_ли,
                             'движок': ч.get('движок'), 'файл': имя[:60],
                             'url': url[:200]})
                        итог['людей'] += 1
                        if тех_ли:
                            итог['техЛПР'] += 1
                            плюс('техЛПР')
                        if ПРИМЕНИТЬ:
                            with замок:
                                try:
                                    db.add_person(
                                        inn, ч['person'],
                                        post=ч.get('post') or '',
                                        source='zakupki:утверждаю-ocr',
                                        source_url=url)
                                    СЧ['записано'] = СЧ.get('записано', 0) + 1
                                except Exception as ex:  # noqa: BLE001
                                    зап['ошибка_записи'] = str(ex)[:90]
                    сброс(фд, зап)
    except Exception as ex:  # noqa: BLE001
        итог.setdefault('err', f'{type(ex).__name__}: {str(ex)[:90]}')
        плюс('ошибок')
    плюс('компаний')
    with замок:
        try:
            e.commit()
        except Exception:  # noqa: BLE001
            pass
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())


def сброс(поток, зап):
    with замок:
        поток.write(json.dumps(зап, ensure_ascii=False) + '\n')
        поток.flush()
        os.fsync(поток.fileno())


печать('старт')
try:
    with ThreadPoolExecutor(max_workers=ПОТОКОВ) as пул:
        list(пул.map(работа, todo))
except Exception as ex:  # noqa: BLE001
    print('пул упал:', type(ex).__name__, str(ex)[:200])
ф.close()
фд.close()
печать('итог')
sys.stdout.flush()
os._exit(0)
