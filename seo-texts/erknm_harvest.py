# -*- coding: utf-8 -*-
"""Выгрузка контрольных мероприятий по нашим ИНН из открытых данных ЕРКНМ.

Зачем. Реестр ЭПБ говорит, что машина отработала срок. ЕРКНМ говорит, что **пришёл
надзор**. Связь проверена на ПАО «НЛМК»: 26.05.2026 экспертиза дала вывод «не
соответствует» по турбокомпрессору К-3000-61-1, а 05.06.2026 в реестре проверок появилось
предостережение с прямой ссылкой на это заключение. Десять дней между документами.

Раньше был разобран один месяц на 12 % и уже дал 163 записи по 65 предприятиям из 347.
Здесь берутся все доступные месяцы целиком.

Как. Архивы по 230–340 МБ, семь месяцев — это 2,1 ГБ, держать их одновременно негде и
незачем. Каждый месяц качается, разбирается потоком прямо из ZIP без распаковки на диск
и удаляется. В памяти висит только текущий XML-элемент.

Использование:
    python3 erknm_harvest.py <inn.txt> <out.csv> [--god 2026] [--mesyacy 1,2,3]
"""
import csv
import io
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

URL = ('https://proverki.gov.ru/blob/erknm-opendata/{god}/{m}/'
       'data-20260729-structure-20220125.zip')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
INN = re.compile(r'\b(\d{10}|\d{12})\b')


def skachat(god, m, path):
    req = urllib.request.Request(URL.format(god=god, m=m), headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(path, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return os.path.getsize(path)


def tekst(el):
    return ' '.join(t.strip() for t in el.itertext() if t and t.strip())


def razobrat(zip_path, nashi, god, m, w):
    """Пройти по XML потоком, вернуть число найденных записей.

    Ключевое: ИНН лежит в **атрибуте** `<SUBJECT INN="...">`, а не в тексте. Первая версия
    искала регуляркой по `itertext()` и нашла ноль — itertext атрибуты не читает вовсе.
    Записи называются `INSPECTION`, корень `ns2:INSPECTIONS`.

    ИНН физлиц в выгрузке замаскированы («******766***»), у юрлиц открыты: на выборке в
    60 МБ — 6 518 открытых ЮЛ против 75 замаскированных.
    """
    nashlos = 0
    with zipfile.ZipFile(zip_path) as z:
        for name in [n for n in z.namelist() if n.lower().endswith('.xml')]:
            with z.open(name) as fh:
                try:
                    for _, el in ET.iterparse(fh, events=('end',)):
                        if el.tag.rsplit('}', 1)[-1] != 'INSPECTION':
                            continue
                        nashi_v_zapisi, imena = set(), {}
                        for s in el.iter():
                            if s.tag.rsplit('}', 1)[-1] == 'SUBJECT':
                                inn = (s.get('INN') or '').strip()
                                if inn in nashi:
                                    nashi_v_zapisi.add(inn)
                                    imena[inn] = (s.get('NAME') or '').strip()
                        if nashi_v_zapisi:
                            vid = ''
                            adres = ''
                            for s in el.iter():
                                t = s.tag.rsplit('}', 1)[-1]
                                if t == 'KIND_CONTROL' and not vid:
                                    vid = s.get('VALUE') or ''
                                if t in ('ADDRESS', 'OBJECT_ADDRESS') and not adres:
                                    adres = (s.get('VALUE') or s.get('ADDRESS') or '').strip()
                            txt = ' '.join(x.strip() for x in el.itertext() if x and x.strip())
                            for inn in nashi_v_zapisi:
                                w.writerow({
                                    'god': god, 'mesyac': m, 'inn': inn,
                                    'zakazchik': imena.get(inn, ''),
                                    'erpid': el.get('ERPID', ''),
                                    'tip': el.get('TYPE_NAME', ''),
                                    'status': el.get('STATUS', ''),
                                    'data_nachala': el.get('START_DATE', ''),
                                    'vid_nadzora': vid, 'adres': adres[:200],
                                    'est_kompressor': 'да' if re.search(
                                        r'компрессор|нагнетател|воздуходув', txt, re.I) else '',
                                    'tekst': txt[:1200]})
                                nashlos += 1
                        el.clear()
                except ET.ParseError as e:
                    print(f'    {name}: разбор оборвался — {e}', file=sys.stderr)
    return nashlos


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: erknm_harvest.py <inn.txt> <out.csv> [--god 2026] [--mesyacy 1,2]')
    inn_path, out_path = sys.argv[1], sys.argv[2]
    god = sys.argv[sys.argv.index('--god') + 1] if '--god' in sys.argv else '2026'
    mes = (sys.argv[sys.argv.index('--mesyacy') + 1].split(',')
           if '--mesyacy' in sys.argv else [str(i) for i in range(1, 8)])

    nashi = {l.strip() for l in open(inn_path, encoding='utf-8') if l.strip()}
    print(f'наших ИНН: {len(nashi)}, месяцев: {len(mes)}', file=sys.stderr)

    tmp = os.environ.get('ERKNM_TMP', '/tmp/erknm.zip')
    f = open(out_path, 'w', encoding='utf-8-sig', newline='')
    w = csv.DictWriter(f, fieldnames=['god', 'mesyac', 'inn', 'zakazchik', 'erpid', 'tip',
                                      'status', 'data_nachala', 'vid_nadzora', 'adres',
                                      'est_kompressor', 'tekst'],
                       delimiter=';', extrasaction='ignore')
    w.writeheader()
    vsego = 0
    for m in mes:
        try:
            size = skachat(god, m, tmp)
        except Exception as e:  # noqa: BLE001
            print(f'{god}/{m}: не скачался — {e}', file=sys.stderr)
            continue
        n = razobrat(tmp, nashi, god, m, w)
        f.flush()
        os.remove(tmp)
        vsego += n
        print(f'{god}/{m}: архив {size // 1048576} МБ, найдено записей {n}, всего {vsego}',
              file=sys.stderr)
    f.close()
    print(f'итого {vsego} записей → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
