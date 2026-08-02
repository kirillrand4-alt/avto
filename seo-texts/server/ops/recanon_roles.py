# -*- coding: utf-8 -*-
"""Пересчёт ролей по действующему канону для УЖЕ записанных строк.

Канон ролей пополняется, когда на живых данных находится непокрытая должность
(так добавился «гл.конструктор» после пробоя Криогенмаша). Но записи, сделанные
ДО пополнения, остаются со старой ролью и продолжают лежать в выгрузке ниже
закупщиков. Пересчитываем из сохранённого текста должности — он в people.post
есть всегда, потому и хранится отдельно от роли.

Телефоны трогаем осторожно: у них в role лежит не должность, а метка источника
(«контакты компании (чеко)»), поэтому пересчитываем ТОЛЬКО те, где роль
совпадает с постом связанного человека.

По умолчанию СУХОЙ ПРОГОН. Запуск: python recanon_roles.py [--apply]
"""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
# Пересчёт «всего подряд» трогает и то, что канона не касалось: роль, которую
# ИСТОЧНИК знал лучше текста должности. Живой пример из сухого прогона —
# «Руководитель службы маркетинга» стояла как «продажи», а канон по слову
# «руковод» делает из неё «директор». Это ухудшение, и делать его молча,
# заодно с исправлением инженеров, нельзя. С этим флагом применяются только
# те строки, где меняется САМ ОТВЕТ «технический ЛПР или нет» — то есть ровно
# то, ради чего канон правился.
ТОЛЬКО_ТЕХ = '--tolko-tehlpr' in sys.argv
db = EDB.EnrichDB()
e = db.cx


def main():
    строки = list(e.execute(
        'SELECT rowid, inn, person, post, role FROM people WHERE ifnull(post,"")<>""'))
    менять = []
    for rowid, inn, person, post, role in строки:
        нов = EDB.EnrichDB._canon_role(post)
        if нов and нов != (role or ''):
            менять.append({'rowid': rowid, 'инн': inn, 'фио': person,
                           'должность': post, 'было': role, 'стало': нов})
    всего_кандидатов = len(менять)
    if ТОЛЬКО_ТЕХ:
        Т = set(EDB.EnrichDB.TECH_ROLES)
        менять = [x for x in менять
                  if (x['было'] in Т) != (x['стало'] in Т)]
    out = {'людей_с_должностью': len(строки),
           'кандидатов_всего': всего_кандидатов,
           'фильтр': 'только меняющие ответ техЛПР' if ТОЛЬКО_ТЕХ else 'все',
           'меняется': len(менять),
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'стало_техЛПР': sum(1 for x in менять
                               if x['стало'] in EDB.EnrichDB.TECH_ROLES
                               and x['было'] not in EDB.EnrichDB.TECH_ROLES),
           'примеры': менять[:14]}
    if ПРИМЕНИТЬ and менять:
        e.executemany('UPDATE people SET role=? WHERE rowid=?',
                      [(x['стало'], x['rowid']) for x in менять])
        # телефон человека тоже поднимаем в приоритете, если роль у него
        # ровно та же, что была у человека
        for x in менять:
            e.execute('UPDATE phone_contacts SET role=? WHERE inn=? AND '
                      'person=? AND ifnull(role,"")=?',
                      (x['стало'], x['инн'], x['фио'], x['было'] or ''))
        e.commit()
        out['обновлено'] = len(менять)
        out['людей_техЛПР_итого'] = e.execute(
            'SELECT COUNT(*) FROM people WHERE role IN (%s)'
            % ','.join('?' * len(EDB.EnrichDB.TECH_ROLES)),
            EDB.EnrichDB.TECH_ROLES).fetchone()[0]
    print(json.dumps(out, ensure_ascii=False, indent=1)[:5000])
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
