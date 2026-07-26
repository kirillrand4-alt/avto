# -*- coding: utf-8 -*-
"""Парсинг CSV/XLSX и валидация: граничные случаи, из-за которых реальные выгрузки
ломаются молча (Excel-числа, cp1251, дубли, шапка не в первой строке, лимиты)."""
import io

import panel_core as core


def _csv(text):
    return text.encode('utf-8')


def test_csv_semicolon_basic():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Название\n7701234567;ООО Ромашка\n500100732259;ИП Иванов\n'))
    assert out['error'] == ''
    assert [r['inn'] for r in out['accepted']] == ['7701234567', '500100732259']
    assert out['accepted'][0]['name'] == 'ООО Ромашка'
    assert out['rejected'] == []


def test_csv_comma_and_latin_aliases():
    out = core.parse_companies_file('a.csv', _csv(
        'inn,name\n7701234567,Ромашка\n'))
    assert out['error'] == ''
    assert len(out['accepted']) == 1


def test_csv_alias_naimenovanie_case_insensitive():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Наименование\n7701234567;Завод\n'))
    assert out['accepted'][0]['name'] == 'Завод'


def test_csv_cp1251():
    blob = 'ИНН;Название\n7701234567;Пермский завод\n'.encode('cp1251')
    out = core.parse_companies_file('a.csv', blob)
    assert out['error'] == ''
    assert out['accepted'][0]['name'] == 'Пермский завод'


def test_header_not_first_row():
    # выгрузки часто несут «шапку отчёта» до заголовков колонок
    out = core.parse_companies_file('a.csv', _csv(
        'Отчёт от 26.07.2026;\n;\nИНН;Название\n7701234567;Ромашка\n'))
    assert out['error'] == ''
    assert len(out['accepted']) == 1


def test_bad_inn_rejected_with_reason():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Название\n123;Короткий\nabcdefghij;Буквы\n77012345678;11 цифр\n'))
    assert out['accepted'] == []
    assert len(out['rejected']) == 3
    assert all(x['reason'] == 'ИНН не 10/12 цифр' for x in out['rejected'])
    # номер строки файла — 1-based, после заголовка
    assert out['rejected'][0]['row'] == 2


def test_empty_name_rejected():
    out = core.parse_companies_file('a.csv', _csv('ИНН;Название\n7701234567;\n'))
    assert out['accepted'] == []
    assert out['rejected'][0]['reason'] == 'пустое название'


def test_dedup_keeps_first_and_reports_duplicate():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Название\n7701234567;Первая\n7701234567;Вторая\n'))
    assert len(out['accepted']) == 1
    assert out['accepted'][0]['name'] == 'Первая'
    assert 'дубль ИНН' in out['rejected'][0]['reason']


def test_inn_with_spaces_and_excel_float():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Название\n77 0123 4567;Пробелы\n7701234568.0;Флоат\n'))
    assert [r['inn'] for r in out['accepted']] == ['7701234567', '7701234568']


def test_empty_rows_skipped_silently():
    out = core.parse_companies_file('a.csv', _csv(
        'ИНН;Название\n\n;;\n7701234567;Ромашка\n'))
    assert len(out['accepted']) == 1
    assert out['rejected'] == []


def test_no_header_is_fatal_error():
    out = core.parse_companies_file('a.csv', _csv('a;b\n1;2\n'))
    assert 'Не найдены колонки' in out['error']


def test_wrong_extension_rejected():
    out = core.parse_companies_file('a.exe', b'x')
    assert 'csv' in out['error']


def test_size_limit(monkeypatch):
    monkeypatch.setattr(core, 'MAX_BYTES', 100)
    out = core.parse_companies_file('a.csv', b'x' * 101)
    assert 'лимита' in out['error']


def test_row_limit_reported(monkeypatch):
    monkeypatch.setattr(core, 'MAX_ROWS', 2)
    body = 'ИНН;Название\n' + ''.join(
        f'770123456{i};Компания {i}\n' for i in range(5))
    out = core.parse_companies_file('a.csv', _csv(body))
    assert len(out['accepted']) == 2
    assert any('превышен лимит' in x['reason'] for x in out['rejected'])


def test_xlsx_with_numeric_inn():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['ИНН', 'Название'])
    ws.append([7701234567, 'Из Excel'])        # ИНН числом — типовой случай
    ws.append(['500100732259', 'Строкой'])
    buf = io.BytesIO()
    wb.save(buf)
    out = core.parse_companies_file('a.xlsx', buf.getvalue())
    assert out['error'] == ''
    assert [r['inn'] for r in out['accepted']] == ['7701234567', '500100732259']
