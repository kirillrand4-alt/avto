# -*- coding: utf-8 -*-
"""Сколько ЛПР-контактов ИМЕННЫЕ (с ФИО), а сколько — общий ящик отдела."""
import json
import re
import sqlite3

CENTRO = r'C:\seostat\data\centrifugal.db'
# ящики, которые извлекатель пометил ролью, но по локальной части видно, что это
# не человек, а функция (кадры, качество, приёмная) — считать их ЛПР нельзя
GENERIC = re.compile(
    r'^(?:rabota|job|hr|personal|kadr|kachestvo|quality|info|office|mail|secretar|'
    r'priemn|zakaz|sales|opt|delo|doc|kancel|post|contact|admin|reception)',
    re.I)


def main():
    cx = sqlite3.connect(f'file:{CENTRO}?mode=ro', uri=True, timeout=60)
    cx.row_factory = sqlite3.Row
    out = {}
    for label, like in (('гл.инженер', '%инженер%'), ('директор', '%директор%')):
        rows = cx.execute(
            'select base, inn, kind, value, person from contact where role like ?',
            (like,)).fetchall()
        named = [r for r in rows if (r['person'] or '').strip()]
        local = [r for r in rows if r['kind'] == 'email'
                 and not GENERIC.match((r['value'] or '').split('@')[0])]
        good = [r for r in rows if (r['person'] or '').strip()
                and not GENERIC.match((r['value'] or '').split('@')[0])]
        out[label] = {
            'всего': len(rows),
            'телефонов': sum(1 for r in rows if r['kind'] == 'phone'),
            'компаний': len({(r['base'], r['inn']) for r in rows}),
            'с_ФИО': len(named),
            'не_функциональный_ящик': len(local),
            'именной_И_не_функциональный': len(good),
            'компаний_с_таким': len({(r['base'], r['inn']) for r in good}),
            'по_базам': {b: len({r['inn'] for r in good if r['base'] == b})
                         for b in ('centro1', 'centro2')},
        }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
