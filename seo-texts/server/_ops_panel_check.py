# -*- coding: utf-8 -*-
"""Что панель обзвона показывает по конкретному ИНН — проверка после пересборки.

Смотрим не в enrich.db, а в СНИМОК centrifugal.db, из которого панель и рисует
карточку: сборка могла отфильтровать строку, и убедиться нужно именно здесь.
"""
import json
import sqlite3
import sys

БД = r'C:\seostat\data\centrifugal.db'
ИНН = next((a for a in sys.argv[1:] if a.isdigit()), '5001000066')


def строки(cx, sql, args=()):
    cur = cx.execute(sql, args)
    поля = [d[0] for d in cur.description]
    return [dict(zip(поля, r)) for r in cur.fetchall()]


def main():
    cx = sqlite3.connect(f'file:{БД}?mode=ro', uri=True, timeout=30)
    комп = строки(cx, 'SELECT base, inn, name_short, priority, n_phones, '
                      'n_emails, n_persons, n_signals, site, revenue '
                      'FROM company WHERE inn=?', (ИНН,))
    out = {'инн': ИНН, 'карточки': комп}
    for c in комп:
        out.setdefault('люди', []).extend(строки(
            cx, 'SELECT person, post, role, source, source_url FROM person '
                'WHERE base=? AND inn=?', (c['base'], ИНН)))
        out.setdefault('контакты', []).extend(строки(
            cx, 'SELECT kind, value, person, role, source, source_url '
                'FROM contact WHERE base=? AND inn=? LIMIT 20',
            (c['base'], ИНН)))
    out['ссылка_панели'] = [
        f'https://parsercompressor.online/obzvon/{c["base"]}?q={ИНН}' for c in комп]
    # раннер отдаёт stdout ХВОСТОМ — сводку печатаем последней, иначе её срежет
    out['проверка_реквизитов'] = [
        c['value'] for c in out.get('контакты', [])
        if c['value'] in ('+7 (500) 100-00-66', '+7 (495) 123-45-67')]
    print(json.dumps(out, ensure_ascii=False, indent=1)[:4000])
    print(json.dumps({
        'карточки': [(c['base'], c['name_short'], c['n_persons'], c['n_phones'])
                     for c in комп],
        'люди': [(p['person'], (p['post'] or '')[:38])
                 for p in out.get('люди', [])],
        'реквизиты_среди_телефонов': out['проверка_реквизитов'] or 'нет',
        'ссылка': out['ссылка_панели']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
