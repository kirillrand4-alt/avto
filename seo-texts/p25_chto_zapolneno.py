# -*- coding: utf-8 -*-
"""Какие колонки p25.db реально заполнены, а какие пусты. Замер до любых выводов.

ПОЧЕМУ ЭТО ПОНАДОБИЛОСЬ. Домен предприятия я попробовала добыть из корпоративной почты и
получила ЧИСТЫЙ НОЛЬ: 491 из 491 «корпоративной почты нет». Ноль такого размера — почти
всегда не свойство мира, а свойство входа, и принимать его без проверки нельзя: ровно так
рождаются ложные «мы посмотрели, там пусто».

Поэтому здесь не гипотеза, а перепись: по каждой колонке `company` — сколько записей
непустых. Схема p25.db склонирована с боевой базы центробежки (76 колонок), и вопрос не
«есть ли колонка», а «доехали ли в неё данные при импорте книги продаж».
"""
import json
import sqlite3

BAZA = 'file:C:/seostat/data/p25.db?mode=ro'


def main():
    b = sqlite3.connect(BAZA, uri=True)
    kol = [r[1] for r in b.execute('pragma table_info(company)')]
    vsego = b.execute('select count(*) from company').fetchone()[0]
    zapolneno, pusto = {}, []
    for k in kol:
        n = b.execute(
            'select count(*) from company where coalesce("%s","") not in ("", "0")' % k
        ).fetchone()[0]
        if n:
            zapolneno[k] = n
        else:
            pusto.append(k)
    # Заодно — что есть у людей: там источник контакта и есть главная мера.
    lyudi = {}
    for t, poles in (('person', ('phone', 'email', 'position', 'source_url',
                                 'chem_podtverzhdena')),
                     ('contact', ('value', 'person', 'position', 'source_url',
                                  'phone_type'))):
        try:
            n = b.execute('select count(*) from %s' % t).fetchone()[0]
        except Exception:  # noqa: BLE001
            continue
        lyudi[t] = {'всего': n}
        for p in poles:
            try:
                lyudi[t][p] = b.execute(
                    'select count(*) from %s where coalesce("%s","") <> ""' % (t, p)
                ).fetchone()[0]
            except Exception as e:  # noqa: BLE001
                lyudi[t][p] = 'нет колонки: %s' % type(e).__name__
    for k, v in sorted(zapolneno.items(), key=lambda x: -x[1]):
        print('REC %-34s %5d из %d' % (k, v, vsego))
    print('ИТОГ ' + json.dumps({'предприятий': vsego, 'колонок': len(kol),
                                'непустых_колонок': len(zapolneno),
                                'ПУСТЫХ_НАСКВОЗЬ': pusto, 'люди': lyudi},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
