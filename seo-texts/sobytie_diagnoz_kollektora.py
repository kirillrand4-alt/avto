# -*- coding: utf-8 -*-
"""Почему 49 сырых материалов дали НОЛЬ событий. Смотрю глазами, а не гадаю.

Проба из 10 запросов: raw_items 49, capex_events 0, with_inn 0, saved_to_db 0. Ноль тут
может значить три разные вещи, и чинятся они по-разному:
  1) запросы приносят не то — тогда виноваты мои формулировки;
  2) материал тот, но капекс-фильтр его не признаёт — вопрос к фильтру;
  3) материал тот и признан, но дедуп seen_news его уже съел раньше.

Прибор зовёт коллектор НАПРЯМУЮ теми же запросами и печатает заголовки, а потом гоняет
через тот же разбор события по одному, с печатью вердикта. Контроль: выдуманный запрос
обязан дать ноль материалов.
"""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import news_scan as NS  # noqa: E402

OTRASLI = ['химический завод', 'нефтехимический комбинат', 'нефтеперерабатывающий завод',
           'газоперерабатывающий завод', 'производство полимеров',
           'завод минеральных удобрений', 'производство аммиака', 'производство метанола',
           'металлургический комбинат', 'сталелитейный завод']
RANNIE = ['подписано соглашение о строительстве']
zapros = [f'{t} {o}' for t in RANNIE for o in OTRASLI]
KONTROL = ['подписано соглашение о строительстве комбинат щварцкопфер']

for imya, qq in (('МОИ ЗАПРОСЫ', zapros), ('КОНТРОЛЬ', KONTROL)):
    print('\n##### %s (%d запросов)' % (imya, len(qq)))
    try:
        raw = NS.col_xmlriver(qq, 45, 8, engines=('yandex',))
    except Exception as e:  # noqa: BLE001
        print('  коллектор упал: %s' % str(e)[:160])
        continue
    print('  сырых материалов: %d' % len(raw))
    for x in raw[:12]:
        if isinstance(x, dict):
            print('   - %-96s' % str(x.get('title') or x.get('name') or '')[:96])
            print('     %s' % str(x.get('url') or x.get('link') or '')[:110])
        else:
            print('   - %s' % str(x)[:110])
    if imya == 'КОНТРОЛЬ':
        continue

    print('\n  --- теперь тот же материал через разбор события, по одному ---')
    est = getattr(NS, 'extract_event', None)
    if est is None:
        print('  функции extract_event нет, имя проверить')
        continue
    import inspect
    print('  сигнатура extract_event%s' % inspect.signature(est))
    vzyato = 0
    for x in raw[:6]:
        if not isinstance(x, dict):
            continue
        try:
            r = est(x)
        except TypeError:
            try:
                r = est(x, None)
            except Exception as e:  # noqa: BLE001
                print('   разбор упал: %s' % str(e)[:120])
                break
        except Exception as e:  # noqa: BLE001
            print('   разбор упал: %s' % str(e)[:120])
            break
        vzyato += 1
        print('   * %-70s' % str(x.get('title') or '')[:70])
        print('     вердикт: %s' % json.dumps(r, ensure_ascii=False)[:340])
    print('  разобрано без падения: %d' % vzyato)

print('\n##### дедуп: сколько ключей уже виденных')
try:
    import sqlite3
    c = sqlite3.connect(r'C:\sender\enrich.db').cursor()
    print('  seen_news: %d' % c.execute('select count(*) from seen_news').fetchone()[0])
except Exception as e:  # noqa: BLE001
    print('  не прочиталось: %s' % str(e)[:90])
