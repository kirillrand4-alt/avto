import os, json
м = ['meyer_baza', 'kc_pishch_otbor', 'kc_spisok', 'cc_obhod', 'cc_checko_proxy', 'meyer_nalichie', 'meyer_proverka',
     'enrich_contacts', 'verify_company', 'kc_kontakty', 'kc_sayty', 'kc_audit', 'kc_audit2', 'poisk_otbor', 'poisk_razbor', 'meyer_xlsx', 'meyer_lpr']
o = {x: [os.path.exists(r'C:\sender\server\%s.py' % x), os.path.exists(r'C:\sender\%s.py' % x)] for x in м}
print('===ИТОГ==='); print(json.dumps(o))
