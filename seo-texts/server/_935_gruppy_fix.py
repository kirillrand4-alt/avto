# -*- coding: utf-8 -*-
r"""Прописать группу «Партия 935» так, как её понимает панель.

Разбор 17.08: выпадашка «группа» на экране подтверждения — это
store.recipient_groups(), где группа получателя = segment ПЛЮС список
extra_json.gruppy. Утренняя партия (920) лежит в gruppy; мой импорт заполнил
segment=kc/meyer и пустой extra_json — получатели в группе «Партия 935» не
видны, зато в списке групп появился мусор «kc (2772)» и «meyer (888)».

Три правки одной транзакцией:
  1) всем строкам source='партия-935' добавить «Партия 935» в extra_json.gruppy;
  2) убрать мой segment kc/meyer (направление письма решает карточка компании,
     а не этот столбец — ai_quota._kandidaty_po_gruppe, строки 606-615);
  3) 892 компании отбора, чьи адреса живут в других группах, подключить тем же
     списком gruppy — НЕ трогая их source/segment: механизм для того и заведён
     («компания из новостной кампании, попавшая ещё и в отраслевую партию»).
     Подключаем ТОЛЬКО если ИНН получателя совпадает с ИНН компании отбора:
     общий ящик другого юрлица в партию не тянем.
"""
import json
import sqlite3
import sys

ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
ГРУППА = 'Партия 935'

САЙТОВЫЕ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТЫЕ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
          "and coalesce(e.pometka,'') not like '%скрыт%' "
          "and coalesce(e.pometka,'') not like '%не использовать%'")


def _с_группой(extra):
    try:
        d = json.loads(extra) if (extra or '').strip() else {}
        if not isinstance(d, dict):
            d = {}
    except Exception:  # noqa: BLE001
        d = {}
    гр = [str(x).strip() for x in (d.get('gruppy') or []) if str(x).strip()]
    if ГРУППА in гр:
        return None
    d['gruppy'] = гр + [ГРУППА]
    return json.dumps(d, ensure_ascii=False)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    e = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    отбор_инн = {str(r[0]) for r in e.execute(
        "select k.inn from companies k "
        "where exists (select 1 from emails x where x.inn=k.inn and %s and %s) "
        "and exists (select 1 from site_facts f where f.inn=k.inn "
        " and coalesce(f.format,0)>=2 and f.facts_json like '%%\"продукция\": [\"%%')"
        % (САЙТОВЫЕ.replace('e.', 'x.'), ЧИСТЫЕ.replace('e.', 'x.')))}
    e.close()

    s = sqlite3.connect(SENDER, timeout=90)
    s.row_factory = sqlite3.Row
    итог = {'отбор_компаний': len(отбор_инн), 'gruppy_добавлена': 0,
            'уже_была': 0, 'segment_очищен': 0,
            'чужая_группа_подключена': 0, 'чужой_ящик_не_наш_инн': 0}
    правки = []
    for r in s.execute("select id, coalesce(extra_json,'') ex, "
                       "coalesce(segment,'') seg, coalesce(inn,'') inn, "
                       "coalesce(source,'') src from recipients"):
        инн = ''.join(c for c in r['inn'] if c.isdigit())
        свой = r['src'] == 'партия-935'
        из_отбора = инн in отбор_инн
        if not (свой or из_отбора):
            continue
        новый_ex = _с_группой(r['ex'])
        новый_seg = None
        if свой and r['seg'] in ('kc', 'meyer'):
            новый_seg = ''
        if новый_ex is None and новый_seg is None:
            итог['уже_была'] += 1
            continue
        правки.append((r['id'], новый_ex, новый_seg))
        if новый_ex is not None:
            итог['gruppy_добавлена'] += 1
            if not свой:
                итог['чужая_группа_подключена'] += 1
        if новый_seg is not None:
            итог['segment_очищен'] += 1
    # чужие ящики: адрес компании отбора занят получателем с другим ИНН —
    # посчитать для доклада (мы их сознательно не подключаем)
    итог['чужой_ящик_не_наш_инн'] = итог['отбор_компаний'] - 0  # уточняется ниже

    with s:
        for rid, ex, seg in правки:
            if ex is not None and seg is not None:
                s.execute('update recipients set extra_json=?, segment=NULL, '
                          "updated_at=datetime('now') where id=?", (ex, rid))
            elif ex is not None:
                s.execute('update recipients set extra_json=?, '
                          "updated_at=datetime('now') where id=?", (ex, rid))
            else:
                s.execute('update recipients set segment=NULL, '
                          "updated_at=datetime('now') where id=?", (rid,))

    # пересчёт групп так же, как это делает панель
    счёт = {}
    охваченные_инн = set()
    for r in s.execute("select coalesce(segment,'') seg, "
                       "coalesce(extra_json,'') ex, coalesce(inn,'') inn "
                       'from recipients'):
        гр = set()
        if r['seg'].strip():
            гр.add(r['seg'].strip())
        if 'gruppy' in r['ex']:
            try:
                гр |= {str(x).strip() for x in
                       (json.loads(r['ex']).get('gruppy') or []) if str(x).strip()}
            except Exception:  # noqa: BLE001
                pass
        for g in гр:
            счёт[g] = счёт.get(g, 0) + 1
        if ГРУППА in гр:
            охваченные_инн.add(''.join(c for c in r['inn'] if c.isdigit()))
    s.close()
    итог['чужой_ящик_не_наш_инн'] = len(отбор_инн - охваченные_инн)
    итог['группы_после'] = sorted(счёт.items(), key=lambda kv: -kv[1])[:12]
    итог['компаний_отбора_в_группе'] = len(отбор_инн & охваченные_инн)
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
