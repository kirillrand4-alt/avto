# -*- coding: utf-8 -*-
"""Разбор карточек tender.pro провайдерским API: ФИО, должность, телефон, почта.

ПОЧЕМУ ЭТО ГЛАВНЫЙ КАНАЛ. Замер за ночь: из 77 технарей с личным мобильным
**73 пришли с tender.pro и только 4 с сайтов предприятий**. Контакт там лежит
свободным текстом в блоке «Комментарий:», рядом с фамилией и должностью, и
привязка к юрлицу даётся самим документом, а не нашим сопоставлением.

ПОЧЕМУ ПРОВАЙДЕР, А НЕ РЕГУЛЯРКА. Текст живой: «Контактное лицо по техническим
вопросам: Инженер-энергетик  Волков Максим Валерьевич, +7 924 228 04 44»,
«По всем вопросам обращаться к Михееву Максиму Владимировичу (843) 554-…».
Порядок слов, инициалы, должность до или после имени — регулярка тут даёт
мусор. Правило владельца: тяжёлую работу — через провайдерский API.

ЧТО ЗАПРЕЩЕНО МОДЕЛИ, и это записано в самом запросе:
  * достраивать должность, которой в тексте нет («инженер» ≠ «главный инженер»);
  * приписывать человеку номер, стоящий в другом предложении, — только если
    они названы вместе;
  * различать «контактное лицо по техническим вопросам» и настоящую должность:
    первое — роль в этой закупке, а не место работы человека.

DURABLE И РЕЗЮМИРУЕМО. Каждая карточка пишется в jsonl с fsync сразу; при
повторном запуске уже разобранные пропускаются. Рестарт контейнера прогон не
теряет — он идёт на сервере.

Запуск: python tp_razbor.py [--limit N] [--model MODEL]
"""
import io
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, r'C:\sender')   # gen_provider.py лежит здесь (спросил сервер)
sys.path.insert(0, r'C:\sender\server')

СЫРЬЁ = r'C:\seostat\drop\drop-storage\tp_raw.json'
ПОТОК = r'C:\seostat\drop\tp_razbor_lyudey.jsonl'
ЛИМИТ = 0
МОДЕЛЬ = 'claude-fable-5'
for i, а in enumerate(sys.argv):
    if а == '--limit' and i + 1 < len(sys.argv):
        ЛИМИТ = int(sys.argv[i + 1])
    if а == '--model' and i + 1 < len(sys.argv):
        МОДЕЛЬ = sys.argv[i + 1]

ЗАДАНИЕ = """Ты разбираешь текст блока «Комментарий» карточки закупки с площадки
tender.pro. Нужны КОНТАКТНЫЕ ЛИЦА: фамилия-имя-отчество, должность, телефон, почта.

ЖЁСТКИЕ ПРАВИЛА, нарушение делает строку негодной:
1. Бери ТОЛЬКО то, что написано в тексте. Ничего не достраивай и не угадывай.
   Если должность не названа — оставь пустую строку, это нормальный ответ.
2. «Инженер» и «главный инженер» — разные должности. Не повышай и не понижай.
3. Телефон приписывай человеку ТОЛЬКО если они названы вместе (в одном
   предложении или подряд). Номер из другого места текста — не его.
4. Отличай РОЛЬ В ЭТОЙ ЗАКУПКЕ от ДОЛЖНОСТИ НА ПРЕДПРИЯТИИ.
   «Контактное лицо по техническим вопросам», «консультации по техническим
   вопросам», «ответственный за процедуру» — это роль в закупке; тогда
   dolzhnost оставь пустой, а rol_v_zakupke заполни.
   «Главный энергетик», «инженер-энергетик», «начальник ОМТС» — должность.
5. Добавочный номер выноси отдельно в dobavochnyy, не склеивай с номером.
6. citata — короткий кусок исходного текста (до 160 знаков), из которого
   всё взято. Без цитаты строку не выдавай.

Ответ — ТОЛЬКО JSON, без пояснений:
{"lyudi": [{"fio": "", "dolzhnost": "", "rol_v_zakupke": "", "telefon": "",
            "dobavochnyy": "", "pochta": "", "citata": ""}]}
Если контактных лиц в тексте нет — {"lyudi": []}."""


