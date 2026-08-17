# -*- coding: utf-8 -*-
r"""Проверка ответа соседа: «случаев "имя выведено из ящика" — ноль».

Его довод круговой: imya_ok ставится ТОЛЬКО при own-site и source_url — это
условия самого флага, а не доказательство, что имя стояло на странице. При этом
в _chistoe_fio есть ветка: фамилия читается в ящике -> страничная сверка
пропускается. Значит вопрос решается только замером: берём каждый imya_ok=1 и
ищем фамилию в скачанных страницах компании.

  страница        фамилия найдена в тексте страниц — имя реально со страницы;
  только_ящик     на страницах фамилии нет, но она читается в адресе — тут
                  сверка пропускалась, и «выведено из ящика» исключить нельзя;
  ни_там_ни_там   нет ни на странице, ни в ящике (так флаг стоять не должен);
  кэша_нет        страницы не сохранились — проверить нечем.
"""
import gzip
import json
import os
import re
import sqlite3
import sys

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')

_TRANSLIT = {'а': ['a'], 'б': ['b'], 'в': ['v', 'w'], 'г': ['g'], 'д': ['d'],
             'е': ['e', 'ye', 'je'], 'ё': ['e', 'yo', 'jo'], 'ж': ['zh', 'j', 'g'],
             'з': ['z'], 'и': ['i', 'y'], 'й': ['y', 'i', 'j'], 'к': ['k', 'c'],
             'л': ['l'], 'м': ['m'], 'н': ['n'], 'о': ['o'], 'п': ['p'], 'р': ['r'],
             'с': ['s', 'c'], 'т': ['t'], 'у': ['u'], 'ф': ['f'],
             'х': ['h', 'kh', 'x'], 'ц': ['c', 'ts', 'tc'], 'ч': ['ch'],
             'ш': ['sh'], 'щ': ['sch', 'shch'], 'ъ': [''], 'ы': ['y', 'i'],
             'ь': [''], 'э': ['e'], 'ю': ['yu', 'ju', 'u'], 'я': ['ya', 'ja', 'a']}


def _v_yashchike(fio, email):
    if not email or '@' not in (email or ''):
        return False
    ящик = re.sub(r'[^a-z]', '', email.split('@')[0].lower())
    части = [c for c in re.split(r'[\s.]+', fio) if len(c) > 3]
    if len(ящик) < 4 or not части:
        return False
    фам = части[0].lower().replace('ё', 'е')
    в = ['']
    for ch in фам[:5]:
        в = [x + h for x in в for h in _TRANSLIT.get(ch, [ch])][:64]
    return any(x and x in ящик for x in в)


def _tekst(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return None
    try:
        d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return None
    куски = []
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        куски.append(re.sub(r'<[^>]+>', ' ', re.sub(
            r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)))
    return ' '.join(куски).lower().replace('ё', 'е')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    строки = list(c.execute(
        "select inn, email, person from emails where imya_ok=1 "
        "and coalesce(person,'')<>'' order by inn"))
    c.close()
    итог = {'записей_imya_ok': len(строки), 'страница': 0, 'только_ящик': 0,
            'ни_там_ни_там': 0, 'кэша_нет': 0}
    компании = {}
    примеры = {'только_ящик': [], 'ни_там_ни_там': []}
    кэш_текст = {'inn': None, 'текст': None}
    for inn, email, person in строки:
        inn = str(inn)
        if кэш_текст['inn'] != inn:
            кэш_текст = {'inn': inn, 'текст': _tekst(inn)}
        текст = кэш_текст['текст']
        части = [x for x in re.split(r'[\s.]+', person) if len(x) > 3]
        корень = части[0].lower().replace('ё', 'е')[:-1] if части else ''
        if текст is None:
            куда = 'кэша_нет'
        elif корень and корень in текст:
            куда = 'страница'
        elif _v_yashchike(person, email):
            куда = 'только_ящик'
        else:
            куда = 'ни_там_ни_там'
        итог[куда] += 1
        компании.setdefault(куда, set()).add(inn)
        if куда in примеры and len(примеры[куда]) < 8:
            примеры[куда].append({'инн': inn, 'ящик': email, 'имя': person})
    итог['компаний'] = {k: len(v) for k, v in компании.items()}
    print(json.dumps({'примеры': примеры}, ensure_ascii=False, indent=1))
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
