# -*- coding: utf-8 -*-
"""Что лежит в заголовке карточки закупки: несёт ли он предмет."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

def main():
    inn = next((a for a in sys.argv[1:] if a.isdigit()), '0263009557')
    z = EC.find_zakupki_contacts(inn, max_cards=10)
    карт = (z or {}).get('cards') or []
    строки = [{'предмет': (c.get('subject') or '')[:120],
               'заголовок': (c.get('title') or '')[:50]} for c in карт]
    подошло = sum(1 for c in карт
                  if EC._ЗАКУПКА_ТЕХНИЧЕСКАЯ.search(
                      (c.get('title') or '') + ' ' + (c.get('subject') or '')))
    print(json.dumps({'инн': inn, 'карточек': len(карт),
                      'с_предметом': sum(1 for c in карт if c.get('subject')),
                      'подошло_по_профилю': подошло, 'строки': строки},
                     ensure_ascii=False, indent=1)[:3000])

if __name__ == '__main__':
    main()
