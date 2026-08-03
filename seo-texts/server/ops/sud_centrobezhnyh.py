# -*- coding: utf-8 -*-
"""Суд над карточками панели: доказывает ли карточка воздушный центробежный.

Задание владельца: по каждой карточке одна линза доказывает, что центробежный
компрессор на предприятии ЕСТЬ (или его покупают, или собираются купить),
вторая доказывает, что его нет, а судья выносит приговор. На выходе в панели
остаются только доказанные, мусор и непрофильные не показываются вовсе.

ПОЧЕМУ СПОР, А НЕ ОДИН ВОПРОС. Одиночная модель на вопрос «есть ли тут
центробежный компрессор» отвечает «да» слишком охотно: в карточке почти всегда
есть слово «компрессор» или «воздуходувка», и его хватает. Ровно на этом
сгорела разметка источника — соседняя сессия показала три карточки подряд, где
«центробежная» стояло по слову: RRF-350 это Рутс, ГАЦ-28-6М3 колесо вентилятора
АВО, WORTEX BB 2536-D ручной инструмент. Adversarial-линза обязана искать
опровержение, и это меняет ответ.

МОДЕЛИ — по замеру владельца от 02.08, а не по привычке. Линзы разбирают
свободный текст, это `gemini-3.6-flash`. Приговор — спорный случай и судейство,
это `claude-fable-5`, он дороже, но полнее. Гонять обе линзы через fable значит
платить в тридцать раз больше за тот же разбор.

DURABILITY. Приговор пишется в СЕРВЕРНОЕ хранилище — таблица `sud_centro` в
`enrich.db` плюс jsonl с fsync — а не только в возвращаемый JSON. Песочница при
рестарте откатывается к снимку, и результат прогона на тысячу карточек исчез бы
целиком. Прогон резюмируемый: уже осуждённые ИНН пропускаются, поэтому его
можно бить на куски и переживать перезапуск.

По умолчанию СУХОЙ ПРОГОН: судит и пишет приговоры, но НИЧЕГО не скрывает.
Запуск: python sud_centrobezhnyh.py [--lim N] [--potok N] [--apply]
        [--skryt-neustanovleno]
"""
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ЦБ = os.getenv('CENTRIFUGAL_DB') or r'C:\seostat\data\centrifugal.db'
ПР = os.getenv('CENTRO_SALES_DB') or r'C:\seostat\data\centro_sales.db'
ЖУРНАЛ = r'C:\sender\server\sud_centro.jsonl'
КЛЮЧ = os.environ.get('PROVIDER_API_KEY', '')
БАЗА_API = os.environ.get('PROVIDER_BASE_URL', 'https://router.cheap').rstrip('/')
МОДЕЛЬ_ЛИНЗЫ = 'gemini-3.6-flash'
МОДЕЛЬ_СУДЬИ = 'claude-fable-5'
ПРИМЕНИТЬ = '--apply' in sys.argv
СКРЫТЬ_НЕУСТ = '--skryt-neustanovleno' in sys.argv
ФАКТОВ_В_КАРТОЧКЕ = 22
# Версия суда. Приговор без карты позиций (см. `fakty_ids`) применить к фактам
# нельзя: судья возвращает НОМЕРА строк карточки, а не id фактов, и без
# сохранённого порядка номер «3» указывает в пустоту после любой пересборки.
# Первая версия карту не писала; повышение версии заставляет пересудить.
ВЕРСИЯ_СУДА = 2
_ПЕЧАТЬ = threading.Lock()


def арг(имя, поум):
    try:
        return int(sys.argv[sys.argv.index(имя) + 1])
    except (ValueError, IndexError):
        return поум


ЛИМ = арг('--lim', 40)
ПОТОК = арг('--potok', 6)
БЮДЖЕТ_С = арг('--budzhet', 1500)

