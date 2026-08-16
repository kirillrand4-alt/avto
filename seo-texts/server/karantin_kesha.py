# -*- coding: utf-8 -*-
r"""Увести из кэша страницы, скачанные с ЧУЖИХ сайтов.

Соседняя сессия 16.08 про «Трастметалл»: «это тот самый карантинный
mismatch-паспорт, грязь ещё в кэше». Замечание точное и шире одного случая:
паспорт мы убрали, привязку сняли, а файл `<ИНН>.json.gz` со страницами чужого
сайта остался лежать — и его читает не только разбор фактов, но и всё, что
работает по кэшу: сбор контактов, сверка, замеры качества.

Кэш живёт дольше вердикта, поэтому вердикт надо доводить до кэша.

Что считаем чужим:
  * привязка отклонена сверкой (site_facts.privyazka = «улик нет» или «площадка: …»);
  * компания помечена verified='mismatch' И паспорт в карантине;
  * у компании вообще нет привязки, а файл в кэше есть — значит он остался от
    снятого адреса.

Файлы НЕ УДАЛЯЮТСЯ: переезжают в pagecache_otkloneno рядом. Вернуть — `--vernut ИНН`.

    python karantin_kesha.py --stat       посчитать, ничего не трогая
    python karantin_kesha.py --primenit   увести файлы в отстойник
    python karantin_kesha.py --vernut ИНН вернуть один файл обратно
"""
import gzip
import json
import os
import shutil
import sqlite3
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
ОТСТОЙНИК = os.environ.get('PAGECACHE_OTKLONENO',
                           os.path.join(os.path.dirname(KESH), 'pagecache_otkloneno'))
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ЛОГ = os.path.join(DIR, 'karantin_kesha.jsonl')


def _домен_кэша(путь):
    """С какого домена скачаны страницы в файле (по первой записи с адресом)."""
    try:
        d = json.loads(gzip.open(путь, 'rb').read().decode('utf-8', 'replace'))
    except Exception:  # noqa: BLE001
        return ''
    for pg in (d.get('pages') or []):
        u = pg.get('url') or ''
        if u:
            return PL.домен(u)
    return ''


def найти():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    привязки = {str(r['inn']): (r['site'] or r['cand'] or '', r['verified'] or '')
                for r in c.execute("select inn, coalesce(site,'') site, "
                                   "coalesce(cand_site,'') cand, coalesce(verified,'') verified "
                                   "from companies")}
    отклонённые = {str(r['inn']): (r['privyazka'] or '') for r in c.execute(
        "select inn, coalesce(privyazka,'') privyazka from site_facts "
        "where coalesce(otkloneno_json,'')<>''")}
    c.close()
    находки = []
    for имя in os.listdir(KESH):
        if not имя.endswith('.json.gz'):
            continue
        inn = имя.split('.')[0]
        сайт, вердикт = привязки.get(inn, (None, None))
        if сайт is None:
            continue                      # компании нет в базе — не наше дело
        if inn in отклонённые:
            причина = 'привязка отклонена: ' + (отклонённые[inn] or 'улик нет')
        elif not сайт:
            причина = 'привязка снята, адреса у компании больше нет'
        elif вердикт == 'mismatch':
            причина = 'verified=mismatch'
        else:
            # СТАРЫЙ ДОМЕН. 16.08 у 947 компаний адрес заменился: вместо снятой
            # площадки поставлен настоящий сайт из базы обзвона. Файл в кэше при
            # этом остался от площадки — по нему и собрался бы паспорт. Домен
            # страниц обязан совпадать с текущей привязкой.
            дк = _домен_кэша(os.path.join(KESH, имя))
            дп = PL.домен(сайт)
            if not дк or not дп or дк == дп or дк.endswith('.' + дп) or дп.endswith('.' + дк):
                continue
            причина = 'страницы с другого домена: в кэше %s, привязка %s' % (дк, дп)
        находки.append({'inn': inn, 'файл': имя, 'причина': причина})
    return находки


def применить():
    находки = найти()
    os.makedirs(ОТСТОЙНИК, exist_ok=True)
    увезено = 0
    with open(ЛОГ, 'a', encoding='utf-8') as f:
        for н in находки:
            src = os.path.join(KESH, н['файл'])
            dst = os.path.join(ОТСТОЙНИК, н['файл'])
            try:
                shutil.move(src, dst)
                увезено += 1
            except Exception as e:  # noqa: BLE001
                н['сбой'] = str(e)[:120]
            н['ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')
            f.write(json.dumps(н, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    return {'найдено': len(находки), 'увезено': увезено, 'отстойник': ОТСТОЙНИК}


def вернуть(inn):
    имя = '%s.json.gz' % str(inn).strip()
    src = os.path.join(ОТСТОЙНИК, имя)
    if not os.path.exists(src):
        return {'нет в отстойнике': имя}
    shutil.move(src, os.path.join(KESH, имя))
    return {'вернули': имя}


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--stat':
        находки = найти()
        по_причинам = {}
        for н in находки:
            к = н['причина'].split(':')[0]
            по_причинам[к] = по_причинам.get(к, 0) + 1
        print(json.dumps({'файлов_на_вывод': len(находки), 'по_причинам': по_причинам,
                          'примеры': находки[:8]}, ensure_ascii=False, indent=1))
    elif a[0] == '--primenit':
        print(json.dumps(применить(), ensure_ascii=False, indent=1))
    elif a[0] == '--vernut' and len(a) > 1:
        print(json.dumps(вернуть(a[1]), ensure_ascii=False))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
