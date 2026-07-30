# -*- coding: utf-8 -*-
"""Поднять ЛИЧНЫЙ номер в people.phone, если он есть, но лежит не там.

Найдено сравнением с мерой третьей сессии. Она предложила считать не
«телефоны», а личные мобильные, привязанные к названному человеку, и назвала
своё число — 161. У меня вышло 99, и разницу надо было объяснить, а не
списать на «источник беднее».

Причина оказалась моей: импорт клал в `people.phone` ПЕРВЫЙ номер карточки
(`телефоны[0]`), а первым на карточке закупки обычно стоит коммутатор.
Мобильный при этом честно попадал в `phone_contacts` — то есть данные не
терялись, но человек в выгрузке выглядел «только с городским».

Замер: у 33 из 383 технических людей мобильный есть в `phone_contacts`, а в
`people.phone` стоит городской. Живьём: Кудряшова Лариса Вячеславовна,
гл.инженер — в people `(8352) 73-55-49`, а мобильный `8-909-304-56-55`.

Что делает: для каждого технического человека ищет ЕГО ЖЕ мобильный в
`phone_contacts` (совпадение по ИНН и ФИО) и поднимает его в `people.phone`.
Прежний номер НЕ теряется — он и так лежит в `phone_contacts`.

По умолчанию СУХОЙ ПРОГОН. Запись — с --apply.
"""
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
# мобильный: код 9xx после +7 / 8. Восьмёрка-800 не мобильный — это общий
# номер, и по мере третьей сессии он в счёт не идёт.
_МОБ = re.compile(r'(?:\+?7|8)\D{0,3}9\d\d')
_ВОСЕМЬСОТ = re.compile(r'8\D{0,3}800')


def мобильный(т):
    т = т or ''
    return bool(_МОБ.search(т)) and not _ВОСЕМЬСОТ.search(т)


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тр = "','".join(EDB.EnrichDB.TECH_ROLES)
    ряды = q("SELECT rowid, inn, person, role, COALESCE(phone,'') FROM people "
             f"WHERE role IN ('{тр}') OR role='техконтакт'").fetchall()
    было = sum(1 for r in ряды if мобильный(r[4]))
    print(f'технических людей (техЛПР + техконтакт): {len(ряды)}')
    print(f'  мобильный уже в people.phone: {было}')

    поднято = 0
    примеры = []
    for rid, инн, фио, роль, тел in ряды:
        if мобильный(тел):
            continue
        свои = [p[0] for p in q(
            'SELECT phone FROM phone_contacts WHERE inn=? AND person=?',
            (инн, фио)).fetchall()]
        моб = next((p for p in свои if мобильный(p)), '')
        if not моб:
            continue
        поднято += 1
        if len(примеры) < 10:
            примеры.append((инн, фио, роль, тел or '(пусто)', моб))
        if ПРИМЕНИТЬ:
            q('UPDATE people SET phone=? WHERE rowid=?', (моб, rid))
    if ПРИМЕНИТЬ:
        db.cx.commit()

    print(f'  мобильный найден в phone_contacts и '
          f'{"поднят" if ПРИМЕНИТЬ else "будет поднят"}: {поднято}')
    print()
    for и, ф, р, т, м in примеры:
        print(f'  {и}  {ф[:24]:<24} {р:<12} было {т[:18]:<18} стало {м[:18]}')

    стало = q(
        "SELECT COUNT(*) FROM people WHERE (role IN ('%s') OR role='техконтакт') "
        "AND (phone LIKE '%%9%%')" % тр).fetchone()[0]
    print()
    print('=== ИЗ БАЗЫ ===')
    ряды2 = q("SELECT COALESCE(phone,'') FROM people "
              f"WHERE role IN ('{тр}') OR role='техконтакт'").fetchall()
    честно = sum(1 for r in ряды2 if мобильный(r[0]))
    предпр = q(
        "SELECT COUNT(DISTINCT inn) FROM people "
        f"WHERE (role IN ('{тр}') OR role='техконтакт') AND phone!=''").fetchone()[0]
    print(f'  ЛИЧНЫХ НОМЕРОВ в people.phone: {честно} (было {было})')
    print(f'  предприятий за ними: {предпр}')
    print(f'подняли {поднято}, личных {честно}')


if __name__ == '__main__':
    main()
