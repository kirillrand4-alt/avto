# -*- coding: utf-8 -*-
# 14.10, база КЦ: полный прогон, конвейер набора kc1t (KC_CEL=kc). Сам ждёт «готово» в kc1t_poisk_*.log.
# 16.10 владелец: «не можешь пустить параллельно?» — волны (PILOT_VOLNY=1): конвейер идёт по найденному, не дожидаясь конца поиска.
# Агенты без лимита (пороги выручки как в полном прогоне Meyer: Sol от 500 млн, Luna от 120 млн).
# Продолжить с шага N: PILOT_S_SHAGA=N в окружении раннера (по умолчанию 0).
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
НАБОР = 'kc1'
ЛОГ = os.path.join(DIR, '%s_konveyer_%s.log' % (НАБОР, time.strftime('%d%m-%H%M')))
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', os.path.join(DIR, 'pilot_konveyer.py')],
                     cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                     stdout=выход, stderr=subprocess.STDOUT, close_fds=False,
                     env=dict(os.environ, POISK_NABOR=НАБОР, KC_NABOR=НАБОР, POISK_REGIONY_SVERKI='все', KC_CEL='kc',
                              PILOT_VOLNY='1', PILOT_VOLNA_MIN=os.environ.get('PILOT_VOLNA_MIN', '150'),
                              POISK_RAZBOR_POTOKOV='40', POISK_RAZBOR_POTOKOV_KAT='120', POISK_KAT_NA_DOMEN='3',
                              POISK_KAT_PREDOHR='10', POISK_KAT_STOP='1', RAZBOR_BRAUZER_MINUT='30',
                              KC_EC='1', KC_EC_XML_OT='5e8', KC_EC_BEZ_MODELI=os.environ.get('KC_EC_BEZ_MODELI', '1'),
                              KC_LIMIT_MIN='25', KC_POTOKOV=os.environ.get('KC_POTOKOV', '48'), KC_AGENT_XML_MIN='60',
                              PILOT_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna',
                              PILOT_S_SHAGA=os.environ.get('PILOT_S_SHAGA', '0')))
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
