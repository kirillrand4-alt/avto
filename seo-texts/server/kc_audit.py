# -*- coding: utf-8 -*-
r"""База КЦ, проверка «нет ли лишнего» (владелец 07.10: «номера только с сайта компании или закупок?
нет лишнего?»).

  1. Чей сайт: ИНН компании на страницах обхода, иначе ядро названия в тексте (kc_sayty.чей_сайт).
     Сайт без ИНН и без названия — номера с него не берём.
  2. Каждый номер с сайта, которому модель ещё не сказала «чей» (номера без подписи), — модель по
     фрагменту страницы: номер этой компании или чужой (дилер, дистрибьютор, другой завод группы,
     магазин-партнёр, горячая линия ведомства, разработчик сайта).
Выход (fsync): C:\sender\server\kc-audit.jsonl -> копия на дроп.
"""
import io
import json
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import kc_sayty as KS  # noqa: E402

ВЫХОД = os.path.join(DIR, 'kc-audit.jsonl')
_лок = threading.Lock()
ПРОМПТ = (
    'Компания «{имя}» (ИНН {инн}), её сайт {сайт}. На сайте найдены номера; для каждого — фрагмент текста '
    'страницы вокруг номера.\n{номера}\n\n'
    'Для КАЖДОГО номера реши: «эта» — номер самой компании «{имя}» (её офис, завод, отдел, сотрудник, общий '
    'номер сайта, горячая линия компании); «чужой» — номер другой организации: дилер, дистрибьютор, торговый '
    'партнёр, магазин, другое предприятие/филиал группы в другом городе, госорган или горячая линия ведомства '
    '(Роспотребнадзор, ФНС и т.п.), разработчик сайта, банк. Если по фрагменту не понять — «эта».\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер_в_списке,"чей":"эта|чужой","кто":"до 8 слов: чей номер"}}]')


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def хост(u):
    u = re.sub(r'^[a-z]+://', '', (u or '').strip().lower()).split('/')[0]
    return u[4:] if u.startswith('www.') else u


def одна(к, з):
    out = {'inn': к['inn'], 'сайт': з['сайт']}
    out['сайт_чей'] = KS.чей_сайт(к, з)
    без = [н for н in з.get('номера', []) if н.get('чей') not in ('эта', 'другая')]
    ответ = {}
    for k in range(0, len(без), 25):
        кусок = без[k:k + 25]
        список = '\n'.join('%d. %s%s — «…%s…»' % (j + 1, н['номер'], (' доб. ' + н['доб']) if н['доб'] else '',
                                                 (н.get('контекст') or '')[-260:]) for j, н in enumerate(кусок))
        r = KK.модель(ПРОМПТ.format(имя=к['имя'], инн=к['inn'], сайт=з['сайт'], номера=список), True)
        for j, н in enumerate(кусок):
            x = r.get(j + 1) or {}
            ответ[н['номер'] + '|' + н['доб']] = {'чей': x.get('чей') if x.get('чей') in ('эта', 'чужой') else '',
                                                 'кто': (x.get('кто') or '')[:80]}
    out['номера'] = ответ
    out['итог'] = 'ok'
    записать(out)


def main():
    сп = json.load(io.open(os.path.join(DIR, 'kc-spisok.json'), encoding='utf-8'))['компании']
    конт = {}
    for s in io.open(os.path.join(DIR, 'kc-kontakty.jsonl'), encoding='utf-8', errors='replace'):
        з = json.loads(s)
        if з.get('итог') == 'ok':
            конт[з['inn']] = з
    if os.path.exists(ВЫХОД):
        os.remove(ВЫХОД)
    задачи = [(к, конт[i]) for i, к in сп.items()
              if i in конт and конт[i].get('сайт') and хост(конт[i]['сайт']) == хост(к['сайт'])]
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda x: одна(*x), задачи))
    shutil.copyfile(ВЫХОД, r'C:\seostat\drop\drop-storage\kc-audit.jsonl')
    сч = {'компаний': len(задачи), 'сайт': {}, 'номера': {}}
    for s in io.open(ВЫХОД, encoding='utf-8'):
        з = json.loads(s)
        к = з['сайт_чей'].split(':')[0]
        сч['сайт'][к] = сч['сайт'].get(к, 0) + 1
        for v in з['номера'].values():
            сч['номера'][v['чей'] or '?'] = сч['номера'].get(v['чей'] or '?', 0) + 1
    print('===ИТОГ===')
    print(json.dumps(сч, ensure_ascii=False))


if __name__ == '__main__':
    main()
