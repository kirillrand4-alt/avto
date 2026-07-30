# -*- coding: utf-8 -*-
"""Телефоны и почты по ИНН — заказ второй сессии под её находку в ЕРКНМ.

Вторая сессия нашла, что тексты ПРЕДОСТЕРЕЖЕНИЙ Ростехнадзора в ЕРКНМ
называют технических работников поимённо и с должностью: «главный энергетик
Казаков Алексей Григорьевич», «заместитель главного механика Латыпов Артур
Индусович». 71 человек на 24 предприятиях. Телефонов там нет, и без них
имя не звонибельно.

У меня телефоны есть: 25 786 записей с источником и ссылкой. Отдаю всё, что
знаю по этим ИНН — телефоны предприятия, почты, сайт и уже известных людей,
чтобы её 71 имя не дублировалось с моими.

ВАЖНАЯ ОГОВОРКА, её же слова, и я с ней согласен: повод для звонка отсюда
брать НЕЛЬЗЯ. Человек назван в предостережении потому, что НЕ ПРОШЁЛ проверку
знаний. Берём только «кто занимает роль», повод — из состояния машины.

Запуск: python tel_dlya_erknm.py --inn ФАЙЛ-СО-СПИСКОМ
"""
import csv
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

# Имя выхода задаётся параметром: тот же оп обслуживает и заказ по ЕРКНМ, и
# заказ по 683 водоканалам. Плодить копию ради имени файла незачем.
ИМЯ = (sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv
       else 'TELEFONY-dlya-2-sessii-ERKNM.csv')
ПАПКА = r'C:\sender\server'
СПИСОК = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv
          else r'C:\sender\server\erknm_inn.txt')


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def main():
    if not os.path.exists(СПИСОК):
        raise SystemExit(f'нет файла со списком ИНН: {СПИСОК}')
    инны = []
    for строка in open(СПИСОК, encoding='utf-8-sig', errors='replace'):
        м = re.search(r'(?<!\d)(\d{10}|\d{12})(?!\d)', строка)
        if м and м.group(1) not in инны:
            инны.append(м.group(1))
    print(f'ИНН в заказе: {len(инны)}')
    if not инны:
        return

    db = EDB.EnrichDB()
    q = db.cx.execute
    сп = ','.join('?' * len(инны))
    тр = "','".join(EDB.EnrichDB.TECH_ROLES)

    путь = os.path.join(ПАПКА, ИМЯ)
    с_тел = с_поч = с_людьми = 0
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['ИНН', 'компания', 'регион', 'сайт', 'телефоны',
                    'источники_телефонов', 'почты', 'людей_у_меня',
                    'техЛПР_у_меня', 'кто_уже_есть'])
        for и in инны:
            к = q('SELECT COALESCE(name,%s), COALESCE(region,%s), '
                  'COALESCE(site,%s) FROM companies WHERE inn=?' % ("''", "''", "''"),
                  (и,)).fetchone() or ('', '', '')
            тел = q('SELECT phone, COALESCE(source,%s) FROM phone_contacts '
                    'WHERE inn=? ORDER BY rowid LIMIT 8' % "''", (и,)).fetchall()
            поч = [r[0] for r in q('SELECT email FROM emails WHERE inn=? LIMIT 6',
                                   (и,)).fetchall()]
            люди = q('SELECT person, COALESCE(post,%s), COALESCE(role,%s), '
                     'COALESCE(phone,%s) FROM people WHERE inn=? LIMIT 12' % ("''", "''", "''"),
                     (и,)).fetchall()
            тех = q(f"SELECT COUNT(*) FROM people WHERE inn=? AND role IN ('{тр}')",
                    (и,)).fetchone()[0]
            if тел:
                с_тел += 1
            if поч:
                с_поч += 1
            if люди:
                с_людьми += 1
            в.writerow([
                и, к[0][:80], к[1], к[2],
                ' | '.join(t[0] for t in тел),
                ' | '.join(sorted({t[1] for t in тел})),
                ' | '.join(поч),
                len(люди), тех,
                ' ;; '.join(f'{p} | {po} | {ro}' + (f' | {ph}' if ph else '')
                            for p, po, ro, ph in люди)])
        ф.flush()
        os.fsync(ф.fileno())

    print(f'{ИМЯ}: {len(инны)} строк')
    print(f'  с телефоном у меня: {с_тел} из {len(инны)}')
    print(f'  с почтой: {с_поч}')
    print(f'  с людьми в базе: {с_людьми}')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')

    print()
    print('=== ЧТО ОТДАЁТСЯ (примеры) ===')
    for и in инны[:10]:
        имя = (q('SELECT name FROM companies WHERE inn=?', (и,)).fetchone()
               or ('',))[0] or ''
        т = q('SELECT phone FROM phone_contacts WHERE inn=? LIMIT 2',
              (и,)).fetchall()
        print(f'  {и}  {имя[:34]:<34} {" | ".join(x[0] for x in т) or "(телефона нет)"}')
    print(f'ИНН {len(инны)}, с телефоном {с_тел}, с почтой {с_поч}')


if __name__ == '__main__':
    main()
