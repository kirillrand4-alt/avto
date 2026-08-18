# -*- coding: utf-8 -*-
r"""Одна компания — один адрес в партии: снимаем лишние теги группы.

Найдено 18.08 после догруза: у 489 компаний группы «Партия 935» по два и более
получателя. Так вышло при первой заливке 17.08: правило смотрело, не занят ли
ВЫБРАННЫЙ адрес, но не смотрело, есть ли у компании в панели ДРУГОЙ адрес — и
заводило вторую строку. Плюс тег группы по ИНН подхватил соседние партии.
Кампания берёт кандидатов по группе, значит компания получила бы два письма.

Чиним мягко: у лишних строк убираем ТЕГ группы, саму строку и её source не
трогаем — она законно живёт в своей партии. Оставляем лучший адрес: сайтовый
важнее прочих, затем роль (техЛПР > снабжение > директор > продажи > общий),
при равенстве — тот, что уже писали или подтверждали.

    python dubli_v_gruppe.py            посчитать
    python dubli_v_gruppe.py --primenit снять лишние теги
"""
import json
import sqlite3
import sys
import time

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
ГРУППА = 'Партия 935'


def _ранг(роль):
    р = (роль or '').lower()
    for балл, куски in ((0, ('энерг', 'механ', 'инжен', 'техдир', 'технич',
                             'производ', 'технолог', 'конструктор')),
                        (1, ('снабж', 'закуп')), (2, ('директор', 'руковод')),
                        (3, ('прода', 'коммерч'))):
        if any(к in р for к in куски):
            return балл
    return 4


def разбор(применять=False):
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    сайтовые, роли = set(), {}
    for инн, em, роль, ист in c.execute(
            "select inn, lower(email), coalesce(role,''), coalesce(source,'') "
            "from emails where coalesce(email,'')<>''"):
        роли[(str(инн), em)] = роль
        if ист in ('own-site', 'zenno') or ист.startswith('сайт:'):
            сайтовые.add((str(инн), em))
    c.close()
    s = sqlite3.connect(SENDER, timeout=90)
    s.row_factory = sqlite3.Row
    по_инн = {}
    for r in s.execute("select id, coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                       "coalesce(extra_json,'') ex, coalesce(source,'') src "
                       "from recipients where extra_json like '%%%s%%'" % ГРУППА):
        инн = ''.join(ch for ch in r['inn'] if ch.isdigit())
        # ТЕГ ЧИТАЕМ РАЗБОРОМ JSON, а не по LIKE: та же строка «Партия 935»
        # остаётся в записи gruppy_ubrano — следе УЖЕ СНЯТОГО тега, и по LIKE
        # снятый получатель выглядит как состоящий в группе. Один раз это чуть
        # не стоило партии: «лучшим» мог оказаться получатель без тега, а тег
        # сняли бы с настоящего.
        try:
            _d = json.loads(r['ex']) if (r['ex'] or '').strip() else {}
        except Exception:  # noqa: BLE001
            _d = {}
        if ГРУППА not in [str(g) for g in (_d.get('gruppy') or [])]:
            continue
        if инн:
            по_инн.setdefault(инн, []).append(dict(r))
    # писали ли уже с этого адреса — такой не трогаем ни при каких условиях
    писали = {str(r[0]).lower() for r in s.execute(
        "select distinct lower(email) from confirm_reviews where coalesce(email,'')<>''")}
    итог = {'компаний_в_группе': len(по_инн), 'с_дублями': 0, 'лишних': 0,
            'снято_тегов': 0, 'оставили_из_за_письма': 0}
    примеры, снять = [], []
    for инн, ст in по_инн.items():
        if len(ст) < 2:
            continue
        итог['с_дублями'] += 1
        ст.sort(key=lambda r: (
            0 if r['em'] in писали else 1,
            0 if (инн, r['em']) in сайтовые else 1,
            _ранг(роли.get((инн, r['em']), '')), r['em']))
        лучший, прочие = ст[0], ст[1:]
        итог['лишних'] += len(прочие)
        for р in прочие:
            if р['em'] in писали:
                итог['оставили_из_за_письма'] += 1
                continue
            снять.append(р['id'])
        if len(примеры) < 5:
            примеры.append({'инн': инн, 'оставляем': лучший['em'],
                            'снимаем': [р['em'] for р in прочие][:3]})
    if применять and снять:
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        with s:
            for rid in снять:
                r = s.execute("select coalesce(extra_json,'') from recipients "
                              'where id=?', (rid,)).fetchone()
                try:
                    d = json.loads(r[0]) if (r[0] or '').strip() else {}
                    if not isinstance(d, dict):
                        d = {}
                except Exception:  # noqa: BLE001
                    d = {}
                d['gruppy'] = [g for g in (d.get('gruppy') or []) if g != ГРУППА]
                d.setdefault('gruppy_ubrano', []).append(
                    {'gruppa': ГРУППА, 'ts': ts, 'prichina': 'дубль компании в партии'})
                s.execute('update recipients set extra_json=?, updated_at=? where id=?',
                          (json.dumps(d, ensure_ascii=False), ts, rid))
                итог['снято_тегов'] += 1
    s.close()
    итог['примеры'] = примеры
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    и = разбор('--primenit' in sys.argv)
    прим = и.pop('примеры', [])
    print(json.dumps({'примеры': прим}, ensure_ascii=False, indent=1))
    print(json.dumps(и, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
