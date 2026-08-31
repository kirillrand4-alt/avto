# -*- coding: utf-8 -*-
r"""Долить Партию 935: новые мейеровские компании и адреса к уже стоящим в ней.

Владелец 30.08: «ступень где 1505 и туда же вообще без выручки — заливай в 935
плюс докинь контакты в те, которые уже там были».

КОГО БЕРЁМ (мягкая ступень, выбранная владельцем):
  * направление мейер;
  * паспорт сайта есть — любой непустой, полноту не требуем;
  * есть адрес, снятый со страницы ТОГО ЖЕ домена, что и паспорт, либо домен
    самого адреса совпадает с доменом сайта;
  * выручка от 30 млн ЛИБО неизвестна вовсе (владелец: «туда же закинем вообще
    без выручки»);
  * компании ещё нет в Партии 935.

ЧТО ЕЩЁ: тем, кто в партии уже стоит, дописываем недостающие адреса своего
домена — не больше трёх на компанию, чтобы партия не распухла втрое.

ЧЕГО НЕ ДЕЛАЕМ. Ничего не отправляем и не активируем: холд владельца на
рассылку и прогрев в силе, кампании остаются в состоянии draft. Это заливка
адресов, а не запуск.

ОТСЕВ на входе, помимо гейта, которым адреса добывались:
  * стоп-лист панели (suppression) — туда писать нельзя;
  * пометки «спам-ловушка», «скрытый», «не использовать» — канон репозитория;
  * адреса, уже стоящие в recipients (у таблицы уникальный индекс по email).

    python zaliv_935.py             посчитать, ничего не писать
    python zaliv_935.py --delat     залить
"""
import json
import os
import re
import sqlite3
import sys
import time

ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
ЖУРНАЛ = r'C:\sender\server\zaliv-935.jsonl'
ПОРОГ_ВЫРУЧКИ = 30_000_000
ДОБАВОК_НА_КОМПАНИЮ = 3      # сколько адресов дописываем тем, кто уже в партии
ПАРТИЯ = 'партия-935'

РОЛЕВЫЕ = re.compile(r'^(?:info|mail|office|sales|zakaz|order|post|contact|'
                     r'kontakt|general|admin|adm|reception|priem|sekret)', re.I)


def _журнал(запись):
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(запись, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _домен(строка):
    d = re.sub(r'^https?://', '', str(строка or '').strip().lower()).split('/')[0]
    return d[4:] if d.startswith('www.') else d


def _родня(a, b):
    return bool(a) and bool(b) and (a == b or a.endswith('.' + b) or b.endswith('.' + a))


def собрать():
    S = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True,
                        timeout=60)
    в935 = set(str(r[0]) for r in S.execute(
        "select distinct inn from recipients where source=? and coalesce(inn,'')<>''",
        (ПАРТИЯ,)))
    уже_адреса = set(r[0].lower() for r in S.execute(
        "select email from recipients where coalesce(email,'')<>''"))
    стоп = set()
    try:
        for (e,) in S.execute("select email from suppression "
                              "where coalesce(email,'')<>''"):
            стоп.add(str(e).lower())
    except sqlite3.Error:
        pass
    S.close()

    E = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True,
                        timeout=180)
    M = "coalesce(division,'') like '%meyer%'"
    комп = {}
    for i, n, s, c, rev, reg, ok in E.execute(
            "select inn, coalesce(name,''), coalesce(site,''), "
            "coalesce(cand_site,''), revenue_rub, coalesce(region,''), "
            "coalesce(okved,'') from companies where " + M):
        комп[str(i)] = {'name': n, 'дом': _домен(s or c), 'rev': rev,
                        'region': reg, 'okved': ok, 'паспорт': False}
    for i, s in E.execute("select inn, coalesce(site,'') from site_facts "
                          "where coalesce(facts_json,'')<>''"):
        i = str(i)
        if i in комп:
            комп[i]['паспорт'] = True
            if s:
                комп[i]['дом'] = _домен(s)
    свои = {}
    for i, e, r, u, п in E.execute(
            "select inn, lower(email), coalesce(role,''), coalesce(source_url,''), "
            "coalesce(pometka,'') from emails where coalesce(email,'')<>''"):
        i = str(i)
        if i not in комп:
            continue
        низ = п.lower()
        if any(x in низ for x in ('спам-ловушк', 'скрыт', 'не использовать')):
            continue
        д = комп[i]['дом']
        if not ((u and _родня(_домен(u), д)) or _родня(e.split('@')[-1], д)):
            continue
        if e in стоп:
            continue
        свои.setdefault(i, []).append({'email': e, 'role': r})
    E.close()

    def годна(i):
        k = комп[i]
        if not k['паспорт'] or i not in свои:
            return False
        rev = k['rev']
        return (rev is None or rev <= 0) or rev >= ПОРОГ_ВЫРУЧКИ

    новые = sorted(i for i in комп if i not in в935 and годна(i))
    добор = sorted(i for i in в935 if i in свои)
    return комп, свои, в935, уже_адреса, новые, добор


