# -*- coding: utf-8 -*-
r"""Судья ролей: провайдер сверяет нашу роль с куском страницы, я смотрю только споры.

Зачем именно так. Мой глаз точен, но стоит квоты сессии, которую владелец просил
беречь. Правило дешёвое, но слепое: попытка ставить роль по «одной должности в
окне 500 знаков» дала 4 ошибки из 8 — окно захватывает соседние карточки людей.
Провайдер посередине: видит контекст и стоит центы (600 токенов на адрес, у
gpt-5.6-luna это 0,2 $ за миллион входа — около 12 центов на тысячу адресов).

Порядок: судья размечает всё, человек читает ТОЛЬКО расхождения.

Честность замера держится на трёх вещах:
  * судье НЕ показывают нашу роль — иначе он будет с ней соглашаться;
  * ему дают ровно тот кусок страницы, где стоит адрес, и ничего сверх;
  * ответ «не видно» разрешён и поощряется: пустое лучше правдоподобного.

Результат в enrich.db, таблица roli_sud — сервер переживает рестарт песочницы,
в отличие от файлов в возвращаемом JSON.

Запуск:
    python roli_sudya.py --sudit [сколько компаний] [потоков]
    python roli_sudya.py --spory [сколько показать]
    python roli_sudya.py --stat
"""
import concurrent.futures as cf
import gzip
import json
import os
import re
import sqlite3
import sys
import threading
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ZHURNAL = os.path.join(DIR, 'zenno_razbor.jsonl')
MODEL = os.environ.get('SUDYA_MODEL', 'gpt-5.6-luna')

SHEMA = """CREATE TABLE IF NOT EXISTS roli_sud(
    inn TEXT, email TEXT, nasha_rol TEXT, rol_sudi TEXT, dovod TEXT,
    soglasie INTEGER, ts TEXT, model TEXT,
    PRIMARY KEY (inn, email))"""

ROLI = ('гл.инженер|гл.энергетик|гл.механик|техдиректор|нач.производства|'
        'гл.технолог|нач.цеха|АСУ/КИПиА|техконтакт|инженер (не главный)|'
        'снабжение/закупки|директор|продажи|приёмная|бухгалтерия|кадры|общий')

PROMPT = """Определи РОЛЬ каждого email по куску страницы сайта, где он найден.

Компания: «%(name)s».

Роль выбирай СТРОГО из списка: %(roli)s

Правила:
- роль ставится по тому, что написано РЯДОМ с адресом: должность человека,
  название отдела, заголовок блока;
- если рядом перечислено НЕСКОЛЬКО отделов, а адрес один общий — это «общий»,
  угадывать ближайший нельзя;
- если рядом ничего нет — «общий»;
- «приёмная» это секретарь и приёмная руководителя, «директор» — сам руководитель;
- «техконтакт» — техническая служба без уточнения должности.

Для каждого адреса верни короткий ДОВОД — дословную фразу со страницы, по
которой определил. Не нашёл фразы — довод пустой и роль «общий».

Куски страницы:
%(kuski)s

Верни СТРОГО JSON без markdown:
{"emails":[{"email":"","role":"","dovod":"дословная фраза со страницы или пусто"}]}"""


def _bd():
    # check_same_thread=False: пишем из пула потоков, но ВСЕГДА под общим замком
    # (zamok в sudit) — иначе sqlite справедливо ругается «объект создан в другом
    # потоке». Замок обязателен: без него параллельные INSERT перемешают
    # транзакции.
    c = sqlite3.connect(BD, timeout=60, check_same_thread=False)
    c.execute(SHEMA)
    c.execute('PRAGMA journal_mode=WAL')
    c.commit()
    return c


