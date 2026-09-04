# -*- coding: utf-8 -*-
r"""Поставить на пересбор паспорта с чужими источниками — по правилу владельца.

  * СМЕСЬ своё+чужое (класс «Аэлиты») — примесь доказана, факты могли приехать
    с чужой страницы: карточку очищаем, чтобы негодные факты не ушли в письмо,
    и ставим в очередь на пересбор;
  * один чужой домен, но контактов оттуда нет — только в очередь на пересбор,
    факты пока оставляем: письмо по ним хотя бы связное;
  * один чужой домен и контакты оттуда же — НЕ ТРОГАЕМ (владелец 04.09).

Признак очереди — format=0: готовность считается по версии формата.
"""
import json, os, re, sqlite3, time

def дом(с):
    d = re.sub(r'^https?://', '', str(с or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d
def родня(a, b):
    return bool(a) and bool(b) and (a == b or a.endswith('.' + b) or b.endswith('.' + a))

смесь, только_очередь = [], []
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=600)
почты = {}
for инн, e, u in c.execute("select inn, lower(email), coalesce(source_url,'') from emails"):
    почты.setdefault(str(инн), []).append((e, u))
for инн, сайт, сырое in c.execute(
        "select inn, coalesce(site,''), coalesce(sources_json,'') from site_facts "
        "where coalesce(facts_json,'')<>''"):
    try:
        источники = json.loads(сырое or '[]')
    except Exception:                                          # noqa: BLE001
        continue
    if not isinstance(источники, list) or not источники:
        continue
    свой = дом(сайт)
    if not свой:
        continue
    чужие = [u for u in источники if not родня(дом(u), свой)]
    if not чужие:
        continue
    инн = str(инн)
    домены = {дом(u) for u in чужие}
    if len(чужие) < len(источники):
        смесь.append(инн)
    elif len(домены) == 1:
        д = next(iter(домены))
        if any(родня(дом(u), д) or родня(e.split('@')[-1], д)
               for e, u in почты.get(инн, [])):
            continue                      # правило владельца: не трогаем
        только_очередь.append(инн)
    else:
        только_очередь.append(инн)
c.close()

ПРИЧИНА = 'пересбор 04.09: в источниках был чужой домен'
w = sqlite3.connect(r'C:\sender\enrich.db', timeout=300)
w.execute('PRAGMA busy_timeout=300000')
легло = {'очищено_и_в_очередь': 0, 'только_в_очередь': 0}
for k in range(0, len(смесь), 400):
    кусок = смесь[k:k + 400]
    w.execute("update site_facts set facts_json='', format=0, note=? "
              "where inn in (%s)" % ','.join('?' * len(кусок)), [ПРИЧИНА + ' (смесь)'] + кусок)
    легло['очищено_и_в_очередь'] += len(кусок)
    w.commit()
for k in range(0, len(только_очередь), 400):
    кусок = только_очередь[k:k + 400]
    w.execute("update site_facts set format=0, note=? "
              "where inn in (%s)" % ','.join('?' * len(кусок)), [ПРИЧИНА] + кусок)
    легло['только_в_очередь'] += len(кусок)
    w.commit()
w.close()
ж = r'C:\sender\server\pasporta-sbros-04-09.jsonl'
with open(ж, 'w', encoding='utf-8') as f:
    for и in смесь:
        f.write(json.dumps({'inn': и, 'что': 'очищен и в очередь'}, ensure_ascii=False) + '\n')
    for и in только_очередь:
        f.write(json.dumps({'inn': и, 'что': 'в очередь'}, ensure_ascii=False) + '\n')
    f.flush(); os.fsync(f.fileno())
print(json.dumps({'смесь_очищено': len(смесь), 'в_очередь_без_очистки': len(только_очередь),
                  'применено': легло, 'журнал': ж}, ensure_ascii=False, indent=1))
