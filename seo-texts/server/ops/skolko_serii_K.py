# -*- coding: utf-8 -*-
"""Сколько предприятий с машинами серии «К» (К-250/К-350/К-500/ЦТК-275).

Вопрос владельца по странице каталога: сколько у нас предприятий именно с
такими компрессорами и сколько всего в базе.

Считаем ПО ПРЕДПРИЯТИЯМ (ИНН), а не по фактам: на одном заводе бывает три
записи про один и тот же К-250 из разных источников, и «фактов» получится
втрое больше, чем заводов — цифра, по которой нельзя планировать обзвон.

Марку берём из тех же полей и через тот же отбраковщик, что и панель
(`centro_medium.rejection_reason`), иначе счёт разъедется с тем, что продавец
видит на экране.

Осторожность в разборе обозначения: «К-250» надо отличать от «АК-250»,
«ГПА-К-250» и от «К-250» в номере документа. Поэтому число ищем только там,
где перед буквой К нет другой буквы/цифры, и требуем разделитель или пробел.
ЦТК-275 пишут и как «ЦТК 275», и как «ЦТК-275-1,08».

Запуск: python skolko_serii_K.py
"""
import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog, centro_medium  # noqa: E402

# что показано на странице каталога: подвальные машины серии К + ЦТК-275
СЕРИИ = {
    'К-250': re.compile(r'(?<![A-Za-zА-Яа-я0-9])К\s*[-–]?\s*250(?!\d)', re.I),
    'К-350': re.compile(r'(?<![A-Za-zА-Яа-я0-9])К\s*[-–]?\s*35[04](?!\d)', re.I),
    'К-500': re.compile(r'(?<![A-Za-zА-Яа-я0-9])К\s*[-–]?\s*500(?!\d)', re.I),
    'ЦТК-275': re.compile(r'ЦТК\s*[-–]?\s*275(?!\d)', re.I),
}


def main():
    with centro_catalog.connect() as conn:
        факты = centro_catalog._rows(conn, 'SELECT * FROM fact', ())
        всего_в_базе = conn.execute(
            'SELECT COUNT(*) FROM company').fetchone()[0]
        с_фактом = conn.execute(
            'SELECT COUNT(DISTINCT inn) FROM fact').fetchone()[0]

    по_серии = defaultdict(set)
    марки_внутри = Counter()
    чистых = 0
    примеры = []
    for row in факты:
        item = {
            **row,
            'status': row.get('status') or row.get('chto') or '',
            'model': row.get('model') or row.get('kto_ili_marka') or '',
            'equipment_type': (row.get('equipment_type')
                               or row.get('dolzhnost_ili_tip') or ''),
            'medium': row.get('medium') or row.get('rol') or '',
            'evidence': row.get('evidence') or row.get('chem_dokazano') or '',
            'quote': row.get('quote') or row.get('citata') or '',
        }
        if centro_medium.rejection_reason(item):
            continue
        чистых += 1
        инн = str(row.get('inn') or '')
        марка = item['model']
        if not инн or not марка:
            continue
        for имя, рег in СЕРИИ.items():
            if рег.search(марка):
                по_серии[имя].add(инн)
                марки_внутри[марка.strip()[:60]] += 1
                if len(примеры) < 12:
                    примеры.append({'inn': инн, 'марка': марка.strip()[:60],
                                    'кто': (row.get('name') or '')[:50]})

    все = set().union(*по_серии.values()) if по_серии else set()
    print(json.dumps({
        'предприятий_в_базе_всего': всего_в_базе,
        'из_них_с_хотя_бы_одним_чистым_фактом': с_фактом,
        'чистых_фактов_всего': чистых,
        'предприятий_с_серией_К_или_ЦТК275': len(все),
        'по_сериям_предприятий': {k: len(v) for k, v in sorted(по_серии.items())},
        'написания_марок_внутри': марки_внутри.most_common(20),
        'примеры': примеры,
    }, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
