# -*- coding: utf-8 -*-
r"""Круг догруза «Партии 935»: собрать → импортировать → протегировать → сверить.

Зачем отдельный круг, а не разовая команда. Паспорта дособираются круглые сутки,
поэтому список «компания готова к письму» растёт сам по себе: сегодня 7118, через
час больше. Один прогон закрывает только то, что готово на эту минуту.

И главное — тут два шага, а не один, и каждый закрывает свою дыру:
  * штатный импорт заводит получателя, но НЕ ставит группу (extra_json={}), а
    без группы получатель не виден ни под одним фильтром панели — 85 строк 20.08
    приехали именно так;
  * тегирование ставит группу тем, кто уже в панели, но ничего не знает про тех,
    кого в панели ещё нет.
Поэтому порядок жёсткий: CSV → импорт → тег → сверка. Сверяем результат, а не
код возврата: каждая строка CSV обязана найтись в recipients И нести группу.

    python dogruz_cikl.py            # сухой прогон: что бы сделали
    python dogruz_cikl.py --primenit # импорт + теги + сверка
"""
import csv
import io
import json
import os
import sqlite3
import subprocess
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import dogruz_935 as D  # noqa: E402

SENDER_BD = r'C:\sender\sender.db'


def _stroki_csv():
    if not os.path.exists(D.CSV_PATH):
        return []
    with io.open(D.CSV_PATH, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def _import(путь):
    p = subprocess.run([sys.executable, '-m', 'sender', '--config',
                        r'C:\sender\sender.yaml', 'import', путь],
                       cwd=r'C:\sender', capture_output=True, text=True,
                       timeout=1800)
    вывод = ((p.stdout or '') + (p.stderr or '')).strip()
    try:
        return {'rc': p.returncode, **json.loads(вывод[вывод.index('{'):])}
    except Exception:  # noqa: BLE001
        return {'rc': p.returncode, 'вывод': вывод[-400:]}


def _sverka(ряды):
    c = sqlite3.connect('file:%s?mode=ro' % SENDER_BD.replace('\\', '/'),
                        uri=True, timeout=60)
    c.row_factory = sqlite3.Row
    нашлось = без_группы = 0
    примеры = []
    for r in ряды:
        адрес = (r.get('email') or '').strip().lower()
        if not адрес:
            continue
        ряд = c.execute("select id, coalesce(extra_json,'') ex from recipients "
                        'where lower(email)=?', (адрес,)).fetchone()
        if not ряд:
            if len(примеры) < 5:
                примеры.append({'нет_в_панели': адрес})
            continue
        нашлось += 1
        try:
            гр = (json.loads(ряд['ex']) or {}).get('gruppy') or []
        except Exception:  # noqa: BLE001
            гр = []
        if D.ГРУППА not in гр:
            без_группы += 1
            if len(примеры) < 5:
                примеры.append({'без_группы': адрес, 'id': ряд['id']})
    всего = c.execute('select count(*) from recipients where extra_json like ?',
                      ('%' + D.ГРУППА + '%',)).fetchone()[0]
    c.close()
    return {'в_csv': len(ряды), 'нашлось_в_панели': нашлось,
            'БЕЗ_ГРУППЫ': без_группы, 'в_группе_всего': всего,
            'примеры': примеры}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if '--primenit' not in sys.argv:
        свод, теги, строки = D.собрать()
        свод['пример_csv'] = строки[:2]
        свод['тегов_поставили_бы'] = len(теги)
        print(json.dumps(свод, ensure_ascii=False, indent=1))
        return 0

    итог = {}
    # 1. CSV новых + теги тем, кто уже в панели.
    итог['шаг1_сбор'] = D.применить()
    ряды = _stroki_csv()
    # 2. Импорт новых, если они есть.
    if ряды:
        итог['шаг2_импорт'] = _import(D.CSV_PATH)
        # 3. Второй проход тегирования — теперь импортированные видны по ИНН.
        итог['шаг3_теги'] = D.применить()
    else:
        итог['шаг2_импорт'] = {'нечего импортировать': True}
    # 4. Сверка по строкам ПЕРВОГО csv: они и есть догруз этого круга.
    итог['шаг4_сверка'] = _sverka(ряды)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
