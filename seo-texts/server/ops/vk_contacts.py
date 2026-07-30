# -*- coding: utf-8 -*-
"""Контакты из групп ВКонтакте по нашим базам — боевой проход, а не проба.

Зачем отдельный op. VK-путь живёт внутри `enrich_one`, а `enrich_one` для наших
двух баз НЕ ВЫЗЫВАЕТСЯ вовсе: и `sales_sites`, и `core_sites` ходят по сайтам
своим кодом. Единственный, кто зовёт `enrich_one`, — новостной скан, и он
приходит только к тем компаниям, про которые нашлась новость. То есть по базе
продажников и ядру центробежных группы ВК не спрашивались ни разу, а замер на
45 компаниях показал, что там лежит ровно то, чего базе не хватает: НАЗВАННЫЙ
человек с должностью и прямым телефоном.

Что даёт источник (замер 29.07, 45 компаний): слаг находится у 23, группа
открывается у 19, непустой блок «Контакты» у 7 — 11 контактов, 7 с должностью,
6 телефонов, 4 почты. Охват скромный, но цена — один HTTP-вызов.

Три починки, без которых замер был занижен, уже в `enrich_contacts`:
  * `_VK_SLUG_DENY` не знал `js` и `rtrg`, и виджет `//vk.com/js/api/openapi.js`
    выигрывал у настоящей ссылки в подвале (поиск берёт первое совпадение);
  * VK-путь стоял под условием «почта ещё не найдена» — фолбэк вместо прохода;
  * `user_id` из блока контактов извлекался и выбрасывался, человек уезжал
    без имени. Теперь один `users.get` на группу возвращает ФИО.

Запись идёт через `EC.persist_contacts`, то есть через `add_email`/`add_phone`/
`add_person`, а не своим SQL. Это принципиально: рубеж против реквизитов и
защита роли от понижения живут в этих методах, и писатель со своим INSERT их
не увидит — ровно так реквизит-телефон однажды и пережил починку.

Резюмируемо: поток `vk_contacts_stream.jsonl` с fsync, повторный запуск
продолжает с места остановки и переживает рестарт. По умолчанию СУХОЙ ПРОГОН.
Запуск: python vk_contacts.py [бюджет_сек] [--apply] [--limit N] [--inn ИНН]
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB          # noqa: E402
import enrich_contacts as EC     # noqa: E402

_поз = [a for a in sys.argv[1:] if not a.startswith('--')]
БЮДЖЕТ = float(_поз[0]) if _поз else 600.0
ПРИМЕНИТЬ = '--apply' in sys.argv
ОДИН = (sys.argv[sys.argv.index('--inn') + 1] if '--inn' in sys.argv else '')
ЛИМИТ = int(sys.argv[sys.argv.index('--limit') + 1]
            if '--limit' in sys.argv else 100000)
ПОТОК = r'C:\seostat\drop\vk_contacts_stream.jsonl'
НАЧАЛО = time.time()

db = EDB.EnrichDB()
e = db.cx
ТЕХ = set(EDB.EnrichDB.TECH_ROLES)


def цели():
    if ОДИН:
        return [ОДИН]
    сделано = set()
    if os.path.exists(ПОТОК):
        for ln in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                j = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if not j.get('err'):
                сделано.add(str(j.get('inn')))
    из = []
    for inn, name, site in e.execute(
            'SELECT inn, name, site FROM companies '
            # revenue_rub, а НЕ pxr: колонка pxr пуста у всех 9924 компаний, и
            # сортировка по ней даёт произвольный порядок под видом «сверху
            # вниз по выручке». Живая колонка — revenue_rub (1461 непустых).
            'ORDER BY COALESCE(revenue_rub,0) DESC'):
        if str(inn) in сделано:
            continue
        из.append({'inn': str(inn), 'name': name or '', 'site': site or ''})
        if len(из) >= ЛИМИТ:
            break
    return из


def main():
    todo = цели()
    out = {'целей': len(todo), 'пройдено': 0, 'со_слагом': 0, 'с_группой': 0,
           'с_контактами': 0, 'почт': 0, 'телефонов': 0, 'людей': 0,
           'телефонов_отсеяно': 0, 'технических': 0, 'ошибок': 0,
           'режим': 'ПРИМЕНЕНИЕ' if ПРИМЕНИТЬ else 'сухой прогон (--apply)',
           'примеры': []}
    # раннер отдаёт stdout ХВОСТОМ — печатаем счётчики и в начале, и в конце
    print(json.dumps({'старт': True, **{k: v for k, v in out.items()
                                        if not isinstance(v, list)}},
                     ensure_ascii=False))
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    for c in todo:
        if time.time() - НАЧАЛО > БЮДЖЕТ:
            break
        inn = c['inn']
        итог = {'inn': inn}
        try:
            vkc = EC.find_vk_group_contacts(c) or {}
        except Exception as ex:  # noqa: BLE001
            out['ошибок'] += 1
            итог['err'] = f'{type(ex).__name__}:{str(ex)[:90]}'
            ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
            ф.flush()
            os.fsync(ф.fileno())
            continue
        out['пройдено'] += 1
        if vkc.get('error'):
            итог['нет'] = str(vkc['error'])[:110]
        if vkc.get('group'):
            out['с_группой'] += 1
            out['со_слагом'] += 1
            итог['группа'] = vkc.get('url')
            итог['как_подтверждена'] = vkc.get('verified_by')
        конт = vkc.get('contacts') or []
        if конт:
            out['с_контактами'] += 1
        итог['контактов'] = len(конт)

        # приводим ответ ВК к форме результата конвейера, чтобы писал общий
        # persist_contacts, а не свой INSERT
        r = {'emails': [], 'phone_roles': [], 'people': []}
        for x in конт:
            роль = (x.get('desc') or '').strip()
            фио = (x.get('person') or '').strip()
            if x.get('email'):
                r['emails'].append(
                    {'email': x['email'], 'role': роль or 'общий',
                     'person': фио, 'source': 'vk-group',
                     'source_url': vkc.get('url') or ''})
            if x.get('phone'):
                r['phone_roles'].append(
                    {'phone': x['phone'], 'role': роль, 'dept': роль,
                     'person': фио, 'source': 'vk-group',
                     'source_url': vkc.get('url') or ''})
            if фио:
                r['people'].append(
                    {'person': фио, 'post': роль, 'phone': x.get('phone') or '',
                     'email': x.get('email') or '', 'source': 'vk-group',
                     'source_url': vkc.get('url') or ''})
                канон = EDB.EnrichDB._canon_role(роль)
                if канон in ТЕХ:
                    out['технических'] += 1
                if len(out['примеры']) < 16:
                    out['примеры'].append(
                        {'инн': inn, 'фио': фио, 'должность': роль,
                         'тел': x.get('phone') or '', 'почта': x.get('email') or '',
                         'ссылка': vkc.get('url') or ''})
        # почты из описания группы — без роли и без человека, кладём ниже
        for адрес in (vkc.get('emails') or []):
            r['emails'].append({'email': адрес, 'role': 'общий', 'person': '',
                                'source': 'vk-group',
                                'source_url': vkc.get('url') or ''})

        if ПРИМЕНИТЬ:
            из = EC.persist_contacts(db, inn, r, source='vk-group')
            for k in ('почт', 'телефонов', 'людей', 'телефонов_отсеяно'):
                out[k] += из.get(k, 0)
            итог['записано'] = из
            try:
                db.cx.execute(
                    'INSERT OR REPLACE INTO stage_log(inn, stage, detail, ts) '
                    'VALUES(?,?,?,datetime("now"))',
                    (inn, 'vk_contacts',
                     f"группа={vkc.get('url') or '-'} контактов={len(конт)}"))
                db.cx.commit()
            except Exception:  # noqa: BLE001
                pass
        else:
            итог['было_бы'] = {'почт': len(r['emails']),
                               'телефонов': len(r['phone_roles']),
                               'людей': len(r['people'])}
        ф.write(json.dumps(итог, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
    ф.close()

    print(json.dumps({'примеры': out.pop('примеры')}, ensure_ascii=False)[:1800])
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
