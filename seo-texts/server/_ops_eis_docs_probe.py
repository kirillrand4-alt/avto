# -*- coding: utf-8 -*-
"""Разведка: какие ссылки на ДОКУМЕНТЫ отдаёт карточка закупки ЕИС.

Нужно для способа А5 (гриф «УТВЕРЖДАЮ»): техническую документацию утверждает
главный инженер, его должность и ФИО стоят на титульном листе. Прежде чем
писать разбор, надо увидеть, где лежат файлы и что это за форматы.
"""
import json
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402


def main():
    инн = sys.argv[1] if len(sys.argv) > 1 else '7424024375'
    z = EC.find_zakupki_contacts(инн, max_cards=2)
    out = {'инн': инн, 'rss': (z or {}).get('rss_items'), 'карточки': []}
    for c in ((z or {}).get('cards') or [])[:2]:
        url = c.get('url') or ''
        стр = {'url': url[-60:]}
        try:
            h = EC._eis_get(url)
            стр['байт'] = len(h)
            # вкладки карточки
            стр['вкладки'] = sorted(set(re.findall(
                r'href="([^"]*(?:documents|attachments|docs)[^"]*)"', h)))[:8]
            # прямые ссылки на файлы
            стр['файлы'] = sorted(set(re.findall(
                r'href="([^"]*(?:filestore|download|file\.html)[^"]*)"', h)))[:8]
            # есть ли слово УТВЕРЖДАЮ прямо на странице
            txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))
            стр['утверждаю_на_странице'] = 'УТВЕРЖДАЮ' in txt.upper()
            # пробуем вкладку документов
            m = re.search(r'href="([^"]*documents[^"]*)"', h)
            if m:
                du = m.group(1).replace('&amp;', '&')
                if du.startswith('/'):
                    du = 'https://zakupki.gov.ru' + du
                стр['вкладка_документов'] = du[-70:]
                hd = EC._eis_get(du)
                стр['док_байт'] = len(hd)
                стр['док_файлы'] = sorted(set(re.findall(
                    r'href="([^"]*(?:filestore|download)[^"]*)"', hd)))[:10]
                стр['имена_файлов'] = sorted(set(re.findall(
                    r'>([^<>]{4,80}\.(?:docx?|pdf|rtf|xlsx?|zip))<', hd)))[:10]
        except Exception as ex:  # noqa: BLE001
            стр['ошибка'] = f'{type(ex).__name__}: {str(ex)[:90]}'
        out['карточки'].append(стр)
    print(json.dumps(out, ensure_ascii=False)[:3500])


if __name__ == '__main__':
    main()