def _tekst(inn):
    p = os.path.join(KESH, '%s.json.gz' % inn)
    if not os.path.exists(p):
        return ''
    try:
        with gzip.open(p, 'rb') as f:
            d = json.loads(f.read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return ''
    t = '\n'.join(re.sub(r'<[^>]+>', ' ', pg.get('html') or '')
                  for pg in (d.get('pages') or []))
    return re.sub(r'[ \t\xa0]+', ' ', t)


def _kusok(tekst, adres, okno=700):
    """Окрестность адреса — ровно то, по чему человек и судит."""
    tn = tekst.lower()
    out = []
    for m in list(re.finditer(re.escape(adres.lower()), tn))[:2]:
        n = max(0, m.start() - okno)
        k = min(len(tekst), m.end() + okno // 2)
        out.append(re.sub(r'\s+', ' ', tekst[n:k]).strip())
    return '\n...\n'.join(out)


def _json_iz(otvet):
    s = re.sub(r'^```(?:json)?|```$', '', (otvet or '').strip(), flags=re.M).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        a, b = s.find('{'), s.rfind('}')
        if a >= 0 and b > a:
            try:
                return json.loads(s[a:b + 1])
            except Exception:  # noqa: BLE001
                pass
    return None


def _kompanii(skolko):
    """Свежие компании из журнала разбора, у которых есть страницы и роли."""
    zap = []
    for s in open(ZHURNAL, encoding='utf-8', errors='replace'):
        if '"inn"' not in s:
            continue
        try:
            zap.append(json.loads(s))
        except Exception:  # noqa: BLE001
            pass
    c = _bd()
    uzhe = {(r[0], r[1]) for r in c.execute('select inn, email from roli_sud')}
    c.close()
    out = []
    for d in reversed(zap):
        inn = str(d.get('inn') or '')
        em = [e for e in (d.get('emails') or [])
              if e.get('email') and (inn, e['email']) not in uzhe]
        if not em:
            continue
        t = _tekst(inn)
        if not t:
            continue
        kuski = []
        for e in em[:10]:
            k = _kusok(t, e['email'])
            if k:
                kuski.append((e['email'], (e.get('role') or ''), k))
        if kuski:
            out.append({'inn': inn, 'name': str(d.get('name') or '')[:70],
                        'kuski': kuski})
        if len(out) >= skolko:
            break
    return out


def sudit(skolko=60, potokov=10):
    import gen_provider
    kl = gen_provider.make_client()
    komp = _kompanii(skolko)
    zamok = threading.Lock()
    c = _bd()
    itog = {'компаний': 0, 'адресов': 0, 'согласий': 0, 'споров': 0, 'сбоев': 0}

    def odin(k):
        kuski_txt = '\n\n'.join(
            '--- %s\n%s' % (a, t) for a, _r, t in k['kuski'])
        promt = PROMPT % {'name': k['name'], 'roli': ROLI, 'kuski': kuski_txt}
        try:
            msg = gen_provider.call(kl, [{'role': 'user', 'content': promt}],
                                    model=MODEL, attempts=2)
            otvet = ''.join(b.text for b in getattr(msg, 'content', [])
                            if getattr(b, 'type', '') == 'text'
                            and getattr(b, 'text', ''))
        except Exception:  # noqa: BLE001
            with zamok:
                itog['сбоев'] += 1
            return
        d = _json_iz(otvet) or {}
        sud = {str(x.get('email') or '').lower(): x
               for x in (d.get('emails') or []) if isinstance(x, dict)}
        with zamok:
            itog['компаний'] += 1
            for adres, nasha, _t in k['kuski']:
                x = sud.get(adres.lower())
                if not x:
                    continue
                rol_s = str(x.get('role') or '').strip()
                sogl = int(rol_s == (nasha or 'общий'))
                itog['адресов'] += 1
                itog['согласий' if sogl else 'споров'] += 1
                c.execute('INSERT OR REPLACE INTO roli_sud(inn,email,nasha_rol,'
                          'rol_sudi,dovod,soglasie,ts,model) VALUES(?,?,?,?,?,?,?,?)',
                          (k['inn'], adres, nasha, rol_s,
                           str(x.get('dovod') or '')[:300], sogl,
                           time.strftime('%Y-%m-%dT%H:%M:%S'), MODEL))
            c.commit()

    with cf.ThreadPoolExecutor(max_workers=potokov) as pul:
        list(pul.map(odin, komp))
    itog['согласие_%'] = round(100 * itog['согласий'] / max(1, itog['адресов']), 1)
    c.close()
    return itog


def spory(skolko=15):
    c = _bd()
    c.row_factory = sqlite3.Row
    out = [dict(r) for r in c.execute(
        'select inn, email, nasha_rol, rol_sudi, dovod from roli_sud '
        'where soglasie=0 order by ts desc limit ?', (skolko,))]
    c.close()
    return out


def stat():
    c = _bd()
    vsego = c.execute('select count(*) from roli_sud').fetchone()[0]
    sogl = c.execute('select count(*) from roli_sud where soglasie=1').fetchone()[0]
    pary = {'%s -> %s' % (r[0] or '(пусто)', r[1]): r[2] for r in c.execute(
        'select nasha_rol, rol_sudi, count(*) from roli_sud where soglasie=0 '
        'group by 1,2 order by 3 desc limit 12')}
    c.close()
    return {'проверено_адресов': vsego, 'согласий': sogl,
            'согласие_%': round(100 * sogl / max(1, vsego), 1),
            'частые_расхождения': pary}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        print(json.dumps(stat(), ensure_ascii=False, indent=1))
    elif a[0] == '--sudit':
        print(json.dumps(sudit(int(a[1]) if len(a) > 1 else 60,
                               int(a[2]) if len(a) > 2 else 10),
                         ensure_ascii=False, indent=1))
    elif a[0] == '--spory':
        print(json.dumps(spory(int(a[1]) if len(a) > 1 else 15),
                         ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
