# -*- coding: utf-8 -*-
"""Состояние базы контактов одним взглядом: что есть, с ролями и по источникам.

Нужен после каждого крупного прогона, чтобы отчитываться цифрами из БАЗЫ, а не
из счётчиков прогона: счётчик показывает, сколько прогон думал, что записал,
а база — что действительно лежит.
"""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

# Список берём из боевого определения, а не переписываем руками: свой
# список я уже написал мимо канона («главный инженер» вместо «гл.инженер»)
# и получил заниженный ноль там, где технические ЛПР есть.
ТЕХ = EDB.EnrichDB.TECH_ROLES


def main():
    e = EDB.EnrichDB().cx
    out = {}
    out['компаний'] = e.execute('select count(*) from companies').fetchone()[0]
    out['телефонов'] = e.execute(
        'select count(*) from phone_contacts').fetchone()[0]
    out['телефонов_с_ролью'] = e.execute(
        "select count(*) from phone_contacts where ifnull(role,'')<>''"
    ).fetchone()[0]
    out['телефонов_техЛПР'] = e.execute(
        'select count(*) from phone_contacts where role in (%s)'
        % ','.join('?' * len(ТЕХ)), ТЕХ).fetchone()[0]
    out['компаний_с_телефоном'] = e.execute(
        'select count(distinct inn) from phone_contacts').fetchone()[0]
    out['почт'] = e.execute('select count(*) from emails').fetchone()[0]
    out['почт_с_ролью'] = e.execute(
        "select count(*) from emails where ifnull(role,'')<>'' "
        "and role<>'общий'").fetchone()[0]
    out['компаний_с_почтой'] = e.execute(
        'select count(distinct inn) from emails').fetchone()[0]
    out['людей'] = e.execute('select count(*) from people').fetchone()[0]
    out['людей_техЛПР'] = e.execute(
        'select count(*) from people where role in (%s)'
        % ','.join('?' * len(ТЕХ)), ТЕХ).fetchone()[0]
    out['людей_без_контактов'] = e.execute(
        "select count(*) from people where ifnull(phone,'')='' "
        "and ifnull(email,'')=''").fetchone()[0]
    out['компаний_с_людьми'] = e.execute(
        'select count(distinct inn) from people').fetchone()[0]
    out['роли_телефонов'] = [
        {'роль': r[0] or '(пусто)', 'штук': r[1]} for r in e.execute(
            'select role, count(*) c from phone_contacts group by role '
            'order by c desc limit 14')]
    out['источники_телефонов'] = [
        {'источник': r[0] or '(пусто)', 'штук': r[1]} for r in e.execute(
            'select source, count(*) c from phone_contacts group by source '
            'order by c desc limit 10')]
    out['роли_людей'] = [
        {'роль': r[0] or '(пусто)', 'штук': r[1]} for r in e.execute(
            'select role, count(*) c from people group by role '
            'order by c desc limit 14')]
    out['сигналы'] = [
        {'тип': r[0], 'штук': r[1]} for r in e.execute(
            'select event_type, count(*) c from signals group by event_type '
            'order by c desc limit 8')]
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    # раннер отдаёт stdout ХВОСТОМ — сводку цифр повторяем в конце
    print(json.dumps({k: v for k, v in out.items()
                      if not isinstance(v, list)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
