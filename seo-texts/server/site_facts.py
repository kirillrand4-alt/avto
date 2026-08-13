# -*- coding: utf-8 -*-
r"""Факты о продукции и новости с сайта предприятия — для персонализации писем.

По ТЗ соседней сессии (TZ-OBHOD-SAYTOV-fakty-dlya-pisem.md, 13.08). Смысл: письмо
во втором абзаце называет, что предприятие выпускает. Сейчас генератор берёт одно
поле activity, и когда там пусто — модель пересказывает НАЗВАНИЕ ОКВЭД как
продукцию. Замеры соседей: «Машины Сладости» получили «конфеты-суфле и какао-
порошок» (какао — это название кода 10.82), «Пивкомбинат Балаковский» по сайту
делает печенье и пряники, а не пиво. Слепое сравнение с живым редактором: 2,89
против 4,11 по конкретности — разрыв ровно в том, что она открывает сайт.

Отсюда три запрета ТЗ, которые вшиты в промпт: ничего не выводить из ОКВЭД, ничего
не выводить из названия компании, не обобщать до отрасли. Пустое поле — нормальный
результат, пустое лучше правдоподобного.

Страницы берём ИЗ КЭША (их привозит Зенка или обычный краул) — сеть здесь не нужна.
Результат кладём в enrich.db, таблица site_facts: это сервер, он переживает рестарт
песочницы.

Команды:
    python site_facts.py --ochered [N]    поставить компании кампании 8 в очередь Зенки
                                          за фактами (строка «ИНН;url;facts»)
    python site_facts.py --sobrat [N]     разобрать страницы из кэша провайдером
    python site_facts.py --stat           что собрано
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ZENNO = os.environ.get('ZENNO_DIR', r'C:\seostat\drop\zenno')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER_BD = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
KAMPANIYA = int(os.environ.get('KAMPANIYA', '8'))
MODEL = os.environ.get('FACTS_MODEL', 'claude-fable-5')

SHEMA = """CREATE TABLE IF NOT EXISTS site_facts(
    inn TEXT PRIMARY KEY,
    facts_json  TEXT,
    sources_json TEXT,
    site TEXT,
    ts   TEXT,
    note TEXT)"""

PROMPT = """Ты собираешь факты о предприятии ТОЛЬКО из текста его сайта — для холодного
письма, где второй абзац называет, что предприятие выпускает.

ТРИ ЗАПРЕТА (нарушение делает работу бессмысленной):
1. Ничего не выводить из ОКВЭД: код — классификатор, а не ассортимент.
2. Ничего не выводить из названия компании: «Пивкомбинат» может делать печенье,
   «Молзавод» — мороженое.
3. Не обобщать до отрасли: «молочная продукция» вместо «масло, крем-сыр, сыр»
   бесполезна — такая фраза подходит любому заводу и читается как массовая рассылка.

Все значения — СЛОВАМИ САЙТА, без пересказа. Пустое поле — нормальный результат;
пустое лучше правдоподобного.

Компания: %(name)s, ИНН %(inn)s, сайт %(site)s.

Страницы сайта (адрес и текст):
%(stranicy)s

Верни СТРОГО JSON:
{"продукция": ["до 12 позиций или групп, словами сайта"],
 "упаковка_фасовка": ["флоу-пак", "ведро 5 кг"],
 "сырьё": ["что заходит на вход"],
 "мощности": ["ТОЛЬКО фразы с числом, дословно"],
 "контроль_качества": ["ХАССП", "ISO 22000", "собственная лаборатория"],
 "новости": [{"дата": "как на сайте", "заголовок": "дословно",
              "url": "прямая ссылка", "текст": "первые 2-3 предложения дословно"}],
 "свежая_новость": "первая подходящая из новостей, с датой",
 "цитата": "одна буквальная строка со страницы, подтверждающая продукцию",
 "источники": ["url, откуда взято"],
 "уверенность": "высокая|средняя|низкая"}

