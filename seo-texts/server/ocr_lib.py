# -*- coding: utf-8 -*-
r"""Распознавание СКАНОВ: PDF без текстового слоя.

Зачем отдельный модуль. Читать PDF мы научились 29.07 (`pypdf`), но замер
протоколов закупочных комиссий показал: четыре документа из шести — сканы, то
есть картинка без единого символа. Для таких `pypdf` честно отдаёт пустоту, и
две трети источника нам просто не видны. Это дыра в инструменте, а не в
гипотезе, и закрывать её надо инструментом.

Что стоит на сервере (проверено 30.07):
  * `tesseract` 5.5.3 — из пакета conda-forge, распакован в
    C:\sender\_ocr\tess\bin. Официальное зеркало UB Mannheim отдаёт с этого
    сервера 403, а установщик требовал бы прав; conda-forge раздаёт обычный
    архив, и права не нужны вовсе. Русские данные — tessdata_fast/rus.
  * `PyMuPDF` (fitz) — рендер страницы в картинку. Poppler и pdf2image не
    нужны: PyMuPDF рисует сам, одной библиотекой вместо трёх.
  * `pypdf` — остаётся первым разбором текстового слоя.

Порядок в `doc_text`: текстовый слой -> если его нет или он подозрительно
короток -> OCR первых страниц. Гриф «УТВЕРЖДАЮ» и состав комиссии стоят на
титуле, поэтому по умолчанию распознаём ДВЕ первые страницы, а не весь том:
на трёхстах листах ТЗ OCR стоил бы часы и ничего не добавил.

ЧЕСТНАЯ ОГОВОРКА. OCR ошибается, и ошибается именно в ФИО — там, где ошибка
дороже всего. Поэтому:
  * результат помечается как распознанный (`движок`), чтобы не выдавать его за
    прочитанный;
  * рядом кладём картинку страницы, по которой можно сверить глазами;
  * доля кириллицы и осмысленных слов — дешёвый признак того, что вышел мусор.
"""
import hashlib
import io
import os
import re
import subprocess
import sys
import threading

БАЗА = os.environ.get('OCR_HOME', r'C:\sender\_ocr\tess')
ТЕССЕРАКТ = os.path.join(БАЗА, 'bin', 'tesseract.exe')
ТЕССДАТА = os.path.join(БАЗА, 'tessdata')
ЛИБЫ = os.environ.get('OCR_LIBS', r'C:\sender\_ocrlibs')
КЭШ = os.environ.get('OCR_CACHE', r'C:\seostat\drop\ocr_cache')
КАРТИНКИ = os.environ.get('OCR_SHOTS', r'C:\seostat\drop\drop-storage\ocr_shots')

_замок = threading.Lock()


def _fitz():
    if ЛИБЫ not in sys.path:
        sys.path.insert(0, ЛИБЫ)
    import fitz  # noqa: PLC0415
    return fitz


def доступен():
    """(есть ли tesseract, есть ли русский язык, есть ли рендер)."""
    из = {'tesseract': os.path.exists(ТЕССЕРАКТ),
          'rus': os.path.exists(os.path.join(ТЕССДАТА, 'rus.traineddata'))}
    try:
        _fitz()
        из['fitz'] = True
    except Exception:  # noqa: BLE001
        из['fitz'] = False
    return из


def _среда():
    с = dict(os.environ)
    с['PATH'] = os.path.join(БАЗА, 'bin') + ';' + с.get('PATH', '')
    с['TESSDATA_PREFIX'] = ТЕССДАТА
    return с


def кириллица(t):
    """Доля кириллицы среди букв. Дешёвый признак мусора после OCR."""
    букв = re.findall(r'[^\W\d_]', t or '', re.UNICODE)
    if not букв:
        return 0.0
    кир = sum(1 for c in букв if 'а' <= c.lower() <= 'я' or c.lower() == 'ё')
    return кир / len(букв)