ЗНАНИЕ = (
    'ЧТО СЧИТАЕТСЯ НАШЕЙ МАШИНОЙ. Воздушный ЦЕНТРОБЕЖНЫЙ (динамический, '
    'турбо) компрессор: серии К-250, К-350, К-500, К-905, К-1500, ЦК, ЦТК, '
    'ТКА, 32ВЦ/43ВЦ, турбовоздуходувки ТВ, нагнетатели ГПА, Centac, Elliott, '
    'Cooper-Bessemer, Siemens STC, Atlas Copco ZH (именно ZH), Aerzen TB, '
    'Turbomax, Turbowin, HIBON, Neuros, Sulzer.\n'
    'ЧТО НАШЕЙ МАШИНОЙ НЕ ЯВЛЯЕТСЯ, даже если слово похоже: винтовые и '
    'поршневые (GA/GX, ZS/ZR, ВК, ЗИФ, ПКС, ВП, FUBAG, Remeza), ВИХРЕВЫЕ и '
    'воздуходувки Рутса (RR/RRF/RRG, Kaeser Omega, Robuschi RBS, 1А, 2АФ), '
    'вентиляторы и дымососы, аппараты воздушного охлаждения, паровые турбины '
    'и турбоагрегаты ТЭЦ, турбокомпрессоры дизелей (ТКР, ТК-23С, КАМАЗ), '
    'НАСОСЫ любые, садовый и ручной инструмент (Zitrek, WORTEX, MELTPLAST), '
    'теплообменники, градирни, трубопроводы и здания.\n'
    'СРЕДА должна быть ВОЗДУХ. Азотные, кислородные, газовые и водородные '
    'компрессоры — другие машины, они НЕ считаются.\n'
    'ЗАСЧИТЫВАЕТСЯ и «есть на предприятии», и «покупает», и «планирует '
    'купить»: продавцу нужны оба случая.'
)


