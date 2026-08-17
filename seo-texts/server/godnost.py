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


def строки():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = list(c.execute(
        "select k.inn, coalesce(k.name,'') name, coalesce(k.site,k.cand_site,'') site, "
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


def воронка():
    все = строки()
    итог = {'компаний_с_сайтом': len(все), 'годны_для_письма': 0}
    причины, фактов = {}, []
    for r in все:
        годен, причина, подтв = разобрать(r)
        if годен:
            итог['годны_для_письма'] += 1
            фактов.append(подтв)
        else:
            причины[причина] = причины.get(причина, 0) + 1
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
    else:
        print(json.dumps(воронка(), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
