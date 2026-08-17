# -*- coding: utf-8 -*-
r"""Полнота карточки по тому, что добыто С САЙТА компании.

Владелец 17.08: «замер полноты мне нужен по информации с сайтов». Правильное
уточнение: реестровые поля мы только что перелили из обзвона, и они меряют не нашу
работу, а полноту чужой выгрузки. С сайта же добывается ровно то, ради чего затеян
обход, — предмет разговора в письме.

Меряем ТОЛЬКО среди тех, у кого сайт реально обойден: если страниц нет, пустая
карточка говорит о недоборе очереди, а не о сайте.

Пятнадцать блоков, все — со страниц компании:
    привязка      доказана уликой со страниц (ИНН, ОГРН, имя, домен);
    продукция     что предприятие выпускает;
    оборудование  линии, станки, комплексы;
    мощности      только фразы с числом и единицей;
    сырьё         что заходит на вход;
    контроль      ХАССП, ISO, своя лаборатория;
    энергохозяйство   компрессорная, покраска, сушка, станочный парк;
    газы          азот, кислород, аргон, резка;
    расширение    новый цех, линия, участок;
    экспорт       страны и поставки за рубеж;
    география     куда отгружают;
    клиенты       названные юрлица-заказчики;
    масштаб       площадь, численность — с числом;
    год основания;
    новости       свежая запись для «почему пишу сейчас»;
    почта, телефон, человек — контакты, добытые с самого сайта.

    python polnota_sayta.py           распределение и узкие места
    python polnota_sayta.py --primery самые полные карточки, для глаз
"""
import json
import os
import sqlite3
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (DIR, os.path.dirname(DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import ploshchadki as PL          # noqa: E402
import sverka_privyazki as SP     # noqa: E402

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
# поле паспорта -> имя блока в отчёте
ИЗ_ПАСПОРТА = (('продукция', 'продукция'), ('оборудование_линии', 'оборудование'),
               ('мощности', 'мощности'), ('сырьё', 'сырьё'),
               ('контроль_качества', 'контроль качества'),
               ('энергохозяйство', 'энергохозяйство'), ('газы', 'газы'),
               ('расширение', 'расширение'), ('экспорт', 'экспорт'),
               ('география_поставок', 'география'), ('клиенты', 'клиенты'),
               ('масштаб', 'масштаб'), ('год_основания', 'год основания'))
БЛОКИ = (['привязка доказана'] + [и for _п, и in ИЗ_ПАСПОРТА]
         + ['новости', 'почта с сайта', 'телефон с сайта', 'человек с сайта'])


def строки():
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    из = list(c.execute(
        "select k.inn, coalesce(k.name,'') name, coalesce(k.ogrn,'') ogrn, "
        "coalesce(nullif(k.site,''),nullif(k.cand_site,''),'') site, "
        "coalesce(k.best_email,'') pochta, "
        "coalesce(f.facts_json,'') facts, coalesce(f.format,0) format, "
        "(select count(*) from people p where p.inn=k.inn and coalesce(p.person,'')<>'' "
        " and coalesce(p.post,'')<>'' and coalesce(p.source_url,'')<>'') lyudi_s_sayta, "
        "(select count(*) from phone_contacts t where t.inn=k.inn "
        " and coalesce(t.source_url,'')<>'') tel_s_sayta "
        "from companies k left join site_facts f on f.inn=k.inn"))
    c.close()
    return из


def блоки(r):
    из = set()
    if r['site']:
        улики, _ = SP.улики(str(r['inn']), r['name'], r['site'], r['ogrn'])
        if улики:
            из.add('привязка доказана')
    d = {}
    if r['facts'] and r['format'] >= 2:
        try:
            d = json.loads(r['facts'])
        except Exception:  # noqa: BLE001
            d = {}
    for поле, имя in ИЗ_ПАСПОРТА:
        if d.get(поле):
            из.add(имя)
    if d.get('свежая_новость') or d.get('новости'):
        из.add('новости')
    # почта считается «с сайта», когда её домен совпадает с доменом сайта:
    # адрес с mail.ru мог прийти из выгрузки и о сайте ничего не говорит
    if r['pochta'] and r['site']:
        if r['pochta'].split('@')[-1].lower() == PL.домен(r['site']):
            из.add('почта с сайта')
    if r['tel_s_sayta']:
        из.add('телефон с сайта')
    if r['lyudi_s_sayta']:
        из.add('человек с сайта')
    return из


def свод():
    все = [r for r in строки()
           if os.path.exists(os.path.join(KESH, '%s.json.gz' % r['inn']))]
    распр, пусто = {}, {б: 0 for б in БЛОКИ}
    полные = 0
    for r in все:
        б = блоки(r)
        распр[len(б)] = распр.get(len(б), 0) + 1
        for имя in БЛОКИ:
            if имя not in б:
                пусто[имя] += 1
        if len(б) == len(БЛОКИ):
            полные += 1
    заполнено = {б: len(все) - n for б, n in пусто.items()}
    return {'обойденных_компаний': len(все), 'блоков_всего': len(БЛОКИ),
            'закрыли_всё': полные,
            'сколько_блоков_у_скольких': dict(sorted(распр.items(), reverse=True)),
            'блок_заполнен_у_скольких': dict(sorted(заполнено.items(),
                                                    key=lambda x: -x[1]))}


def примеры(сколько=8):
    все = [r for r in строки()
           if os.path.exists(os.path.join(KESH, '%s.json.gz' % r['inn']))]
    оценки = []
    for r in все:
        б = блоки(r)
        оценки.append((len(б), str(r['inn']), r['name'][:40], r['site'], sorted(б)))
    оценки.sort(reverse=True)
    return [{'блоков': n, 'инн': i, 'имя': им, 'сайт': с, 'что_есть': б}
            for n, i, им, с, б in оценки[:сколько]]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if '--primery' in sys.argv:
        print(json.dumps(примеры(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(свод(), ensure_ascii=False, indent=1))
