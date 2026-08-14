# -*- coding: utf-8 -*-
r"""Выгрузка контактной базы ИЗ enrich.db — то, что реально собрано сегодня.

Зачем отдельный файл. Старая выгрузка (`export_core` в enrich_contacts) читает
jsonl-потоки прогонов: самый свежий из них от 29 июля, а файл на дропе — от 24
июля. Конвейер туда давно не пишет, он пишет в enrich.db, и колонка людей,
добавленная 14.08, в той выгрузке физически не могла появиться. Владелец:
«9 — чини». Чиним не заплаткой к мёртвому пути, а сборкой из базы.

Колонки — под письма и под звонок:
  all_contacts   адрес|роль|источник|smtp|страница|для кого (заход)
  lyudi          ФИО|должность|роль|откуда|когда видели|ссылка  (люди БЕЗ почты)
  produkciya     что предприятие выпускает СЛОВАМИ САЙТА (site_facts)
  novost         свежая новость с датой — повод письма

Запуск на сервере:
    python vygruzka_bazy.py [имя-на-дропе.csv] [минимум-контактов]
"""
import csv
import io
import json
import os
import sqlite3
import sys
import urllib.request

BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOKEN = os.environ.get('DROP_TOKEN', '')
# порядок ценности роли для выбора лучшего адреса: технарь выше снабженца,
# снабженец выше приёмной — письмо идёт тому, кто решает
VES_ROLI = {'гл.инженер': 100, 'гл.энергетик': 95, 'гл.механик': 92, 'техдиректор': 90,
            'нач.производства': 85, 'нач.цеха': 80, 'инженер (не главный)': 70,
            'техконтакт': 65, 'снабжение/закупки': 60, 'закупки': 58, 'директор': 50,
            'продажи': 30, 'приёмная': 20, 'бухгалтерия': 10, 'кадры': 5, 'общий': 1}


def _fakty(s):
    """Продукция и свежая новость из карточки site_facts."""
    if not s:
        return '', ''
    try:
        d = json.loads(s)
    except Exception:  # noqa: BLE001
        return '', ''
    prod = d.get('продукция')
    if isinstance(prod, list):
        prod = ', '.join(str(x) for x in prod[:6])
    return str(prod or '')[:300], str(d.get('свежая_новость') or '')[:200]


def sobrat(minimum=1):
    c = sqlite3.connect('file:%s?mode=ro' % BD.replace('\\', '/'), uri=True)
    c.row_factory = sqlite3.Row
    pochty, lyudi, telefony, fakty, signaly = {}, {}, {}, {}, {}
    for r in c.execute("select inn, email, coalesce(role,'') role, coalesce(person,'') person, "
                       "coalesce(source,'') src, coalesce(source_url,'') url, "
                       "coalesce(probe_verdict,'') smtp, coalesce(zahod_rol,'') zr, "
                       "coalesce(zahod_fio,'') zf, mx_ok from emails"):
        pochty.setdefault(str(r['inn']), []).append(dict(r))
    for r in c.execute("select inn, person, coalesce(post,'') post, coalesce(role,'') role, "
                       "coalesce(source,'') src, coalesce(observed_at,'') obs, "
                       "coalesce(source_url,'') url from people where coalesce(person,'')<>''"):
        lyudi.setdefault(str(r['inn']), []).append(dict(r))
    for r in c.execute("select inn, phone, coalesce(role,'') role, coalesce(person,'') person "
                       'from phone_contacts'):
        telefony.setdefault(str(r['inn']), []).append(dict(r))
    for r in c.execute("select inn, coalesce(facts_json,'') f from site_facts"):
        fakty[str(r['inn'])] = r['f']
    for r in c.execute("select inn, coalesce(event_type,'') e, coalesce(what,'') w, "
                       "coalesce(source_url,'') u from signals order by coalesce(hotness,0) desc"):
        signaly.setdefault(str(r['inn']), []).append(dict(r))

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['inn', 'name', 'region', 'okved', 'revenue_rub', 'site', 'director',
                'best_email', 'best_role', 'kontaktov',
                'all_contacts(email|роль|источник|smtp|страница|для кого)',
                'lyudi(ФИО|должность|роль|откуда|когда видели|ссылка)',
                'telefony(номер|роль|ФИО)', 'produkciya', 'novost',
                'signal(тип|что|ссылка)'])
    строк = 0
    for k in c.execute("select inn, coalesce(name,'') name, coalesce(short_name,'') sn, "
                       "coalesce(region,'') reg, coalesce(okved,'') okved, "
                       "coalesce(revenue_rub,0) rev, coalesce(site,'') site, "
                       "coalesce(cand_site,'') cand, coalesce(director,'') dir "
                       'from companies'):
        inn = str(k['inn'])
        em = pochty.get(inn) or []
        lю = lyudi.get(inn) or []
        tel = telefony.get(inn) or []
        if len(em) + len(lю) + len(tel) < minimum:
            continue
        em.sort(key=lambda e: -(VES_ROLI.get(e['role'], 0) + (5 if e['smtp'] == 'жив' else 0)))
        best = em[0] if em else {}
        w.writerow([
            inn, k['name'] or k['sn'], k['reg'], k['okved'], int(k['rev'] or 0),
            k['site'] or k['cand'], k['dir'],
            best.get('email', ''), best.get('role', ''), len(em),
            ' ; '.join('%s|%s|%s|%s|%s|%s' % (
                e['email'], e['role'], e['src'], e['smtp'], e['url'],
                (('%s %s' % (e['zr'], e['zf'])).strip() if (e['zr'] or e['zf']) else ''))
                for e in em[:12]),
            ' ; '.join('%s|%s|%s|%s|%s|%s' % (p['person'], p['post'][:60], p['role'],
                                              p['src'], p['obs'], p['url'])
                       for p in lю[:8]),
            ' ; '.join('%s|%s|%s' % (t['phone'], t['role'], t['person']) for t in tel[:6]),
            _fakty(fakty.get(inn))[0], _fakty(fakty.get(inn))[1],
            ' ; '.join('%s|%s|%s' % (s['e'], s['w'][:120], s['u'])
                       for s in (signaly.get(inn) or [])[:3]),
        ])
        строк += 1
    c.close()
    return buf.getvalue().encode('utf-8'), строк


def main():
    imya = sys.argv[1] if len(sys.argv) > 1 else 'BAZA-KONTAKTY-IZ-BD.csv'
    minimum = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    blob, строк = sobrat(minimum)
    otvet = {'файл': imya, 'строк': строк, 'байт': len(blob)}
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        op.open(urllib.request.Request(DROP + '/' + imya, data=blob, method='PUT',
                                       headers={'X-Drop-Token': TOKEN}), timeout=180)
        otvet['на_дропе'] = True
    except Exception as e:  # noqa: BLE001
        otvet['на_дропе'] = 'ошибка: %s' % str(e)[:100]
    print(json.dumps(otvet, ensure_ascii=False))


if __name__ == '__main__':
    main()
