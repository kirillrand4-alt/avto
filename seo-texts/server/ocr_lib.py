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


def ocr_картинка(png, язык='rus', psm=3, таймаут=180):
    """Текст с одной картинки. Общение с tesseract через stdin/stdout — на
    диск ничего не кладём, иначе параллельные потоки дерутся за имена файлов."""
    if not os.path.exists(ТЕССЕРАКТ):
        return ''
    try:
        r = subprocess.run(
            [ТЕССЕРАКТ, 'stdin', 'stdout', '-l', язык, '--psm', str(psm)],
            input=png, capture_output=True, timeout=таймаут, env=_среда())
        return r.stdout.decode('utf-8', 'replace')
    except Exception:  # noqa: BLE001
        return ''


def страницы_pdf(blob, сколько=2, dpi=300):
    """[(номер, png-байты)] первых страниц PDF."""
    try:
        fitz = _fitz()
        d = fitz.open(stream=blob, filetype='pdf')
    except Exception:  # noqa: BLE001
        return []
    из = []
    try:
        for i in range(min(сколько, d.page_count)):
            try:
                pm = d[i].get_pixmap(dpi=dpi)
                из.append((i, pm.tobytes('png')))
            except Exception:  # noqa: BLE001
                continue
    finally:
        try:
            d.close()
        except Exception:  # noqa: BLE001
            pass
    return из


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
