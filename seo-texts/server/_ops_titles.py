# -*- coding: utf-8 -*-
"""Что лежит в заголовке карточки закупки: несёт ли он предмет."""
import json
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_contacts as EC  # noqa: E402

def main():
    inn = next((a for a in sys.argv[1:] if a.isdigit()), '0263009557')
    z = EC.find_zakupki_contacts(inn, max_cards=10)
    т = [(c.get('title') or '')[:110] for c in ((z or {}).get('cards') or [])]
    print(json.dumps({'инн': inn, 'карточек': len(т), 'заголовки': т,
                      'по_профилю': sum(1 for x in т
                                        if EC._ЗАКУПКА_ТЕХНИЧЕСКАЯ.search(x))},
                     ensure_ascii=False, indent=1)[:3000])

if __name__ == '__main__':
    main()
