# -*- coding: utf-8 -*-
r"""Кого ещё можно догрузить в панель по условиям партии 935.

Условия партии (17.08): чистая почта С САЙТА (own-site/zenno/сайт:%, без
ловушек, скрытых и холдинговых) И паспорт текущего формата с непустой
продукцией. Плюс к тому теперь действуют результаты чистки: карточки с
карантинным паспортом отсеиваются сами (facts_json пуст), а «чужие» по
приговору исключаем явно.

Считаем воронку: сколько проходит условия -> сколько уже в группе -> сколько
реально ляжет (адрес не занят получателем с ДРУГИМ ИНН). И заодно смотрим
соседние пласты: чем именно не проходят те, кто рядом.
"""
import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')
ENRICH = r'C:\sender\enrich.db'
SENDER = r'C:\sender\sender.db'
САЙТ = "(e.source in ('own-site','zenno') or e.source like 'сайт:%')"
ЧИСТ = ("coalesce(e.pometka,'') not like '%спам-ловушк%' "
        "and coalesce(e.pometka,'') not like '%скрыт%' "
        "and coalesce(e.pometka,'') not like '%не использовать%'")
ПАСПОРТ = ("coalesce(f.format,0)>=2 and f.facts_json like '%\"продукция\": [\"%'")

c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
c.row_factory = sqlite3.Row
с_почтой = {str(r[0]) for r in c.execute(
    'select distinct e.inn from emails e where %s and %s' % (САЙТ, ЧИСТ))}
с_паспортом = {str(r[0]) for r in c.execute(
    'select f.inn from site_facts f where %s' % ПАСПОРТ)}
карантин = {str(r[0]) for r in c.execute(
    "select inn from site_facts where coalesce(otkloneno_json,'')<>'' "
    "and coalesce(facts_json,'')=''")}
чужие = set()
try:
    чужие = {str(r[0]) for r in c.execute(
        "select inn from prigovor_domenov where verdikt='чужой'")}
except Exception:  # noqa: BLE001
    pass
наши = {str(r[0]) for r in c.execute(
    "select inn from companies where coalesce(nash_priznak,'') "
    "not in ('', 'нет', 'неизвестно')")}
лучший = {str(r[0]): (r[1] or '').lower() for r in c.execute(
    "select inn, coalesce(best_email,'') from companies")}
c.close()

годные = (с_почтой & с_паспортом) - чужие
s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
s.row_factory = sqlite3.Row
в_группе, чей_адрес = set(), {}
for r in s.execute("select coalesce(inn,'') inn, lower(coalesce(email,'')) em, "
                   "coalesce(extra_json,'') ex from recipients"):
    инн = ''.join(ch for ch in r['inn'] if ch.isdigit())
    if r['em']:
        чей_адрес[r['em']] = инн
    if 'Партия 935' in r['ex']:
        в_группе.add(инн)
s.close()

новые = годные - в_группе
занят_чужим = {i for i in новые
               if лучший.get(i) and чей_адрес.get(лучший[i], i) != i}
итог = {
    'проходят_условия_935': len(годные),
    'из_них_уже_в_группе': len(годные & в_группе),
    'НОВЫХ_можно_догрузить': len(новые),
    'из_новых_адрес_занят_другим_ИНН': len(занят_чужим),
    'ляжет_чисто': len(новые - занят_чужим),
    'из_новых_с_признаком_наш': len(новые & наши),
    'соседние_пласты': {
        'почта_с_сайта_есть_паспорта_нет': len(с_почтой - с_паспортом - чужие),
        'паспорт_есть_почты_с_сайта_нет': len(с_паспортом - с_почтой - чужие),
        'паспорт_в_карантине_после_чистки': len(карантин),
        'отсеяно_приговором_чужой': len(чужие & (с_почтой | с_паспортом))},
}
print(json.dumps(итог, ensure_ascii=False, indent=1))
