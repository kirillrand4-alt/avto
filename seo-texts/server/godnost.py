# -*- coding: utf-8 -*-
r"""Что в итоге собралось: доказано ли, чисто ли, хватает ли для письма.

Владелец 17.08: «насколько это доказано, насколько чистые и пригодные данные
получаются? полностью ли их хватает из того что мы получили?».

Считаем не «сколько строк в базе», а сколько компаний ГОДНЫ — то есть письмо им
можно написать прямо сейчас, и каждое утверждение в нём опирается на улику. Пять
условий, все проверяемые:

  1. привязка сайта доказана — ИНН, ОГРН, имя компании или её домен найдены на
     самих страницах. Без этого паспорт может описывать чужой бизнес;
  2. паспорт собран текущим промптом (format=2) и не пуст;
  3. есть материал для захода — факт из продукции, энергохозяйства, газов,
     расширения или мощностей, ПОДТВЕРЖДЁННЫЙ дословным поиском по страницам;
  4. есть куда писать — почта, не скрытая на странице и не ловушка;
  5. компания не конкурент и её привязка не отклонена.

Всё, что не прошло, раскладываем по причинам — это и есть ответ «чего не хватает».

    python godnost.py            воронка и причины отсева
    python godnost.py --primery  по десять годных и негодных, для глаз
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import pasport_sverka as PS       # noqa: E402
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
ДЛЯ_ЗАХОДА = ('продукция', 'энергохозяйство', 'газы', 'расширение', 'мощности')
# Вердикт по каждой компании пишем НА ДИСК по ходу дела. Первый прогон копил всё
# в памяти и печатал в конце — раннер срезал его по таймауту, и двадцать минут
# работы пропадали целиком. Теперь прогон можно продолжить и подытожить отдельно.
ВЕРДИКТЫ = os.path.join(DIR, 'godnost.jsonl')


def строки():
    # nullif, а не просто coalesce: чистки 16-17.08 снимали привязку записью
    # ПУСТОЙ СТРОКИ, а coalesce пропускает только NULL — и пустая строка побеждала
    # живого кандидата. Так 335 компаний попали в отчёт как «привязка ничем не
    # доказана», хотя адрес у них был.
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = list(c.execute(
        "select k.inn, coalesce(k.name,'') name, coalesce(nullif(k.site,''),nullif(k.cand_site,''),'') site, "
        "coalesce(k.ogrn,'') ogrn, coalesce(k.best_email,'') pochta, "
        "coalesce(k.is_competitor,'') konkurent, coalesce(k.division,'') division, "
        "coalesce(k.okved,'') okved, "
        "coalesce(f.facts_json,'') facts, coalesce(f.format,0) format, "
        "coalesce(f.otkloneno_json,'') otkloneno "
        "from companies k left join site_facts f on f.inn=k.inn "
        "where coalesce(k.site,'')<>'' or coalesce(k.cand_site,'')<>''"))
    c.close()
    return из


def разобрать(r):
    """Вернуть (годен, причина_отсева, сколько_подтверждённых_фактов)."""
    if str(r['konkurent']) == '1':
        return False, 'конкурент — не пишем', 0
    if r['otkloneno']:
        return False, 'привязка отклонена, паспорт в карантине', 0
    if not r['facts']:
        return False, 'паспорта нет (сайт ещё не обойден или не разобран)', 0
    if r['format'] < 2:
        return False, 'паспорт старого формата, ждёт переразбора', 0
    улики, _ = SP.улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
    if not улики:
        return False, 'привязка сайта ничем не доказана', 0
    try:
        d = json.loads(r['facts'])
    except Exception:  # noqa: BLE001
        return False, 'паспорт не читается', 0
    t = PS._tekst(str(r['inn']))
    подтв = 0
    for k in ДЛЯ_ЗАХОДА:
        v = d.get(k)
        сп = v if isinstance(v, list) else ([v] if v else [])
        for ф in [str(x) for x in сп if x][:6]:
            if t and PS._podtverzhdena(ф.lower().replace('ё', 'е'), t):
                подтв += 1
    if not подтв:
        return False, 'нет ни одного подтверждённого факта для захода', 0
    if not r['pochta']:
        return False, 'некуда писать: почты нет', подтв
    return True, '', подтв


def прогон(продолжить=True):
    """Пройти компании и записать вердикт по каждой в файл, по ходу дела."""
    готовые = set()
    if продолжить and os.path.exists(ВЕРДИКТЫ):
        with open(ВЕРДИКТЫ, encoding='utf-8') as f:
            for s in f:
                try:
                    готовые.add(json.loads(s)['inn'])
                except Exception:  # noqa: BLE001
                    pass
    все = [r for r in строки() if str(r['inn']) not in готовые]
    сделано = 0
    with open(ВЕРДИКТЫ, 'a', encoding='utf-8') as f:
        for r in все:
            годен, причина, подтв = разобрать(r)
            f.write(json.dumps({'inn': str(r['inn']), 'годен': годен,
                                'причина': причина, 'подтв': подтв,
                                'division': r['division']}, ensure_ascii=False) + '\n')
            сделано += 1
            if сделано % 200 == 0:
                f.flush()
                os.fsync(f.fileno())
        f.flush()
        os.fsync(f.fileno())
    return {'посчитано_сейчас': сделано, 'было_ранее': len(готовые)}


def воронка():
    """Свести вердикты из файла в воронку."""
    итог = {'компаний_с_сайтом': 0, 'годны_для_письма': 0}
    причины, фактов = {}, []
    if not os.path.exists(ВЕРДИКТЫ):
        return итог
    with open(ВЕРДИКТЫ, encoding='utf-8') as f:
        for s in f:
            try:
                d = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            итог['компаний_с_сайтом'] += 1
            if d['годен']:
                итог['годны_для_письма'] += 1
                фактов.append(d['подтв'])
            else:
                причины[d['причина']] = причины.get(d['причина'], 0) + 1
    итог['почему_остальные_не_годны'] = dict(sorted(причины.items(), key=lambda x: -x[1]))
    if фактов:
        фактов.sort()
        итог['подтверждённых_фактов_на_годную'] = {
            'в среднем': round(sum(фактов) / len(фактов), 1),
            'медиана': фактов[len(фактов) // 2],
            'минимум': фактов[0], 'максимум': фактов[-1]}
    return итог


def примеры(сколько=10):
    все = строки()
    годные, плохие = [], []
    for r in все:
        годен, причина, подтв = разобрать(r)
        if годен and len(годные) < сколько:
            d = json.loads(r['facts'])
            годные.append({'инн': str(r['inn']), 'имя': r['name'][:40], 'сайт': r['site'],
                           'почта': r['pochta'], 'подтв_фактов': подтв,
                           'продукция': '; '.join((d.get('продукция') or [])[:3])[:80]})
        elif not годен and len(плохие) < сколько:
            плохие.append({'инн': str(r['inn']), 'имя': r['name'][:40],
                           'сайт': r['site'], 'причина': причина})
        if len(годные) >= сколько and len(плохие) >= сколько:
            break
    return {'годные': годные, 'негодные': плохие}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if '--primery' in sys.argv:
        print(json.dumps(примеры(), ensure_ascii=False, indent=1))
    elif '--progon' in sys.argv:
        print(json.dumps(прогон(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(воронка(), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
