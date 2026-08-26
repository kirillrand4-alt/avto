# -*- coding: utf-8 -*-
r"""Перелить контакты checko из `requisites` в рабочие таблицы.

Разведка 26.08 нашла бесплатный слой: поля `site_checko`, `emails_checko`,
`phones_checko` в таблице `requisites` заполнены и оплачены, а рабочие таблицы
о них не знают. Причина не в потере данных: прогон `ops/checko_contacts.py`
шёл только по двум спискам (продажники и ядро), реквизиты заведены у 2 801
компании из 166 620, и остальным контакты просто никогда не спрашивали.

Что переливаем:
  * сайт — в companies.site, только если site И cand_site пусты (кандидату не
    перебиваем: у него своё происхождение и своя проверка);
  * почты — в emails, только компаниям, у которых нет НИ ОДНОЙ почты;
  * телефоны — в phone_contacts на тех же условиях.

Источник помечаем 'checko-реквизиты', чтобы потом можно было отделить и, если
понадобится, снять одним запросом. Точность checko по сайтам померена на 791
пересечении, где сайт нам уже известен: 83,4 % совпадений — этого хватает для
рабочего поля по решению владельца («оставляй рабочими, они из чеко»).

Пишем мелкими транзакциями: enrich.db держит zenno_most --demon.

    python zalit_kontakty_iz_rekvizitov.py            только замер
    python zalit_kontakty_iz_rekvizitov.py --pisat    залить
"""
import json
import os
import re
import sqlite3
import sys
import time

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ИСТОЧНИК = 'checko-реквизиты'
ЖУРНАЛ = os.path.join(os.environ.get('TEMP_DIR', r'C:\sender\_tmp'),
                      'kontakty-iz-rekvizitov.jsonl')
_ПОЧТА = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
_ТЕЛЕФОН = re.compile(r'\+?\d[\d\s()-]{9,17}\d')


def _kuskami(c, куски, дело):
    """Транзакции по пять записей с повтором: длинная не пролезает мимо моста."""
    ок = 0
    for i in range(0, len(куски), 5):
        часть = куски[i:i + 5]
        for _ in range(40):
            try:
                c.execute('BEGIN IMMEDIATE')
                for з in часть:
                    дело(c, з)
                c.commit()
                ок += len(часть)
                break
            except sqlite3.OperationalError:
                try:
                    c.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(3)
    return ок


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    писать = '--pisat' in sys.argv or os.environ.get('ZALIT_PISAT') == '1'
    теперь = time.strftime('%Y-%m-%dT%H:%M:%S')
    c = sqlite3.connect(BD, timeout=90)
    c.execute('PRAGMA busy_timeout=90000')
    c.row_factory = sqlite3.Row
    d = {'писать': писать}

    сайты = [(str(r['inn']), r['sc'].strip()) for r in c.execute(
        "select r.inn, coalesce(r.site_checko,'') sc from requisites r "
        'join companies k on k.inn=r.inn '
        "where coalesce(r.site_checko,'')<>'' and coalesce(k.site,'')='' "
        "and coalesce(k.cand_site,'')=''")]
    d['сайтов_к_заливке'] = len(сайты)

    почты = []
    for r in c.execute(
            "select r.inn, coalesce(r.emails_checko,'') em from requisites r "
            'join companies k on k.inn=r.inn '
            "where coalesce(r.emails_checko,'')<>'' "
            'and not exists(select 1 from emails e where e.inn=r.inn)'):
        for а in dict.fromkeys(x.lower() for x in _ПОЧТА.findall(r['em'])):
            почты.append((str(r['inn']), а))
    d['компаний_с_почтой'] = len({и for и, _ in почты})
    d['адресов_к_заливке'] = len(почты)

    телефоны = []
    for r in c.execute(
            "select r.inn, coalesce(r.phones_checko,'') ph from requisites r "
            'join companies k on k.inn=r.inn '
            "where coalesce(r.phones_checko,'')<>'' "
            'and not exists(select 1 from phone_contacts p where p.inn=r.inn)'):
        for т in dict.fromkeys(re.sub(r'\D', '', x)
                               for x in _ТЕЛЕФОН.findall(r['ph'])):
            if 10 <= len(т) <= 12:
                телефоны.append((str(r['inn']), '+' + т))
    d['компаний_с_телефоном'] = len({и for и, _ in телефоны})
    d['номеров_к_заливке'] = len(телефоны)

    if писать:
        d['сайтов_записано'] = _kuskami(
            c, сайты, lambda cx, з: (
                cx.execute("UPDATE companies SET site=?, site_source=? WHERE inn=? "
                           "AND coalesce(site,'')=''", (з[1], ИСТОЧНИК, з[0])),
                cx.execute('INSERT INTO stage_log(inn, stage, detail, ts) '
                           'VALUES(?,?,?,?) ON CONFLICT(inn, stage) DO UPDATE SET '
                           'detail=excluded.detail, ts=excluded.ts',
                           (з[0], 'sayt_iz_rekvizitov', з[1][:80], теперь))))
        d['адресов_записано'] = _kuskami(
            c, почты, lambda cx, з: cx.execute(
                'INSERT OR IGNORE INTO emails(inn, email, source, updated_at) '
                'VALUES(?,?,?,?)', (з[0], з[1], ИСТОЧНИК, теперь)))
        d['номеров_записано'] = _kuskami(
            c, телефоны, lambda cx, з: cx.execute(
                'INSERT OR IGNORE INTO phone_contacts(inn, phone, source, updated_at) '
                'VALUES(?,?,?,?)', (з[0], з[1], ИСТОЧНИК, теперь)))
        with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
            for и, з in сайты:
                f.write(json.dumps({'ts': теперь, 'инн': и, 'сайт': з},
                                   ensure_ascii=False) + '\n')
            for и, з in почты:
                f.write(json.dumps({'ts': теперь, 'инн': и, 'почта': з},
                                   ensure_ascii=False) + '\n')
            for и, з in телефоны:
                f.write(json.dumps({'ts': теперь, 'инн': и, 'телефон': з},
                                   ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        d['почт_в_базе_итого'] = c.execute(
            'select count(*) from emails').fetchone()[0]
        d['компаний_с_почтой_итого'] = c.execute(
            'select count(distinct inn) from emails').fetchone()[0]
    c.close()
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
