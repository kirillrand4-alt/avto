# -*- coding: utf-8 -*-
"""Прочитать протокол ЦЕЛИКОМ и посмотреть глазами, есть ли там состав комиссии.

Счётчик сказал «людей 10, технических 0», и я записал это как «гипотеза не
подтверждается». Но между «состав комиссии не публикуют» и «мы вырезаем не тот
кусок» разница принципиальная, а различить их можно только по живому тексту.
Печатаем начало документа, ВСЕ вхождения слова «комисси» с широким окном и
список найденных ФИО — без всякой модели, чтобы видеть сырьё.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

_ФИО = re.compile(r'[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
                  r'|[А-ЯЁ][а-яё\-]{2,}\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+')


def цели_из_потока():
    """ИНН, по которым прогон РЕАЛЬНО достал людей: у них протоколы точно есть."""
    import json as _j
    import os
    п = r'C:\seostat\drop\eis_protocols_stream.jsonl'
    из = []
    if os.path.exists(п):
        for ln in io.open(п, encoding='utf-8', errors='replace') if False else \
                open(п, encoding='utf-8', errors='replace'):
            try:
                x = _j.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if x.get('людей') and str(x.get('inn')) not in из:
                из.append(str(x['inn']))
    return из


def main():
    инны = [a for a in sys.argv[1:] if a.isdigit()] or цели_из_потока()[:4]
    inn = инны[0] if инны else ''
    out = {'инн': inn, 'кандидаты': инны[:4], 'документы': []}
    карточки = []
    for i in инны[:3]:
        z = EC.find_zakupki_contacts(i, max_cards=3)
        карточки += [(i, c) for c in ((z or {}).get('cards') or [])]
    for _i, c in карточки:
        for имя_ф, у in EC.eis_documents(c.get('url') or ''):
            if not EC._ДОК_ФОРМАТ.search(имя_ф or ''):
                continue
            txt = EC.doc_text(у)
            if not txt or len(txt) < 300:
                continue
            # Имя файла приходит с мусором разметки, поэтому «протокольность»
            # определяем ПО СОДЕРЖИМОМУ, а не по названию.
            if not re.search(r'протокол|комисси', txt[:4000], re.I):
                continue
            t = re.sub(r'[ \t]+', ' ', txt)
            зап = {'имя': (имя_ф or '')[:60], 'символов': len(t),
                   'ссылка': у[:90],
                   'начало': re.sub(r'\s+', ' ', t)[:900]}
            окна = []
            for m in re.finditer(r'комисси', t, re.I):
                окна.append(re.sub(r'\s+', ' ',
                                   t[max(0, m.start() - 350):m.start() + 900]))
            зап['вхождений_комисси'] = len(окна)
            зап['окна'] = окна[:3]
            зап['фио_в_документе'] = sorted(set(_ФИО.findall(t)))[:14]
            зап['есть_председатель'] = bool(re.search(r'председател', t, re.I))
            зап['есть_секретарь'] = bool(re.search(r'секретар', t, re.I))
            зап['есть_член_комиссии'] = bool(re.search(r'член\w*\s+комисси', t, re.I))
            зап['есть_инженер'] = bool(re.search(r'инженер', t, re.I))
            out['документы'].append(зап)
            if len(out['документы']) >= 2:
                break
        if len(out['документы']) >= 2:
            break
    print(json.dumps(out, ensure_ascii=False, indent=1)[:9000])


if __name__ == '__main__':
    main()
