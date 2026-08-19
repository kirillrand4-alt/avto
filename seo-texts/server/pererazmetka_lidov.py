# -*- coding: utf-8 -*-
r"""Переразметить уже собранные лиды новым классификатором.

Владелец 19.08: «из собранной статистики ответов нужно приоритеты переписать,
а то он пишет горячий на всё подряд». Правка самого классификатора действует
только на НОВЫЕ письма — уже разобранные лиды остаются со старой меткой, и
менеджер по-прежнему видит «горячий» на отказах. Здесь пересчитываем метки по
сохранённому тексту ответа.

Каждое изменение пишем в lead_events — чтобы в карточке было видно, что метку
сменила переразметка, а не человек.

    python pererazmetka_lidov.py            посчитать
    python pererazmetka_lidov.py --primenit применить
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender')
БД = r'C:\sender\sender.db'


def разбор(применять=False):
    from sender.reply_classify import classify_reply
    s = sqlite3.connect(БД, timeout=90)
    s.row_factory = sqlite3.Row
    строки = [dict(r) for r in s.execute(
        "select id, coalesce(reply_kind,'') было, coalesce(need,'') текст "
        "from leads where coalesce(need,'')<>''")]
    правки, свод = [], {}
    for r in строки:
        стало = classify_reply('', r['текст']).kind
        if стало and стало != r['было']:
            правки.append((r['id'], r['было'], стало))
            к = '%s -> %s' % (r['было'] or '(пусто)', стало)
            свод[к] = свод.get(к, 0) + 1
    итог = {'лидов': len(строки), 'к_переразметке': len(правки),
            'переходы': dict(sorted(свод.items(), key=lambda kv: -kv[1]))}
    if применять and правки:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for lid, было, стало in правки:
                s.execute('update leads set reply_kind=?, updated_at=? where id=?',
                          (стало, ts, lid))
                s.execute('insert into lead_events(lead_id, actor_user_id, action, '
                          'from_status, to_status, detail_json, created_at) '
                          'values(?,?,?,?,?,?,?)',
                          (lid, None, 'reply_kind_recheck', было, стало,
                           json.dumps({'причина': 'переразметка 19.08: телефон в '
                                       'подписи больше не делает ответ горячим'},
                                      ensure_ascii=False), ts))
        итог['переразмечено'] = len(правки)
        итог['стало'] = dict(s.execute(
            "select coalesce(reply_kind,'(пусто)'), count(*) from leads "
            'group by 1 order by 2 desc').fetchall())
    s.close()
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(разбор('--primenit' in sys.argv), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
