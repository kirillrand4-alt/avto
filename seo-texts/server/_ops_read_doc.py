# -*- coding: utf-8 -*-
"""Прочитать КОНКРЕТНЫЙ документ, из которого уже извлеклись люди, и показать
его глазами: есть ли там состав комиссии или только подпись.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

e = EDB.EnrichDB().cx
_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def main():
    урлы = [r[0] for r in e.execute(
        "SELECT DISTINCT source_url FROM people WHERE source_url LIKE "
        "'%filestore%' LIMIT 3")]
    out = {'документов': len(урлы), 'разбор': []}
    for u in урлы:
        зап = {'ссылка': u[:100]}
        t = EC.doc_text(u)
        зап['символов'] = len(t or '')
        if t:
            t = re.sub(r'[ \t]+', ' ', t)
            зап['начало'] = re.sub(r'\s+', ' ', t)[:700]
            зап['есть_председатель'] = bool(re.search(r'председател', t, re.I))
            зап['есть_секретарь'] = bool(re.search(r'секретар', t, re.I))
            зап['есть_член_комиссии'] = bool(re.search(r'член\w*\s+комисси', t, re.I))
            зап['есть_инженер'] = bool(re.search(r'инженер', t, re.I))
            зап['есть_энергетик'] = bool(re.search(r'энергетик', t, re.I))
            зап['фио_всего'] = len(set(_ФИО.findall(t)))
            зап['фио'] = sorted(set(_ФИО.findall(t)))[:12]
            окна = [re.sub(r'\s+', ' ', t[max(0, m.start() - 300):m.start() + 800])
                    for m in re.finditer(r'комисси', t, re.I)]
            зап['вхождений_комисси'] = len(окна)
            зап['окно'] = окна[0] if окна else ''
        out['разбор'].append(зап)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:8000])


if __name__ == '__main__':
    main()
