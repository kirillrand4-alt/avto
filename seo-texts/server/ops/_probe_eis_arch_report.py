# -*- coding: utf-8 -*-
r"""ОТЧЁТ ПО АРХИВНОМУ ПРОХОДУ — цифрами ИЗ БАЗЫ, а не из счётчиков прогона.

Правило 4.6 передачи: между счётчиком прогона и базой стоят чистка и
дедупликация, и три отчётных числа за день оказались завышены в 1,7-2,5 раза
именно потому, что брались из потока разбора. Здесь всё считается запросами к
enrich.db, а сравнение «архив против актуальных» — по durable-потоку.

Порядок печати: подробности сперва, СВОДКА В КОНЦЕ — раннер отдаёт stdout
хвостом, и то, что напечатано первым, до нас не доедет.
"""
import io
import json
import os
import re
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402
import enrich_db as EDB       # noqa: E402

ПОТОК = r'C:\seostat\drop\eis_archive_stream.jsonl'
ИСТ = 'zakupki:eis-archive'


def цифры(s):
    return re.sub(r'\D', '', s or '')


def main():
    db = EDB.EnrichDB()
    e = db.cx
    от = {}

    # ---------------------------------------------------------- 1) БАЗА
    од = lambda q, p=(): e.execute(q, p).fetchone()[0]  # noqa: E731
    от['eis_arch_записей'] = од('SELECT COUNT(*) FROM eis_arch')
    от['eis_arch_компаний'] = од('SELECT COUNT(DISTINCT inn) FROM eis_arch')
    от['eis_arch_с_ФИО'] = од("SELECT COUNT(*) FROM eis_arch WHERE person<>''")
    от['eis_arch_с_телефоном'] = од("SELECT COUNT(*) FROM eis_arch WHERE phone<>''")
    от['eis_arch_с_почтой'] = од("SELECT COUNT(*) FROM eis_arch WHERE email<>''")
    от['свежесть'] = {r[0]: r[1] for r in e.execute(
        'SELECT freshness, COUNT(*) FROM eis_arch GROUP BY freshness')}
    от['горячих'] = од('SELECT COUNT(*) FROM eis_arch WHERE hot=1')
    от['только_из_архива'] = од('SELECT COUNT(*) FROM eis_arch WHERE from_archive=1')
    от['роли'] = {r[0]: r[1] for r in e.execute(
        'SELECT role, COUNT(*) FROM eis_arch GROUP BY role ORDER BY 2 DESC')}
    от['техролей'] = од(
        'SELECT COUNT(*) FROM eis_arch WHERE role IN (%s)'
        % ','.join('?' * len(EDB.EnrichDB.TECH_ROLES)),
        EDB.EnrichDB.TECH_ROLES)
    от['схлопнуто_закупок_в_людей'] = од(
        'SELECT COALESCE(SUM(n_procs),0) FROM eis_arch')
    от['людей_с_2+_закупками'] = од('SELECT COUNT(*) FROM eis_arch WHERE n_procs>=2')
    от['есть_запасная_ссылка'] = од("SELECT COUNT(*) FROM eis_arch WHERE alt_url<>''")
    # что реально легло в общие таблицы этим источником
    от['people_источник_архив'] = од(
        'SELECT COUNT(*) FROM people WHERE source=?', (ИСТ,))
    от['people_компаний'] = од(
        'SELECT COUNT(DISTINCT inn) FROM people WHERE source=?', (ИСТ,))
    от['phone_contacts_архив'] = од(
        'SELECT COUNT(*) FROM phone_contacts WHERE source LIKE ?', (ИСТ + '%',))
    от['emails_архив'] = од('SELECT COUNT(*) FROM emails WHERE source=?', (ИСТ,))
    от['signals_архив'] = од('SELECT COUNT(*) FROM signals WHERE source=?', (ИСТ,))
    от['stage_бой'] = од("SELECT COUNT(*) FROM stage_log WHERE stage='eis_archive'")
    от['stage_сухой'] = од(
        "SELECT COUNT(*) FROM stage_log WHERE stage='eis_archive_dry'")
    # сколько из них НЕ БЫЛО в базе до архивного прохода: телефон, которого нет
    # ни в одной строке другого источника
    от['телефонов_каких_не_было'] = од(
        "SELECT COUNT(*) FROM phone_contacts p WHERE p.source LIKE ? AND NOT EXISTS("
        "SELECT 1 FROM phone_contacts q WHERE q.inn=p.inn AND q.phone=p.phone "
        "AND q.source NOT LIKE ?)", (ИСТ + '%', ИСТ + '%'))
    от['почт_каких_не_было'] = од(
        "SELECT COUNT(*) FROM emails WHERE source=? AND updated_at>=?",
        (ИСТ, time.strftime('%Y-%m-%d')))

    # ------------------------------------------------- 2) ПОТОК (сравнение)
    строки = {}
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                d = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if d.get('inn'):
                строки[d['inn']] = d
    с = {'компаний': len(строки), 'с_позициями_в_еис': 0, 'с_людьми': 0,
         'людей_всего': 0, 'людей_из_актуальных': 0, 'людей_добавил_архив': 0,
         'людей_прежний_подход': 0, 'карточек_архивных_найдено': 0,
         'карточек_открыто': 0, 'отклонено_привязкой': 0,
         'отброшено_старше_3_лет': 0, 'прежний_подход_старше_3_лет': 0}
    for d in строки.values():
        if (d.get('актуальных_позиций') or 0) or (d.get('архивных_позиций') or 0):
            с['с_позициями_в_еис'] += 1
        if (d.get('людей') or 0):
            с['с_людьми'] += 1
        for k_из, k_в in (('людей', 'людей_всего'),
                          ('людей_из_актуальных', 'людей_из_актуальных'),
                          ('людей_добавил_архив', 'людей_добавил_архив'),
                          ('людей_прежний_подход', 'людей_прежний_подход'),
                          ('карточек_архивных', 'карточек_архивных_найдено'),
                          ('открыто_карточек', 'карточек_открыто'),
                          ('карточек_отклонено_привязкой', 'отклонено_привязкой'),
                          ('отброшено_старше_3_лет', 'отброшено_старше_3_лет'),
                          ('прежний_подход_старше_3_лет',
                           'прежний_подход_старше_3_лет')):
            с[k_в] += int(d.get(k_из) or 0)
    от['сравнение'] = с

    # ------------------------------------------- 3) ЖИВЫЕ ПРИМЕРЫ со ссылкой
    прим = [dict(zip(('инн', 'кто', 'долж', 'тел', 'почта', 'дата', 'свежесть',
                      'закупок', 'горяч', 'url'), r)) for r in e.execute(
        "SELECT inn,person,post,phone,email,proc_date,freshness,n_procs,hot,"
        "source_url FROM eis_arch WHERE person<>'' AND (phone<>'' OR email<>'') "
        "ORDER BY n_procs DESC, proc_date DESC LIMIT 8")]
    print('ПРИМЕРЫ ' + json.dumps(прим, ensure_ascii=False, indent=1)[:2600],
          flush=True)

    # ------------------------------------------- 4) ПЕРЕПРОВЕРКА ГЛАЗАМИ
    выбор = []
    for усл in ("freshness='stale'", 'n_procs>=3', 'hot=1', "freshness='fresh'"):
        for r in e.execute(
                'SELECT inn,person,phone,email,proc_date,freshness,n_procs,'
                'source_url FROM eis_arch WHERE ' + усл
                + " AND source_url<>'' ORDER BY proc_date DESC LIMIT 2"):
            if not any(x['url'] == r[7] for x in выбор):
                выбор.append({'inn': r[0], 'person': r[1], 'phone': r[2],
                              'email': r[3], 'дата': r[4], 'свежесть': r[5],
                              'закупок': r[6], 'url': r[7]})
    выбор = выбор[:8]
    пров = {'проверено': 0, 'совпало': 0, 'РАСХОЖДЕНИЙ': 0, 'ошибок': 0, 'что': []}
    for з in выбор:
        try:
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', EC._eis_get(з['url'])))
        except Exception:  # noqa: BLE001
            пров['ошибок'] += 1
            continue
        тц = цифры(t)
        фам = (з['person'] or '').split()[0] if з['person'] else ''
        баз = цифры((з['phone'] or '').split(' доб.')[0])[-10:]
        o = {'инн': з['inn'], 'кто': з['person'], 'дата': з['дата'],
             'св': з['свежесть'], 'закупок': з['закупок'],
             'ИНН_на_странице': з['inn'] in t,
             'фамилия_на_странице': bool(фам) and фам in t,
             'телефон_на_странице': bool(баз) and баз in тц,
             'почта_на_странице': bool(з['email']) and з['email'].lower() in t.lower(),
             'url': з['url']}
        ок = (o['ИНН_на_странице'] and (o['фамилия_на_странице'] or not фам)
              and (o['телефон_на_странице'] or not баз)
              and (o['почта_на_странице'] or not з['email']))
        o['ВЕРДИКТ'] = 'совпало' if ок else 'РАСХОЖДЕНИЕ'
        пров['проверено'] += 1
        пров['совпало' if ок else 'РАСХОЖДЕНИЙ'] += 1
        пров['что'].append(o)
        time.sleep(0.7)
    print('ПЕРЕПРОВЕРКА ' + json.dumps(пров, ensure_ascii=False, indent=1)[:3000],
          flush=True)

    # --------------------------- 5) АУДИТ ПРЕЖНЕГО ИСТОЧНИКА (без рубежа)
    ауд = {'проверено': 0, 'свой': 0, 'ЧУЖАЯ_КАРТОЧКА': 0, 'ошибок': 0, 'кто': []}
    for inn, тел, чел, url in e.execute(
            "SELECT inn, phone, person, source_url FROM phone_contacts "
            "WHERE source='zakupki:eis' AND source_url<>'' "
            "ORDER BY RANDOM() LIMIT 12"):
        try:
            t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', EC._eis_get(url)))
        except Exception:  # noqa: BLE001
            ауд['ошибок'] += 1
            continue
        ауд['проверено'] += 1
        if inn in t:
            ауд['свой'] += 1
        else:
            ауд['ЧУЖАЯ_КАРТОЧКА'] += 1
            зм = re.search(r'Заказчик\s*[:\-]?\s*([^,;]{6,70})', t)
            ауд['кто'].append({'инн': inn, 'кто': чел, 'тел': тел,
                               'чья_карточка': (зм.group(1).strip() if зм else '?')[:55],
                               'url': url[-46:]})
        time.sleep(0.6)
    print('АУДИТ_ПРЕЖНЕГО ' + json.dumps(ауд, ensure_ascii=False, indent=1)[:2000],
          flush=True)

    # ------------------------------------------------------- СВОДКА В КОНЦЕ
    сводка = {k: от[k] for k in (
        'eis_arch_записей', 'eis_arch_компаний', 'eis_arch_с_ФИО',
        'eis_arch_с_телефоном', 'eis_arch_с_почтой', 'свежесть', 'горячих',
        'только_из_архива', 'техролей', 'роли', 'схлопнуто_закупок_в_людей',
        'людей_с_2+_закупками', 'есть_запасная_ссылка',
        'people_источник_архив', 'people_компаний', 'phone_contacts_архив',
        'emails_архив', 'signals_архив', 'телефонов_каких_не_было',
        'stage_бой', 'stage_сухой', 'сравнение')}
    сводка['перепроверка'] = {k: пров[k] for k in
                              ('проверено', 'совпало', 'РАСХОЖДЕНИЙ', 'ошибок')}
    сводка['аудит_прежнего'] = {k: ауд[k] for k in
                                ('проверено', 'свой', 'ЧУЖАЯ_КАРТОЧКА', 'ошибок')}
    print('СВОДКА ' + json.dumps(сводка, ensure_ascii=False, indent=1)[:3600],
          flush=True)


if __name__ == '__main__':
    main()
