# -*- coding: utf-8 -*-
"""Чем на сервере читать PDF: что уже есть, что ставится, что берёт кириллицу.

PDF нас касается дважды и оба раза больно: техдокументация закупок в ЕИС часто
именно PDF (гриф «УТВЕРЖДАЮ» с фамилией главного инженера мы из-за этого
пропускали честно, но пропускали), и годовые отчёты АО, где правление и совет
директоров перечислены поимённо.

Проверяем по порядку: есть ли готовая библиотека; ставится ли pypdf (он на
чистом питоне, компилятор не нужен); и главное — ВЫТАСКИВАЕТ ЛИ ОНА РУССКИЙ
ТЕКСТ. Русские PDF часто идут с собственной кодировкой шрифта, и библиотека,
которая на английском работает, на кириллице может вернуть кашу. Поэтому
меряем не «импортировалось», а долю русских букв в результате.
"""
import io
import json
import re
import subprocess
import sys
import urllib.request

ПРОБНЫЙ = ('https://www.e-disclosure.ru/portal/files.aspx?id=282&type=2',)


def есть(имя):
    try:
        __import__(имя)
        return True
    except Exception:  # noqa: BLE001
        return False


def поставить(пакет):
    try:
        p = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-input',
                            '--disable-pip-version-check', пакет],
                           capture_output=True, text=True, timeout=300)
        return {'код': p.returncode, 'хвост': (p.stdout or p.stderr or '')[-300:]}
    except Exception as ex:  # noqa: BLE001
        return {'ошибка': f'{type(ex).__name__}: {str(ex)[:120]}'}


def доля_кириллицы(t):
    if not t:
        return 0.0
    рус = len(re.findall(r'[а-яёА-ЯЁ]', t))
    букв = len(re.findall(r'[^\W\d_]', t, re.UNICODE)) or 1
    return round(рус / букв, 3)


def main():
    out = {'python': sys.version.split()[0], 'было': {}}
    for имя in ('pypdf', 'PyPDF2', 'pdfminer', 'fitz', 'pdfplumber'):
        out['было'][имя] = есть(имя)
    if not out['было'].get('pypdf'):
        out['установка_pypdf'] = поставить('pypdf')
        out['после_установки'] = есть('pypdf')
    # берём реальный PDF: свой же документ из ЕИС или переданный аргументом
    url = next((a for a in sys.argv[1:] if a.startswith('http')), '')
    if not url:
        out['подсказка'] = 'дайте ссылку на живой PDF аргументом'
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        сырое = urllib.request.urlopen(req, timeout=60).read()
        out['байт'] = len(сырое)
        out['это_pdf'] = сырое[:5] == b'%PDF-'
    except Exception as ex:  # noqa: BLE001
        out['скачивание'] = f'{type(ex).__name__}: {str(ex)[:120]}'
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    if есть('pypdf'):
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(сырое))
            t = '\n'.join((p.extract_text() or '') for p in r.pages[:6])
            out['pypdf'] = {'страниц': len(r.pages), 'символов': len(t),
                            'доля_кириллицы': доля_кириллицы(t),
                            'начало': re.sub(r'\s+', ' ', t)[:300]}
        except Exception as ex:  # noqa: BLE001
            out['pypdf'] = f'{type(ex).__name__}: {str(ex)[:140]}'
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])


if __name__ == '__main__':
    main()