Про новости: годятся запуск и модернизация линии, цеха, склада; рост мощности —
особенно с числом; новый продукт или упаковка; сертификация; новое оборудование;
выход в сеть или регион; награда на отраслевой выставке. НЕ годятся поздравления,
дни рождения, корпоративы, «работаем в штатном режиме», перепечатки чужих новостей.
Без даты новость бесполезна — «недавно» писать нельзя. Глубина — последние 12
месяцев, до 10 записей, свежая первой."""


def _bd():
    c = sqlite3.connect(BD, timeout=60)
    c.execute(SHEMA)
    c.execute('PRAGMA journal_mode=WAL')
    c.commit()
    return c


def _kompanii_kampanii():
    """ИНН и сайты компаний очереди подтверждения (по ТЗ — сперва кампания Meyer)."""
    s = sqlite3.connect(SENDER_BD)
    s.row_factory = sqlite3.Row
    inny = [str(r['inn']) for r in s.execute(
        "select distinct r.inn from confirm_reviews cr "
        "join recipients r on r.id=cr.recipient_id "
        "where cr.campaign_id=? and cr.status='pending' and r.inn is not null",
        (KAMPANIYA,)).fetchall()]
    s.close()
    if not inny:
        return []
    c = sqlite3.connect(BD)
    c.row_factory = sqlite3.Row
    q = ','.join('?' * len(inny))
    out = []
    for r in c.execute("select inn, coalesce(name,'') name, coalesce(site,'') site, "
                       "coalesce(cand_site,'') cand from companies where inn in (%s)" % q,
                       inny):
        u = (r['site'] or r['cand'] or '').strip()
        if u:
            out.append({'inn': str(r['inn']), 'name': r['name'], 'site': u})
    c.close()
    return out


def ochered(predel=100):
    """Поставить компании в очередь Зенки С МЕТКОЙ facts — она возьмёт каталог и
    новости вместо страницы контактов."""
    komp = _kompanii_kampanii()[:predel]
    if not komp:
        return {'нечего_ставить': True}
    put = os.path.join(ZENNO, 'ochered.txt')
    os.makedirs(ZENNO, exist_ok=True)
    with open(put, 'a', encoding='utf-8') as f:
        f.write('\n'.join('%s;%s;facts' % (k['inn'], k['site']) for k in komp) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'поставлено': len(komp), 'файл': put}


def _stranicy(inn, predel_znakov=60000):
    """Страницы компании из кэша: [(url, текст)] — теги срезаны, порядок сохранён."""
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return []
    try:
        with gzip.open(p, 'rb') as f:
            d = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return []
    out, vsego = [], 0
    for pg in (d.get('pages') or []):
        h = pg.get('html') or ''
        if not h:
            continue
        t = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        t = re.sub(r'<[^>]+>', ' ', t)
        for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'),
                     ('&laquo;', '«'), ('&raquo;', '»'), ('&mdash;', '-')):
            t = t.replace(a, b)
        t = re.sub(r'\s+', ' ', t).strip()
        if len(t) < 200:
            continue
        # ТЗ требует дословности: режем страницу, но не выбрасываем целиком
        kusok = t[:8000]
        if vsego + len(kusok) > predel_znakov:
            break
        vsego += len(kusok)
        out.append((pg.get('url') or '', kusok))
    return out


def sobrat(predel=50):
    """Разобрать страницы провайдером и записать в site_facts."""
    import gen_provider as GP
    c = _bd()
    c.row_factory = sqlite3.Row
    gotovye = {str(r[0]) for r in c.execute('select inn from site_facts')}
    komp = [k for k in _kompanii_kampanii() if k['inn'] not in gotovye][:predel]
    if not komp:
        c.close()
        return {'все_разобраны': len(gotovye)}

    klient = GP.make_client()
    itog = {'разобрано': 0, 'без_страниц': 0, 'сбоев': 0, 'с_продукцией': 0,
            'с_новостями': 0}
    for k in komp:
        stranicy = _stranicy(k['inn'])
        if not stranicy:
            c.execute("INSERT OR REPLACE INTO site_facts(inn, facts_json, sources_json, "
                      "site, ts, note) VALUES(?,?,?,?,?,?)",
                      (k['inn'], '', '', k['site'],
                       time.strftime('%Y-%m-%dT%H:%M:%S'), 'страниц в кэше нет'))
            c.commit()
            itog['без_страниц'] += 1
            continue
        tekst = '\n\n'.join('--- %s\n%s' % (u, t) for u, t in stranicy)
        vopros = PROMPT % {'name': k['name'][:80], 'inn': k['inn'],
                           'site': k['site'], 'stranicy': tekst}
        try:
            msg = GP.call(klient, [{'role': 'user', 'content': vopros}],
                          model=MODEL, attempts=3)
            fakty = GP.parse_json(msg)
        except Exception as e:  # noqa: BLE001
            itog['сбоев'] += 1
            c.execute("INSERT OR REPLACE INTO site_facts(inn, facts_json, sources_json, "
                      "site, ts, note) VALUES(?,?,?,?,?,?)",
                      (k['inn'], '', '', k['site'],
                       time.strftime('%Y-%m-%dT%H:%M:%S'), 'провайдер: ' + str(e)[:120]))
            c.commit()
            continue
        istochniki = fakty.get('источники') or [u for u, _t in stranicy]
        c.execute("INSERT OR REPLACE INTO site_facts(inn, facts_json, sources_json, "
                  "site, ts, note) VALUES(?,?,?,?,?,?)",
                  (k['inn'], json.dumps(fakty, ensure_ascii=False),
                   json.dumps(istochniki, ensure_ascii=False), k['site'],
                   time.strftime('%Y-%m-%dT%H:%M:%S'), ''))
        c.commit()
        itog['разобрано'] += 1
        if fakty.get('продукция'):
            itog['с_продукцией'] += 1
        if fakty.get('новости'):
            itog['с_новостями'] += 1
    c.close()
    return itog


def stat():
    c = _bd()
    c.row_factory = sqlite3.Row
    vsego = c.execute('select count(*) from site_facts').fetchone()[0]
    s_faktami = c.execute("select count(*) from site_facts where coalesce(facts_json,'')<>''"
                          ).fetchone()[0]
    prim = [dict(r) for r in c.execute(
        "select inn, site, substr(coalesce(facts_json,''),1,300) f, note "
        "from site_facts order by ts desc limit 3")]
    c.close()
    return {'записей': vsego, 'с_фактами': s_faktami, 'последние': prim}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        print(json.dumps(stat(), ensure_ascii=False, indent=1))
    elif a[0] == '--ochered':
        print(json.dumps(ochered(int(a[1]) if len(a) > 1 else 100),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--sobrat':
        print(json.dumps(sobrat(int(a[1]) if len(a) > 1 else 50),
                         ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
