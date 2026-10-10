# -*- coding: utf-8 -*-
r"""Сайты, найденные агентами, — в общий обход (09.10, проба meyer7t; владелец: «почему не всё найдено из контактов?
confectum.org/contacts/»). Агент ищет сайт и номера ЛПР за ~10 шагов и всех отделов не собирает; полный сбор
(контакты, отделы, руководство, закупки, добавочные, почты) делает только обход kc_kontakty — а он шёл по сайту из
выдачи, часто чужому (Конфектум: export31.ru — центр поддержки экспорта, сайт отклонён; агент нашёл confectum.org с
ИНН, но взял один номер с главной).

Шаг: компании, у которых перепроверка агентов подтвердила сайт завода (kc_agent_pereproverka: сайт_завода_чей —
ИНН компании или отличительное слово названия на странице) и он не тот, что в списке, — сайт в <набор>-spisok.json
заменяется на сайт агента (прежний — в «сайт_был»). Дальше по обычной цепочке: обход (видит смену сайта и обходит
заново), чей номер, чей сайт, проверка сайта, опровергатели — по новому сайту. Под замком (zamok), атомарно.
"""
import io
import json
import os
import shutil
import sys
import time

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
import meyer_nalichie as MN  # noqa: E402
import zamok  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
СПИСОК = os.path.join(DIR, НАБОР + '-spisok.json')
АГЕНТЫ = os.path.join(DIR, НАБОР + '-glubokiy2.jsonl')


def main():
    if not os.path.exists(АГЕНТЫ):
        print('готово: перепроверки агентов нет', flush=True)
        return
    найдено = {}
    for s in io.open(АГЕНТЫ, encoding='utf-8', errors='replace'):
        try:
            x = json.loads(s)
        except ValueError:
            continue
        if x.get('сайт_завода') and x.get('сайт_завода_чей'):
            найдено[x['inn']] = (x['сайт_завода'], x['сайт_завода_чей'])
    # сайт из списка уже подтверждён (ИНН компании на нём или проверка Sol: «та же»/«группа») — не трогаем: проба 09.10,
    # moskart.ru и tiretsalt.ru с ИНН компании были заменены на другие сайты агента
    подтверждён = set()
    п_конт = os.path.join(DIR, НАБОР + '-kontakty.jsonl')
    if os.path.exists(п_конт):
        for s in io.open(п_конт, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('сайт') and з.get('inn') in (з.get('инн_живой') or []):
                подтверждён.add((з['inn'], MN.домен(з['сайт'])))
    п_пров = os.path.join(DIR, НАБОР + '-sayt-proverka.jsonl')
    if os.path.exists(п_пров):
        for s in io.open(п_пров, encoding='utf-8', errors='replace'):
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('итог') in ('та же', 'группа'):
                подтверждён.add((з.get('inn'), MN.домен(з.get('сайт') or '')))
    with zamok.замок(СПИСОК):
        сп = zamok.прочитать(СПИСОК)
        замен = []
        for i, (сайт, чей) in найдено.items():
            к = сп['компании'].get(i)
            if к is None or MN.домен(к.get('сайт') or '') == MN.домен(сайт):
                continue
            if (i, MN.домен(к.get('сайт') or '')) in подтверждён:
                continue
            к['сайт_был'] = к.get('сайт') or ''
            к['сайт'] = сайт if сайт.startswith('http') else 'https://' + сайт
            к['сайт_откуда'] = 'агент: %s' % str(чей)[:120]
            замен.append((i, к['сайт_был'], к['сайт']))
        if замен:
            shutil.copyfile(СПИСОК, СПИСОК + '.bak-' + time.strftime('%d%m-%H%M'))
            zamok.записать_атомарно(СПИСОК, сп)
    for i, был, стал in замен:
        print('%s: %s -> %s' % (i, был or '—', стал), flush=True)
    print('готово', json.dumps({'подтверждено агентами': len(найдено), 'сайт заменён': len(замен)}, ensure_ascii=False),
          flush=True)
    import kc_chuzhie_sayty  # 10.10: прежние сайты и «другая организация» — подходящие Meyer в список «вне списка»
    kc_chuzhie_sayty.запуск_из_шага()


if __name__ == '__main__':
    main()
