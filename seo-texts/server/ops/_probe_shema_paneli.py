# -*- coding: utf-8 -*-
"""Схема таблиц person и contact в базе панели — перед тем как в них писать."""
import sys
sys.path.insert(0, r'C:\seostat')
from app.services import centro_catalog  # noqa: E402


def main():
    with centro_catalog.connect() as conn:
        for т in ('person', 'contact', 'import_info'):
            print(f'=== {т} ===')
            for c in conn.execute(f'PRAGMA table_info({т})').fetchall():
                print(f'  {c[1]:<22} {c[2]}')
            ряд = conn.execute(f'SELECT * FROM {т} LIMIT 2').fetchall()
            for r in ряд:
                print('  пример:', {k: (str(v)[:40] if v is not None else None)
                                    for k, v in dict(r).items()})


if __name__ == '__main__':
    main()