def ocr_картинка(png, язык='rus', psm=1, таймаут=180):
    """Текст с одной картинки. Общение с tesseract через stdin/stdout — на
    диск ничего не кладём, иначе параллельные потоки дерутся за имена файлов.

    psm=1 (а не 3) — с определением ОРИЕНТАЦИИ: половина сканов ЕИС лежит на
    боку, потому что лист клали в сканер поперёк. Для этого нужен osd.traineddata,
    и если его нет, откатываемся на psm=3, а не молчим.
    """
    if not os.path.exists(ТЕССЕРАКТ):
        return ''
    if psm == 1 and not os.path.exists(os.path.join(ТЕССДАТА, 'osd.traineddata')):
        psm = 3
    try:
        r = subprocess.run(
            [ТЕССЕРАКТ, 'stdin', 'stdout', '-l', язык, '--psm', str(psm)],
            input=png, capture_output=True, timeout=таймаут, env=_среда())
        т = r.stdout.decode('utf-8', 'replace')
        if not т.strip() and psm != 3:
            r = subprocess.run(
                [ТЕССЕРАКТ, 'stdin', 'stdout', '-l', язык, '--psm', '3'],
                input=png, capture_output=True, timeout=таймаут, env=_среда())
            т = r.stdout.decode('utf-8', 'replace')
        return т
    except Exception:  # noqa: BLE001
        return ''


def страницы_pdf(blob, сколько=2, dpi=300, шапка=0.0):
    """[(номер, png-байты)] первых страниц PDF.

    `шапка` — доля высоты сверху: гриф «УТВЕРЖДАЮ» стоит в правом верхнем углу
    титульного листа, и распознавание ОДНОЙ шапки с крупным разрешением заметно
    точнее, чем всей страницы: мелкий шрифт таблиц ниже тянет качество вниз, а
    подпись поверх грифа съедает буквы.
    """
    try:
        fitz = _fitz()
        d = fitz.open(stream=blob, filetype='pdf')
    except Exception:  # noqa: BLE001
        return []
    из = []
    try:
        for i in range(min(сколько, d.page_count)):
            try:
                стр = d[i]
                клип = None
                if шапка:
                    r = стр.rect
                    # лист может лежать на боку — тогда «верх» по короткой
                    # стороне, и обрезать надо слева, а не сверху
                    if r.width > r.height:
                        клип = fitz.Rect(r.x0, r.y0, r.x0 + r.width * шапка, r.y1)
                    else:
                        клип = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + r.height * шапка)
                pm = стр.get_pixmap(dpi=dpi, clip=клип)
                из.append((i, pm.tobytes('png')))
            except Exception:  # noqa: BLE001
                continue
    finally:
        try:
            d.close()
        except Exception:  # noqa: BLE001
            pass
    return из


# Гриф печатают ЗАГЛАВНЫМИ, и это спасает от ложных срабатываний: строчное
# «в соответствии с утверждённым планом» анкером не станет. А вот хвост слова
# OCR теряет постоянно — ровно потому, что поверх него расписываются. На живом
# скане «Обоснование НМЦК» СЗЦ «СевРАО» подпись перечеркнула «ДАЮ» и слово
# пропало целиком, хотя глазами читается без труда.
# Хвост слова берём ТОЛЬКО заглавными и только пока следом не начнётся
# строчная буква. Первая редакция шаблона ловила пробелы и перевод строки
# внутри хвоста — и на «УТВЕРЖ\nДиректор» съедала «Д» у следующего слова,
# превращая должность в «иректор». Ровно та ошибка, от которой предостерегает
# правило «обрезка должности переворачивает смысл».
_АНКЕР_OCR = re.compile(r'У[ \t]?Т[ \t]?В[ \t]?Е[ \t]?Р[ \t]?[ЖХК][А-ЯЁ]{0,4}'
                        r'(?![а-яё])')


def починить_анкер(t):
    """Привести потрёпанный OCR-ом гриф к каноническому слову.

    Так разбор грифа остаётся ОДИН — `enrich_contacts.utverzhdayu`, — а здесь
    мы лишь чиним анкер. Заводить второй экстрактор нельзя: разойдутся.
    """
    return _АНКЕР_OCR.sub('УТВЕРЖДАЮ', t or '')


