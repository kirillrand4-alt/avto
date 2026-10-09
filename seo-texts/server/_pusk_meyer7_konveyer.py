# -*- coding: utf-8 -*-
# Полный прогон Meyer: конвейер набора meyer7 ВОЛНАМИ (владелец 09.10): не ждёт конца поиска — волна каждые
# PILOT_VOLNA_MIN минут по уже найденному, финальный проход после поиска (pilot_konveyer.Волны).
# Разбор: сайты 40 потоков и каталоги 120 одновременно, не больше 3 запросов на каталог, предохранитель 10 отказов
# подряд, стоп-лист каталогов, что отказывают и браузеру (POISK_KAT_STOP); checko и b2b.house — razbor_brauzer.py.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'meyer7'
ЛОГ = os.path.join(DIR, '%s_konveyer_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_konveyer.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все',
                              PILOT_VOLNY='1', PILOT_VOLNA_MIN=os.environ.get('PILOT_VOLNA_MIN', '150'),
                              POISK_RAZBOR_POTOKOV='40', POISK_RAZBOR_POTOKOV_KAT='120', POISK_KAT_NA_DOMEN='3',
                              POISK_KAT_PREDOHR='10', POISK_KAT_STOP='1', RAZBOR_BRAUZER_MINUT='30',
                              # 09.10, итоги пробы и сравнения с серверным обогатителем (см. PLAN, часть Е):
                              # обход — свой + обогатитель внутри; его поиски через xmlriver — от 500 млн выручки
                              KC_EC='1', KC_EC_XML_OT='5e8', KC_EC_BEZ_MODELI=os.environ.get('KC_EC_BEZ_MODELI', '1'),
                              KC_LIMIT_MIN='25', KC_POTOKOV=os.environ.get('KC_POTOKOV', '48'),
                              # бюджет xmlriver 3,3 тыс. ₽: сайты по названию — потолок, агенты — стоп по остатку
                              PILOT_SAYTY_MAX='24000', KC_AGENT_XML_MIN='60',
                              # разметка — GPT-6 Luna (A/B 09.10 против 5.6: судья 9:4, ФИО 41 против 30); запасная — 5.6
                              PILOT_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna'))
выход.close()
time.sleep(20)
o = {'pid': p.pid, 'лог': os.path.basename(ЛОГ)}
отч = os.path.join(DIR, НАБОР + '-konveyer.json')
if os.path.exists(отч):
    with open(отч, encoding='utf-8', errors='replace') as f:
        o['статус'] = f.read()[-600:]
if os.path.exists(ЛОГ) and os.path.getsize(ЛОГ):
    with open(ЛОГ, encoding='utf-8', errors='replace') as f:
        o['хвост'] = f.read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