def _апи_чат(модель, промпт, максимум=1200):
    """Не-Claude модель: /v1/chat/completions и Bearer."""
    тело = json.dumps({'model': модель, 'max_tokens': максимум,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    зпр = urllib.request.Request(
        БАЗА_API + '/v1/chat/completions', data=тело, method='POST',
        headers={'Authorization': 'Bearer ' + КЛЮЧ,
                 'Content-Type': 'application/json',
                 'User-Agent': 'curl/8.5.0'})
    with urllib.request.urlopen(зпр, timeout=240) as о:
        д = json.loads(о.read().decode('utf-8', 'replace'))
    return (д['choices'][0]['message']['content'] or '')


def _апи_клод(промпт, максимум=1400):
    """Claude: /v1/messages, x-api-key, обязательный стрим.

    Не-Claude модель через этот путь ВИСНЕТ МОЛЧА, а Claude через
    /v1/chat/completions отвечает иначе — пути не взаимозаменяемы.
    """
    тело = json.dumps({'model': МОДЕЛЬ_СУДЬИ, 'max_tokens': максимум,
                       'stream': True,
                       'messages': [{'role': 'user', 'content': промпт}]},
                      ensure_ascii=False).encode('utf-8')
    зпр = urllib.request.Request(
        БАЗА_API + '/v1/messages', data=тело, method='POST',
        headers={'x-api-key': КЛЮЧ, 'anthropic-version': '2023-06-01',
                 'content-type': 'application/json',
                 'accept': 'text/event-stream', 'User-Agent': 'curl/8.5.0'})
    куски = []
    with urllib.request.urlopen(зпр, timeout=300) as о:
        for сырая in о:
            с = сырая.decode('utf-8', 'replace').strip()
            if not с.startswith('data:'):
                continue
            try:
                ев = json.loads(с[5:].strip())
            except Exception:  # noqa: BLE001
                continue
            if ев.get('type') == 'content_block_delta':
                куски.append((ев.get('delta') or {}).get('text', ''))
    return ''.join(куски)


def _джейсон(текст):
    """Достать объект из ответа. Модель любит обрамлять его пояснениями."""
    м = re.search(r'\{.*\}', текст or '', re.S)
    if not м:
        return {}
    try:
        return json.loads(м.group(0))
    except Exception:  # noqa: BLE001
        # частая беда: висячая запятая или обрезанный хвост
        чищ = re.sub(r',\s*([}\]])', r'\1', м.group(0))
        try:
            return json.loads(чищ)
        except Exception:  # noqa: BLE001
            return {}


def карточка(имя, регион, окв, факты):
    ст = [f'ПРЕДПРИЯТИЕ: {имя}', f'РЕГИОН: {регион or "не указан"}',
          f'ОКВЭД: {окв or "не указан"}', '', 'ФАКТЫ ИЗ БАЗЫ:']
    for i, ф in enumerate(факты, 1):
        части = [f'{i}.']
        if ф['status']:
            части.append(f'[{ф["status"]}]')
        if ф['model']:
            части.append(f'марка «{ф["model"][:60]}»')
        if ф['equipment_type']:
            части.append(f'тип: {ф["equipment_type"][:50]}')
        if ф['medium']:
            части.append(f'среда: {ф["medium"][:30]}')
        if ф['event_date']:
            части.append(f'дата: {ф["event_date"][:20]}')
        if ф['evidence']:
            части.append(f'чем доказано: {ф["evidence"][:90]}')
        if ф['quote']:
            части.append(f'цитата: «{ф["quote"][:220]}»')
        ст.append(' '.join(части))
    return '\n'.join(ст)


def судить(строка):
    инн, имя, регион, окв, факты = строка
    к = карточка(имя, регион, окв, факты)
    # Карта позиций: судья отвечает НОМЕРАМИ строк карточки, и без этого
    # списка его «мусорные факты 3, 7» применить не к чему.
    итог = {'inn': инн, 'imya': имя, 'faktov': len(факты),
            'fakty_ids': [ф['id'] for ф in факты]}
    try:
        за = _джейсон(_апи_чат(МОДЕЛЬ_ЛИНЗЫ, (
            'Ты ОБВИНИТЕЛЬ в споре о промышленном оборудовании. Твоя задача — '
            'доказать, что на предприятии ЕСТЬ воздушный центробежный '
            'компрессор либо его покупают или планируют купить.\n\n'
            + ЗНАНИЕ +
            '\n\nОпирайся ТОЛЬКО на карточку, ничего не домысливай. Верни '
            'СТРОГО JSON: {"nomera": [номера фактов, которые это доказывают], '
            '"dovod": "одно предложение", "sila": 0..3}. sila=0 значит, что '
            'доказательств в карточке нет вовсе — так и скажи, не выдумывай.'
            '\n\n' + к)))
        против = _джейсон(_апи_чат(МОДЕЛЬ_ЛИНЗЫ, (
            'Ты ЗАЩИТНИК в споре о промышленном оборудовании. Твоя задача — '
            'доказать, что карточка НЕ доказывает наличия или покупки '
            'воздушного центробежного компрессора: машина другого принципа, '
            'другая среда, чужая техника, насос, вентилятор, инструмент, или '
            'же в карточке вообще нет речи о компрессорах.\n\n'
            + ЗНАНИЕ +
            '\n\nОпирайся ТОЛЬКО на карточку. Верни СТРОГО JSON: '
            '{"nomera": [номера фактов, которые вводят в заблуждение], '
            '"dovod": "одно предложение", "sila": 0..3}.\n\n' + к)))
        приговор = _джейсон(_апи_клод(
            'Ты СУДЬЯ. Перед тобой карточка предприятия из базы продаж '
            'компрессорной компании и два довода: обвинение утверждает, что '
            'воздушный центробежный компрессор есть или его покупают, защита '
            'утверждает обратное.\n\n' + ЗНАНИЕ +
            '\n\nСуди строго по карточке. Ложное «есть» стоит продавцу '
            'впустую потраченного звонка и доверия к базе, поэтому при '
            'сомнении выбирай «не установлено», а не «есть».\n\n'
            f'{к}\n\nОБВИНЕНИЕ: {json.dumps(за, ensure_ascii=False)}\n'
            f'ЗАЩИТА: {json.dumps(против, ensure_ascii=False)}\n\n'
            'Верни СТРОГО JSON: {"verdikt": "есть|покупает|планирует|нет|'
            'не установлено", "uverennost": 0..3, "pochemu": "одно-два '
            'предложения", "fakty_za": [номера], "fakty_musor": [номера '
            'фактов, которые к компрессорам отношения не имеют]}'))
        итог.update({
            'za': за, 'protiv': против,
            'verdikt': (приговор.get('verdikt') or 'не установлено').strip(),
            'uverennost': int(приговор.get('uverennost') or 0),
            'pochemu': (приговор.get('pochemu') or '')[:400],
            'fakty_za': приговор.get('fakty_za') or [],
            'fakty_musor': приговор.get('fakty_musor') or [],
        })
    except Exception as e:  # noqa: BLE001
        итог['err'] = f'{type(e).__name__}: {str(e)[:140]}'
    return итог


def зеркало(итог):
    """Положить приговор в базу продаж, откуда его читает панель."""
    try:
        пр = sqlite3.connect(ПР, timeout=20)
        пр.execute('PRAGMA busy_timeout=20000')
        пр.execute(
            'CREATE TABLE IF NOT EXISTS sud_verdikt('
            'inn TEXT PRIMARY KEY, verdikt TEXT, uverennost INTEGER, '
            'pochemu TEXT, ts TEXT)')
        пр.execute(
            'INSERT OR REPLACE INTO sud_verdikt(inn, verdikt, uverennost, '
            'pochemu, ts) VALUES(?,?,?,?,?)',
            (итог['inn'], итог['verdikt'], итог['uverennost'],
             итог['pochemu'][:400], time.strftime('%Y-%m-%dT%H:%M:%S')))
        пр.commit()
        пр.close()
    except Exception as e:  # noqa: BLE001
        with _ПЕЧАТЬ:
            print(f'  зеркало приговора не легло: {str(e)[:90]}')


def main():
    if not КЛЮЧ:
        raise SystemExit('нет PROVIDER_API_KEY в окружении раннера')

    db = EDB.EnrichDB()
    db.cx.execute(
        'CREATE TABLE IF NOT EXISTS sud_centro('
        'inn TEXT PRIMARY KEY, verdikt TEXT, uverennost INTEGER, pochemu TEXT,'
        'fakty_za TEXT, fakty_musor TEXT, za TEXT, protiv TEXT, ts TEXT)')
    for стлб, опр in (('fakty_ids', 'TEXT'), ('versiya', 'INTEGER')):
        try:
            db.cx.execute(f'ALTER TABLE sud_centro ADD COLUMN {стлб} {опр}')
        except Exception:  # noqa: BLE001
            pass
    db.cx.commit()
    осуждены = {r[0] for r in db.cx.execute(
        "SELECT inn FROM sud_centro WHERE COALESCE(verdikt,'')<>'' "
        'AND COALESCE(versiya,1) >= ?', (ВЕРСИЯ_СУДА,))}

    цб = sqlite3.connect(f'file:{ЦБ}?mode=ro', uri=True, timeout=20)
    кол = [c[1] for c in цб.execute('PRAGMA table_info("company")')]
    имя_к = next((k for k in ('predpriyatie', 'name', 'name_full') if k in кол), 'inn')
    рег_к = 'region' if 'region' in кол else None
    окв_к = 'okved' if 'okved' in кол else None
    выб = f'SELECT inn, "{имя_к}"' + (f', "{рег_к}"' if рег_к else ", ''") \
          + (f', "{окв_к}"' if окв_к else ", ''") + ' FROM company'
    компании = {str(r[0]): (r[1] or '', r[2] or '', r[3] or '')
                for r in цб.execute(выб)}
    факты = {}
    for r in цб.execute(
            'SELECT inn, COALESCE(status,\'\'), COALESCE(model,\'\'), '
            'COALESCE(equipment_type,\'\'), COALESCE(medium,\'\'), '
            'COALESCE(event_date,\'\'), COALESCE(evidence,\'\'), '
            'COALESCE(quote,\'\'), id FROM fact'):
        факты.setdefault(str(r[0]), []).append({
            'status': r[1], 'model': r[2], 'equipment_type': r[3],
            'medium': r[4], 'event_date': r[5], 'evidence': r[6],
            'quote': r[7], 'id': r[8]})
    цб.close()

    пр = sqlite3.connect(ПР, timeout=20)
    пр.execute('PRAGMA busy_timeout=20000')
    скрыты = set()
    скрыты_судом = set()
    for _и, _пр in пр.execute(
            "SELECT inn, COALESCE(reason,'') FROM hidden_item "
            "WHERE kind='company'"):
        скрыты.add(str(_и))
        if str(_пр).lower().startswith('суд моделей'):
            скрыты_судом.add(str(_и))

    # СУДИМ ВИДИМЫХ И ПЕРЕОТКРЫТЫХ. Прежнее правило «только видимые» было
    # верным ровно до того дня, когда появилась доливка: `pereotkryt_dela.py`
    # снимает приговор у тех, по кому пришли НОВЫЕ доказательства, в том числе
    # у скрытых — а скрытых этот отбор не берёт. Дело оставалось без приговора
    # навсегда: скрыт, значит не судим; не судим, значит приговора нет; нет
    # приговора — нечему его отменить.
    #
    # Замер, на котором это вскрылось: из 834 скрытых предприятий 717 стояли
    # без приговора, то есть три четверти скрытой части базы висели в петле, и
    # доказательства, добытые для них из реестра ЭПБ, пропадали впустую.
    #
    # Скрытого БЕЗ приговора судим (его дело переоткрыто). Скрытого С
    # приговором пропускаем, как и раньше: там решение уже есть, и платить за
    # повтор незачем.
    # Только те, кого прятал САМ СУД: скрытых ручной чисткой и непрофильным
    # ОКВЭДом судить не за что, и платить за них тем более. Из 834 скрытых под
    # это правило подпадает лишь часть — остальные убраны по другим основаниям.
    переоткрытые = {и for и in скрыты_судом if и not in осуждены}
    очередь = []
    for инн, (имя, рег, окв) in компании.items():
        if инн in осуждены:
            continue
        if инн in скрыты and инн not in переоткрытые:
            continue
        ф = факты.get(инн, [])
        # самые содержательные вперёд: с маркой и цитатой
        ф.sort(key=lambda x: (bool(x['model']), bool(x['quote']),
                              len(x['quote'])), reverse=True)
        очередь.append((инн, имя, рег, окв, ф[:ФАКТОВ_В_КАРТОЧКЕ]))
    print(f'видимых предприятий: {len(компании) - len(скрыты & set(компании))}, '
          f'переоткрытых скрытых: {len(переоткрытые & set(компании))}, '
          f'уже осуждено ранее: {len(осуждены)}, в этот прогон: '
          f'{min(len(очередь), ЛИМ)} из {len(очередь)}')
    sys.stdout.flush()
    очередь = очередь[:ЛИМ]
    if not очередь:
        print('судить нечего')
        return

    начало = time.time()
    вердикты = Counter()
    ошибок = 0
    готово = 0
    with ThreadPoolExecutor(max_workers=ПОТОК) as пул:
        for итог in пул.map(судить, очередь):
            готово += 1
            # ПИШЕМ СРАЗУ, а не в конце: прогон могут оборвать по времени,
            # и всё, что не легло в enrich.db, придётся оплачивать заново
            with open(ЖУРНАЛ, 'a', encoding='utf-8') as ж:
                ж.write(json.dumps(итог, ensure_ascii=False) + '\n')
                ж.flush()
                os.fsync(ж.fileno())
            if итог.get('err'):
                ошибок += 1
                if ошибок <= 4:
                    print(f'  {итог["inn"]}: {итог["err"]}')
                continue
            вердикты[итог['verdikt']] += 1
            # ЗЕРКАЛО В БАЗУ ПРОДАЖ. Панель читает centrifugal.db (её
            # пересобирают офлайн) и centro_sales.db (её не пересобирают).
            # Приговор нужен продавцу В ФИЛЬТРЕ, значит он обязан пережить
            # пересборку — а enrich.db панель не видит вовсе.
            зеркало(итог)
            db.cx.execute(
                'INSERT OR REPLACE INTO sud_centro(inn, verdikt, uverennost, '
                'pochemu, fakty_za, fakty_musor, za, protiv, ts, fakty_ids, '
                'versiya) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (итог['inn'], итог['verdikt'], итог['uverennost'],
                 итог['pochemu'], json.dumps(итог['fakty_za']),
                 json.dumps(итог['fakty_musor']),
                 json.dumps(итог.get('za'), ensure_ascii=False)[:1200],
                 json.dumps(итог.get('protiv'), ensure_ascii=False)[:1200],
                 time.strftime('%Y-%m-%dT%H:%M:%S'),
                 json.dumps(итог.get('fakty_ids') or []), ВЕРСИЯ_СУДА))
            db.cx.commit()
            if готово % 10 == 0:
                with _ПЕЧАТЬ:
                    print(f'  … {готово}/{len(очередь)}, '
                          f'{dict(вердикты)}, ошибок {ошибок}')
                    sys.stdout.flush()
            if time.time() - начало > БЮДЖЕТ_С:
                print(f'бюджет времени вышел на {готово} из {len(очередь)}')
                break

    print(json.dumps({
        'осуждено_в_этот_прогон': готово,
        'вердикты': вердикты.most_common(),
        'ошибок': ошибок,
        'секунд': round(time.time() - начало),
    }, ensure_ascii=False, indent=1))

    # ---- применение: скрыть то, что суд не подтвердил
    убрать = {'нет'}
    if СКРЫТЬ_НЕУСТ:
        убрать.add('не установлено')
    к_скрытию = {r[0]: (r[1], r[2] or '') for r in db.cx.execute(
        'SELECT inn, verdikt, pochemu FROM sud_centro WHERE verdikt IN '
        f'({",".join("?" * len(убрать))})', tuple(убрать))
        if r[0] not in скрыты}
    print(f'по приговорам подлежит скрытию: {len(к_скрытию)} '
          f'(режим {"ПРИМЕНЕНИЕ" if ПРИМЕНИТЬ else "сухой"})')
    if not (ПРИМЕНИТЬ and к_скрытию):
        return
    сейчас = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    пр.executemany(
        'INSERT OR REPLACE INTO hidden_item'
        '(inn, kind, value, reason, username, created_at) VALUES(?,?,?,?,?,?)',
        [(и, 'company', и, f'суд моделей: {в} — {п}'[:200], 'admin', сейчас)
         for и, (в, п) in к_скрытию.items()])
    пр.commit()
    стало = {str(r[0]) for r in
             пр.execute("SELECT inn FROM hidden_item WHERE kind='company'")}
    пр.close()
    print(json.dumps({'скрыто_всего': len(стало),
                      'видимых_осталось': len(компании) - len(стало & set(компании))},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