def слой_pdf(blob, страниц=25):
    """Текстовый слой глазами PyMuPDF — ВТОРОЕ независимое мнение к pypdf.

    Это не дублирование: pypdf и mupdf спотыкаются на разных PDF, и часть
    «сканов» на деле оказывается документами, которые не осилил один из двух.
    Признать документ сканом можно только когда молчат оба.
    """
    try:
        fitz = _fitz()
        d = fitz.open(stream=blob, filetype='pdf')
    except Exception:  # noqa: BLE001
        return '', 0
    куски, n = [], 0
    try:
        n = d.page_count
        for i in range(min(страниц, n)):
            try:
                куски.append(d[i].get_text() or '')
            except Exception:  # noqa: BLE001
                continue
    finally:
        try:
            d.close()
        except Exception:  # noqa: BLE001
            pass
    return re.sub(r'[ \t]+', ' ', '\n'.join(куски)).strip(), n


# Ниже какой длины текстовый слой считаем отсутствующим. Титульный лист с
# грифом — это сотни символов; 200 отделяет «пусто» от «что-то есть», но
# оставляет запас на документы, где первая страница почти пустая.
ПОРОГ_СЛОЯ = int(os.environ.get('OCR_MIN_LAYER', '200'))


def разбор_pdf(blob, слой='', страниц=2, dpi=300, кэшировать=True):
    """Текст PDF с запасным путём через OCR.

    Возвращает словарь с ПОЛНОЙ историей разбора: что дал pypdf, что дал mupdf,
    признали ли сканом, что вышло из OCR. История нужна, чтобы отчёт мог
    отличить «источник пуст» от «мы не смогли прочесть» — на этой подмене за
    вчерашний день сгорели четыре замера из шести.
    """
    из = {'байт': len(blob or b''), 'слой_pypdf': len(слой or ''),
          'страниц': 0, 'слой_mupdf': 0, 'скан': False, 'ocr_симв': 0,
          'движок': 'слой', 'текст': слой or '', 'кир': кириллица(слой)}
    м_текст, стр = слой_pdf(blob, страниц=25)
    из['слой_mupdf'] = len(м_текст)
    из['страниц'] = стр
    # берём тот разбор, что дал больше — молчание одной библиотеки не приговор
    if len(м_текст) > len(из['текст']):
        из['текст'] = м_текст
        из['движок'] = 'слой:mupdf'
        из['кир'] = кириллица(м_текст)
    if len(из['текст'].strip()) >= ПОРОГ_СЛОЯ:
        return из
    # оба разбора молчат — это скан
    из['скан'] = True
    ключ = hashlib.sha1((blob or b'')[:200000]).hexdigest()
    путь = os.path.join(КЭШ, ключ + '.txt')
    if кэшировать and os.path.exists(путь):
        try:
            т = io.open(путь, encoding='utf-8', errors='replace').read()
            из.update({'текст': т, 'ocr_симв': len(т), 'движок': 'ocr:кэш',
                       'кир': кириллица(т)})
            return из
        except Exception:  # noqa: BLE001
            pass
    куски = []
    for _, png in страницы_pdf(blob, сколько=страниц, dpi=dpi):
        куски.append(ocr_картинка(png))
    # ШАПКА ПЕРВОГО ЛИСТА отдельно и крупнее: именно там гриф, и на полной
    # странице он теряется среди мелкого текста таблиц
    for _, png in страницы_pdf(blob, сколько=1, dpi=int(dpi * 1.4), шапка=0.34):
        куски.append(ocr_картинка(png, psm=4))
    т = re.sub(r'[ \t]+', ' ', '\n'.join(куски)).strip()
    из.update({'текст': т, 'ocr_симв': len(т), 'движок': 'ocr:tesseract',
               'кир': кириллица(т), 'ключ': ключ})
    if кэшировать and т:
        try:
            os.makedirs(КЭШ, exist_ok=True)
            with io.open(путь + '.tmp', 'w', encoding='utf-8') as f:
                f.write(т)
                f.flush()
                os.fsync(f.fileno())
            os.replace(путь + '.tmp', путь)
        except Exception:  # noqa: BLE001
            pass
    return из