def _лучшие(адреса, сколько):
    """Сначала с внятной ролью, потом общие ящики, потом остальные."""
    def вес(a):
        роль = (a['role'] or '').strip()
        if роль and роль not in ('общий',):
            return 0
        return 1 if РОЛЕВЫЕ.match(a['email']) else 2
    return sorted(адреса, key=lambda a: (вес(a), a['email']))[:сколько]


def залить(делать=False):
    комп, свои, в935, уже_адреса, новые, добор = собрать()
    строки = []
    for i in новые:
        for a in _лучшие(свои[i], 1):
            if a['email'] not in уже_адреса:
                строки.append((i, a, 'новая компания'))
    дописано = 0
    for i in добор:
        есть = sum(1 for a in свои[i] if a['email'] in уже_адреса)
        мест = max(0, ДОБАВОК_НА_КОМПАНИЮ - есть)
        for a in _лучшие([x for x in свои[i] if x['email'] not in уже_адреса], мест):
            строки.append((i, a, 'добор к стоящей'))
            дописано += 1
    итог = {'мейер_всего': len(комп), 'в_партии_935': len(в935),
            'новых_компаний': len(новые), 'добор_компаний': len(добор),
            'строк_к_заливке': len(строки),
            'из_них_новых_компаний': len(строки) - дописано,
            'из_них_добор': дописано}
    if not делать or not строки:
        return итог
    # формат отметки как у существующих строк партии: ISO с микросекундами.
    # time.strftime %f не понимает — это datetime, а не time.
    from datetime import datetime
    сейчас = datetime.now().isoformat()
    к_записи = []
    for i, a, зачем in строки:
        k = комп[i]
        к_записи.append((
            i, a['email'], a['email'].split('@')[-1], k['name'], k['okved'],
            'meyer', 'unknown', ПАРТИЯ,
            json.dumps({'gruppy': ['Партия 935'], 'volna': 'мейер-паспорт-30.08',
                        'zachem': зачем, 'rol': a['role'] or ''},
                       ensure_ascii=False),
            сейчас, сейчас, k['region'],
            1 if РОЛЕВЫЕ.match(a['email']) else 0))
    c = sqlite3.connect(SENDER, timeout=120)
    c.execute('PRAGMA busy_timeout=120000')
    легло = 0
    for k in range(0, len(к_записи), 500):
        кусок = к_записи[k:k + 500]
        for _ in range(8):
            try:
                cur = c.executemany(
                    'insert or ignore into recipients(inn,email,domain,company_name,'
                    'okved,segment,valid_status,source,extra_json,created_at,'
                    'updated_at,region,role_based) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    кусок)
                c.commit()
                легло += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                break
            except sqlite3.OperationalError:
                try:
                    c.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(5)
    итог['залито_строк'] = легло
    итог['теперь_в_935_строк'] = c.execute(
        'select count(*) from recipients where source=?', (ПАРТИЯ,)).fetchone()[0]
    итог['теперь_в_935_инн'] = c.execute(
        'select count(distinct inn) from recipients where source=?',
        (ПАРТИЯ,)).fetchone()[0]
    c.close()
    _журнал({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'ИТОГ': итог,
             'адреса': [s[1]['email'] for s in строки]})
    return итог


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(залить('--delat' in sys.argv[1:]), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
