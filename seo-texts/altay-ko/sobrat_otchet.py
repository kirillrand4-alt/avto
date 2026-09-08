# -*- coding: utf-8 -*-
"""Собирает из jsonl/json два markdown-файла:
  ALTAY-KO-IDEI-PO-LINZAM.md      - все идеи как есть, по металинзам и линзам (сырой слой)
  ALTAY-KO-PRIYOMY-I-PROVERKA.md  - уникальные приёмы + статус по документам инструментов
Запуск (из seo-texts/):  python3 altay-ko/sobrat_otchet.py"""
import json, os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def load_jsonl(n):
    p = os.path.join(HERE, n)
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def idei_md():
    linzy = load_jsonl('metalinzy-linzy.jsonl')
    idei = load_jsonl('metalinzy-idei.jsonl')
    po_linze = {r['linza_id']: r for r in idei}
    out = ['# Алтайский край, предприятия с КО: идеи от линз (сырой слой)', '',
           f'Металинз: {len(linzy)}. Линз: {sum(len(r["linzy"]) for r in linzy)}. '
           f'Линз с идеями: {len(idei)}. Идей: {sum(len(r["idei"]) for r in idei)}. '
           f'Модель: claude-fable-5 через провайдерский API.', '',
           'Формат идеи тот же, что в PASPORT-LINZY.json: что сделать / зачем (почему это след машины) / '
           'класс доказательства / где брать / как проверить (с контролем) / чем рискуем / цена / ожидаемо.', '']
    for m in sorted(linzy, key=lambda r: r['meta_id']):
        out.append(f'## {m["meta_id"]}. Металинза «{m["meta"]}»'); out.append('')
        for i, l in enumerate(m['linzy'], 1):
            lid = f'{m["meta_id"]}-L{i}'
            r = po_linze.get(lid)
            out.append(f'### {lid}. Линза «{l.get("imya", "")}»'); out.append('')
            out.append(f'Фокус: {l.get("fokus", "")}'); out.append('')
            if not r:
                out.append('_идей нет (вызов не удался)_'); out.append(''); continue
            for j, x in enumerate(r['idei'], 1):
                out.append(f'**{lid}-{j}.** {x.get("ideya", "")}')
                out.append(f'- зачем: {x.get("zachem", "")}')
                out.append(f'- класс: {x.get("klass", "")} · цена: {x.get("cena", "")} · ожидаемо: {x.get("ozhidaemo", "")}')
                out.append(f'- где брать: {x.get("gde_brat", "")}')
                out.append(f'- как проверить: {x.get("kak_proverit", "")}')
                out.append(f'- чем рискуем: {x.get("chem_riskuem", "")}')
                out.append('')
    open(os.path.join(HERE, 'ALTAY-KO-IDEI-PO-LINZAM.md'), 'w', encoding='utf-8').write('\n'.join(out))
    return len(idei), sum(len(r['idei']) for r in idei)


def priyomy_md():
    p = os.path.join(HERE, 'priyomy.json')
    if not os.path.exists(p):
        return
    pr = json.load(open(p, encoding='utf-8'))['priyomy']
    prov = {r['id']: r for r in load_jsonl('proverka-priyomov.jsonl')}
    poryadok = ['реализовано', 'частично', 'закрыт', 'не подтверждено цитатой', 'нет']
    c = Counter((prov.get(x['id']) or {}).get('status', 'не проверено') for x in pr)
    out = ['# Алтайский край, предприятия с КО: уникальные приёмы и проверка по инструментам', '',
           f'Приёмов: {len(pr)}. Статусы: ' + ', '.join(f'{k} {c[k]}' for k in poryadok + ['не проверено'] if c.get(k)), '',
           'Документы, по которым проверялось: PARK-2S-INSTRUMENTY-peredacha.md, INSTRUMENTY-I-PRIYOMY.md, '
           'DOKA-kakoy-skript-chto-delaet.md (замена отсутствующего INSTRUMENTY-KAK-POLZOVATSYA.md). '
           'Статусы «реализовано»/«частично»/«закрыт» засчитаны только с дословной цитатой, найденной в документе '
           'механически; без найденной цитаты статус понижен до «не подтверждено цитатой».', '']
    for k in prov:
        if k.startswith('K-'):
            r = prov[k]
            out.append(f'- Контроль {k}: статус «{r["status"]}», инструмент «{r.get("chem", "")}», цитата найдена: {r["citata_naydena"]}')
    out.append('')
    gruppy = defaultdict(list)
    for x in pr:
        gruppy[(prov.get(x['id']) or {}).get('status', 'не проверено')].append(x)
    for st in poryadok + ['не проверено']:
        if not gruppy.get(st):
            continue
        out.append(f'## Статус: {st} ({len(gruppy[st])})'); out.append('')
        for x in gruppy[st]:
            r = prov.get(x['id']) or {}
            out.append(f'### {x["id"]}. {x["nazvanie"]}')
            out.append(f'- источник: {x.get("istochnik", "")} · класс: {x.get("klass", "")} · цена: {x.get("cena", "")} · идей: {len(x.get("idei", []))} ({", ".join(x.get("idei", [])[:8])}{"…" if len(x.get("idei", [])) > 8 else ""})')
            out.append(f'- суть: {x.get("sut", "")}')
            if r:
                if r.get('chem'):
                    out.append(f'- инструмент: `{r["chem"]}` · слой: {r.get("sloy", "")}')
                if r.get('citata'):
                    out.append(f'- цитата ({r.get("dokument_fakt") or r.get("dokument", "")}{"" if r.get("citata_naydena") else ", НЕ найдена в документе"}): «{r["citata"]}»')
                if r.get('status_ishodnyy'):
                    out.append(f'- статус по ответу модели был «{r["status_ishodnyy"]}», понижен: цитата не найдена')
                if r.get('chto_dodelat'):
                    out.append(f'- что доделать: {r["chto_dodelat"]}')
            out.append('')
    open(os.path.join(HERE, 'ALTAY-KO-PRIYOMY-I-PROVERKA.md'), 'w', encoding='utf-8').write('\n'.join(out))
    return len(pr), dict(c)


if __name__ == '__main__':
    print('идеи:', idei_md())
    print('приёмы:', priyomy_md())
