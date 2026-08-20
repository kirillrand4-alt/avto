# -*- coding: utf-8 -*-
r"""Импорт CSV догруза штатной командой и сверка, что всё долетело.

Канон из PANEL-DEPLOY.md: python -m sender --config C:\sender\sender.yaml
import <csv>. После импорта проверяем не «команда не упала», а результат:
каждая строка CSV должна найтись в recipients, и у каждой должна стоять
группа — иначе получатель есть, а ни под одним фильтром не виден.
"""
import csv
import io
import json
import subprocess
import sys

CSV_PATH = r'C:\sender\_tmp\partiya-935-dogruz.csv'
SENDER = r'C:\sender\sender.db'
ГРУППА = 'Партия 935'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    итог = {}
    p = subprocess.run([sys.executable, '-m', 'sender', '--config',
                        r'C:\sender\sender.yaml', 'import', CSV_PATH],
                       cwd=r'C:\sender', capture_output=True, text=True,
                       timeout=1800)
    итог['rc'] = p.returncode
    итог['вывод'] = ((p.stdout or '') + (p.stderr or '')).strip()[-700:]

    with io.open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
        строки = list(csv.DictReader(f))
    итог['в_csv'] = len(строки)

    import sqlite3
    s = sqlite3.connect(SENDER, timeout=60)
    s.row_factory = sqlite3.Row
    нашлось = без_группы = 0
    примеры = []
    for r in строки:
        адрес = (r.get('email') or '').strip().lower()
        if not адрес:
            continue
        ряд = s.execute(
            "select id, coalesce(inn,'') inn, coalesce(extra_json,'') ex "
            'from recipients where lower(email)=?', (адрес,)).fetchone()
        if not ряд:
            if len(примеры) < 6:
                примеры.append({'нет_в_панели': адрес})
            continue
        нашлось += 1
        try:
            гр = (json.loads(ряд['ex']) or {}).get('gruppy') or []
        except Exception:  # noqa: BLE001
            гр = []
        if ГРУППА not in гр:
            без_группы += 1
            if len(примеры) < 6:
                примеры.append({'без_группы': адрес, 'id': ряд['id']})
    s.close()
    итог['нашлось_в_панели'] = нашлось
    итог['БЕЗ_ГРУППЫ'] = без_группы
    итог['примеры'] = примеры
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
