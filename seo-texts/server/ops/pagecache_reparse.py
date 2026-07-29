# -*- coding: utf-8 -*-
"""Перечитать УЖЕ СКАЧАННЫЕ страницы новой регуляркой телефонов.

Зачем именно сейчас. Регулярка номера требовала код ровно из трёх цифр, и
номера с четырёх- и пятизначным кодом («8 (3812) 39-45-67», «+7 (34764) 6 42
27») не находились ВООБЩЕ. Замер на 201 странице кэша: старая форма видела
1385 номеров, новая — 1767, то есть 720 номеров лежали на уже скачанных
страницах и в базу не попали. Среди них — целые справочники заводов, где
рядом с номером стоят ФИО и должность («Начальник отдела сбыта», «отдел
материально-технического снабжения»), а это ровно те технические ЛПР, ради
которых всё и затевалось.

Повторный обход стоил бы прокси, капч и часов — здесь всё уже лежит на диске
(владелец 29.07: «складывай на дроп, чтобы анализировать без повторного
краулинга»). Разбор структурный (people_from_html), поэтому привязка «человек
— должность — телефон» берётся из ОДНОГО блока разметки, а не из плоского
текста.

Ничего не удаляем: только добавляем найденное. Резюмируемо по файлу кэша.
По умолчанию СУХОЙ ПРОГОН, запись — с --apply.

Запуск: python pagecache_reparse.py [--apply] [--limit N]
"""
import gzip
import io
import json
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

ПРИМЕНИТЬ = '--apply' in sys.argv
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
КЭШ = r'C:\seostat\drop\pagecache'
ЖУРНАЛ = r'C:\seostat\drop\pagecache_reparse.jsonl'

db = EDB.EnrichDB()
e = db.cx


def _норм(с):
    ц = re.sub(r'\D', '', с or '')
    if len(ц) == 11 and ц[0] in '78':
        ц = ц[1:]
    return ц[:10] if len(ц) >= 10 else ''


def инн_по_ключу(ключ, страницы):
    """Кэш назван по домену/ключу — ИНН достаём из companies по сайту."""
    д = (ключ or '').split('__')[0].replace('_', '.')
    r = e.execute("SELECT inn FROM companies WHERE site LIKE ? OR site LIKE ?",
                  (f'%{д}%', f'%{д.lstrip("www.")}%')).fetchone()
    if r:
        return r[0]
    for u in страницы[:3]:
        d = EC._domain(u)
        if not d:
            continue
        r = e.execute("SELECT inn FROM companies WHERE site LIKE ?",
                      (f'%{d}%',)).fetchone()
        if r:
            return r[0]
    return ''


def main():
    out = {'файлов': 0, 'без_инн': 0, 'страниц': 0, 'людей_найдено': 0,
           'людей_ново': 0, 'телефонов_ново': 0, 'телефонов_с_ролью': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'примеры': []}
    if not os.path.isdir(КЭШ):
        out['ошибка'] = 'кэша нет: ' + КЭШ
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    ж = io.open(ЖУРНАЛ, 'a', encoding='utf-8') if ПРИМЕНИТЬ else None
    for имя in sorted(os.listdir(КЭШ))[:ЛИМИТ]:
        п = os.path.join(КЭШ, имя)
        try:
            if имя.endswith('.gz'):
                with gzip.open(п, 'rt', encoding='utf-8', errors='replace') as f:
                    j = json.load(f)
            else:
                j = json.load(io.open(п, encoding='utf-8', errors='replace'))
        except Exception:  # noqa: BLE001
            continue
        out['файлов'] += 1
        стр = j.get('pages') or []
        адреса = [(x.get('url') or '') for x in стр if isinstance(x, dict)]
        inn = str(j.get('inn') or '') or инн_по_ключу(
            имя.split('.')[0], адреса)
        if not inn:
            out['без_инн'] += 1
            continue
        # что по этой компании уже есть — чтобы считать ТОЛЬКО прирост
        было_тел = {_норм(r[0]) for r in e.execute(
            'SELECT phone FROM phone_contacts WHERE inn=?', (inn,))}
        было_люд = {(r[0] or '').strip().lower() for r in e.execute(
            'SELECT person FROM people WHERE inn=?', (inn,))}
        for p in стр:
            if not isinstance(p, dict):
                continue
            h, u = p.get('html') or '', p.get('url') or ''
            if not h:
                continue
            out['страниц'] += 1
            for ч in EC.people_from_html(h, u):
                out['людей_найдено'] += 1
                фио = (ч.get('person') or '').strip()
                тел = (ч.get('phone') or '').strip()
                роль = EDB.EnrichDB._canon_role(ч.get('post') or '')
                ново_ч = фио and фио.lower() not in было_люд
                ново_т = тел and _норм(тел) and _норм(тел) not in было_тел
                if ново_ч:
                    out['людей_ново'] += 1
                    было_люд.add(фио.lower())
                if ново_т:
                    out['телефонов_ново'] += 1
                    было_тел.add(_норм(тел))
                    if роль:
                        out['телефонов_с_ролью'] += 1
                if (ново_ч or ново_т) and len(out['примеры']) < 14:
                    out['примеры'].append(
                        {'инн': inn, 'фио': фио, 'должность': ч.get('post'),
                         'роль': роль, 'тел': тел, 'почта': ч.get('email'),
                         'страница': u[:60]})
                if ПРИМЕНИТЬ and (ново_ч or ново_т):
                    if фио:
                        db.add_person(inn, фио, post=ч.get('post') or '',
                                      phone=тел, email=ч.get('email') or '',
                                      source='кэш:перечитан', source_url=u)
                    if ново_т:
                        e.execute(
                            'INSERT OR IGNORE INTO phone_contacts'
                            '(inn, phone, person, role, source, source_url,'
                            ' updated_at) VALUES(?,?,?,?,?,?,datetime("now"))',
                            (inn, тел, фио, роль or '', 'сайт компании', u))
                    ж.write(json.dumps(
                        {'inn': inn, 'person': фио, 'post': ч.get('post'),
                         'phone': тел, 'email': ч.get('email'), 'url': u},
                        ensure_ascii=False) + '\n')
        if ПРИМЕНИТЬ:
            e.commit()
            ж.flush()
            os.fsync(ж.fileno())
    if ж:
        ж.close()
        out['журнал'] = ЖУРНАЛ
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    # счётчики ПОВТОРНО в самый конец: раннер отдаёт stdout ХВОСТОМ, и при
    # длинном списке примеров шапка с цифрами не доезжает
    print(json.dumps({k: v for k, v in out.items() if k != 'примеры'},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