_ПРОМПТ_ГРИФ = (
    'Перед тобой скан первой страницы закупочного документа. В правом верхнем '
    'углу может стоять гриф утверждения: слово УТВЕРЖДАЮ (или УТВЕРЖДЕНО), под '
    'ним ДОЛЖНОСТЬ утвердившего и его фамилия с инициалами.\n'
    'Верни СТРОГО JSON без пояснений: {"есть": true|false, "должность": "...", '
    '"фио": "...", "дословно": "..."}\n'
    'Правила:\n'
    '- "дословно" — точная переписка блока грифа, как напечатано;\n'
    '- должность переписывай ЦЕЛИКОМ. «Заместитель главного инженера» нельзя '
    'сокращать до «главный инженер» — это разные люди и разный вес;\n'
    '- если подпись от руки закрывает буквы, восстанавливай только то, что '
    'видно; не угадывай фамилию;\n'
    '- если грифа на странице нет, верни {"есть": false}.')


def гриф_провайдером(png, модель='claude-fable-5', таймаут=200):
    """Гриф со скана глазами модели — для страниц, где tesseract анкер потерял.

    Зачем второй распознаватель. Подпись от руки идёт ПОВЕРХ слова «УТВЕРЖДАЮ»,
    и тессеракт его теряет, хотя человек читает без усилий. Модель такие места
    читает как человек. Это же и правило владельца: тяжёлое — через
    провайдерский API, а не токенами сессии.

    Возвращает разобранный ответ или {} — молча, потому что это ЗАПАСНОЙ путь,
    и падать из-за него прогон не должен.
    """
    key = os.environ.get('PROVIDER_API_KEY', '')
    if not key or not png:
        return {}
    import base64
    import json as _json
    import urllib.request as _ur
    base = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
    тело = _json.dumps({
        'model': модель, 'max_tokens': 700, 'stream': True,
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {'type': 'base64',
                                         'media_type': 'image/png',
                                         'data': base64.b64encode(png).decode()}},
            {'type': 'text', 'text': _ПРОМПТ_ГРИФ}]}]}, ensure_ascii=False).encode()
    req = _ur.Request(base + '/v1/messages', data=тело, method='POST',
                      headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                               'content-type': 'application/json',
                               'accept': 'text/event-stream',
                               'User-Agent': 'curl/8.5.0'})
    куски = []
    try:
        with _ur.urlopen(req, timeout=таймаут) as r:
            for сырая in r:
                s = сырая.decode('utf-8', 'replace').strip()
                if not s.startswith('data:'):
                    continue
                s = s[5:].strip()
                if not s or s == '[DONE]':
                    continue
                try:
                    j = _json.loads(s)
                except Exception:  # noqa: BLE001
                    continue
                if j.get('type') == 'content_block_delta':
                    куски.append(j.get('delta', {}).get('text') or '')
    except Exception:  # noqa: BLE001
        return {}
    т = ''.join(куски).strip()
    m = re.search(r'\{.*\}', т, re.S)
    if not m:
        return {}
    try:
        import json as _j2
        return _j2.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {}


def снимок(blob, имя, страница=0, dpi=170):
    """Картинку первой страницы — в раздаваемый дропом каталог, чтобы
    распознанное можно было сверить ГЛАЗАМИ, а не поверить на слово."""
    try:
        os.makedirs(КАРТИНКИ, exist_ok=True)
        стр = страницы_pdf(blob, сколько=страница + 1, dpi=dpi)
        if len(стр) <= страница:
            return ''
        п = os.path.join(КАРТИНКИ, имя)
        with open(п, 'wb') as f:
            f.write(стр[страница][1])
            f.flush()
            os.fsync(f.fileno())
        return п
    except Exception:  # noqa: BLE001
        return ''