def текст_ответа(о):
    """GP.call отдаёт объект _Msg, а не строку.

    Первый прогон дал «ответ не разобрался в JSON» на шести карточках из шести.
    Причина не в модели и не в шлюзе: я передавал в разбор сам объект, и
    `str(_Msg)` давал «<gen_provider._Msg object at 0x...>». Текст лежит в
    блоке content с типом text.
    """
    if isinstance(о, str):
        return о
    куски = []
    for б in (getattr(о, 'content', None) or []):
        if getattr(б, 'type', '') == 'text' or hasattr(б, 'text'):
            if getattr(б, 'type', 'text') != 'thinking':
                куски.append(str(getattr(б, 'text', '')))
    return '\n'.join(куски) if куски else str(о)


def вынуть_json(т):
    т = str(т or '').strip()
    м = re.search(r'\{.*\}', т, re.S)
    if not м:
        return None
    try:
        return json.loads(м.group(0))
    except Exception:
        куски = re.findall(r'\{[^{}]*"fio"[^{}]*\}', т, re.S)
        люди = []
        for к in куски:
            try:
                люди.append(json.loads(к))
            except Exception:
                pass
        return {'lyudi': люди} if люди else None


def main():
    import gen_provider as GP

    сыр = json.load(io.open(СЫРЬЁ, encoding='utf-8'))
    карточки = сыр.get('карточки') or []
    сделано = set()
    if os.path.exists(ПОТОК):
        for s in io.open(ПОТОК, encoding='utf-8', errors='replace'):
            try:
                сделано.add(str(json.loads(s).get('tender_id')))
            except Exception:
                continue
    очередь = [к for к in карточки
               if str(к.get('tender_id')) not in сделано
               and len(str(к.get('comment') or '')) > 30]
    if ЛИМИТ:
        очередь = очередь[:ЛИМИТ]
    print(f'карточек всего {len(карточки)}, уже разобрано {len(сделано)}, '
          f'в этот прогон {len(очередь)}')
    if not очередь:
        print('разбирать нечего')
        return

    клиент = GP.make_client()
    ф = io.open(ПОТОК, 'a', encoding='utf-8')
    стат = Counter()
    примеры = []
    for н, к in enumerate(очередь):
        текст = str(к.get('comment') or '')[:6000]
        соо = [{'role': 'user', 'content':
                f'{ЗАДАНИЕ}\n\nПРЕДПРИЯТИЕ: {к.get("company", "")}\n'
                f'ТЕКСТ КАРТОЧКИ:\n{текст}'}]
        try:
            ответ = GP.call(клиент, соо, model=МОДЕЛЬ)
        except Exception as e:  # noqa: BLE001
            стат[f'сбой вызова: {type(e).__name__}'] += 1
            continue
        разбор = вынуть_json(текст_ответа(ответ))
        if разбор is None:
            стат['ответ не разобрался в JSON'] += 1
            continue
        люди = [л for л in (разбор.get('lyudi') or [])
                if str(л.get('fio') or '').strip() and str(л.get('citata') or '').strip()]
        запись = {'tender_id': str(к.get('tender_id')), 'inn': str(к.get('inn')),
                  'company': str(к.get('company', ''))[:80],
                  'url': к.get('url', ''), 'дата': к.get('дата', ''),
                  'свежесть': к.get('свежесть', ''), 'lyudi': люди,
                  'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}
        ф.write(json.dumps(запись, ensure_ascii=False) + '\n')
        ф.flush()
        os.fsync(ф.fileno())
        стат['карточек разобрано'] += 1
        стат['людей извлечено'] += len(люди)
        for л in люди:
            if str(л.get('dolzhnost') or '').strip():
                стат['   с должностью предприятия'] += 1
            elif str(л.get('rol_v_zakupke') or '').strip():
                стат['   только роль в закупке'] += 1
            if str(л.get('telefon') or '').strip():
                стат['   с телефоном'] += 1
            if len(примеры) < 8 and str(л.get('dolzhnost') or '').strip():
                примеры.append(f"   {запись['inn']:12} {str(л.get('fio'))[:24]:24} "
                               f"{str(л.get('dolzhnost'))[:26]:26} "
                               f"{str(л.get('telefon'))[:18]}")
    ф.close()

    for п in примеры:
        print(п)
    print()
    print('=== ЧИСЛА ===')
    for к, v in sorted(стат.items()):
        print(f'   {к:36} {v:5}')


if __name__ == '__main__':
    main()
