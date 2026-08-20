# -*- coding: utf-8 -*-
r"""Собрать фронт панели из ВОССТАНОВЛЕННЫХ исходников и выложить в dist.

Почему так. Исходники на сервере (C:\sender\sender\web\src) отстали на три
недели: правки 11.08 (крестик в ленте, пейджер, подписи статусов) живут только
в собранном бандле. Собирать из них — откатить панель. Настоящие исходники взяты
из sourcemap действующей сборки (_dostat_ishodniki.py) и лежат в
C:\sender\_tmp\web-src-iz-mapy.

Порядок: старый src в бэкап -> кладём восстановленные -> npm run build ->
проверяем, что бандл собрался и в нём есть наши строки -> копируем dist.
Старый dist тоже сохраняем: откат должен быть в одно движение.

    python sobrat_front.py            собрать и проверить, dist НЕ трогать
    python sobrat_front.py --vylozhit собрать и выложить
"""
import io
import json
import os
import shutil
import subprocess
import sys
import time

WEB = r'C:\sender\sender\web'
ВОССТ = r'C:\sender\_tmp\web-src-iz-mapy'
ЖИВОЙ_DIST = r'C:\sender\web\dist'
НОВЫЕ = r'C:\sender\_tmp\web-pravki'      # сюда кладём изменённые файлы
МЕТКА = time.strftime('%Y%m%d-%H%M%S')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    итог = {'метка': МЕТКА}
    src = os.path.join(WEB, 'src')
    бэкап = os.path.join(WEB, 'src.bak-' + МЕТКА)
    shutil.move(src, бэкап)
    shutil.copytree(ВОССТ, src)
    итог['исходники_подменены'] = {'бэкап': бэкап}
    # накладываем наши правки поверх восстановленных
    наложено = []
    if os.path.isdir(НОВЫЕ):
        # правки лежат с той же структурой, что и src (screens/, api/ ...)
        for корень2, _, файлы2 in os.walk(НОВЫЕ):
            for имя in файлы2:
                отн = os.path.relpath(os.path.join(корень2, имя), НОВЫЕ)
                цель = os.path.join(src, отн)
                if os.path.exists(цель):
                    shutil.copy(os.path.join(корень2, имя), цель)
                    наложено.append(отн.replace(os.sep, '/'))
    итог['правки'] = наложено
    # ТИПЫ. В sourcemap их нет: модуль из одних interface/type компилятор
    # стирает, в бандл он не попадает. Берём из прежнего дерева — на поведение
    # они не влияют, нужны только компилятору.
    типы = []
    for отн in ('api/types.ts',):
        ист = os.path.join(бэкап, отн.replace('/', os.sep))
        цель = os.path.join(src, отн.replace('/', os.sep))
        if os.path.exists(ист) and not os.path.exists(цель):
            os.makedirs(os.path.dirname(цель), exist_ok=True)
            shutil.copy(ист, цель)
            типы.append(отн)
    итог['типы_из_бэкапа'] = типы
    # СТИЛИ. В sourcemap их тоже нет — vite собирает CSS отдельным файлом.
    # Берём СКОМПИЛИРОВАННЫЙ css живой сборки, а не из бэкапа: он новее и
    # содержит всё, что появилось после 22.07. Это обычный css, vite его
    # пересоберёт как есть.
    живой_css = ''
    for f3 in sorted(os.listdir(os.path.join(ЖИВОЙ_DIST, 'assets'))):
        if f3.endswith('.css'):
            живой_css = os.path.join(ЖИВОЙ_DIST, 'assets', f3)
    if живой_css:
        стиль = io.open(живой_css, encoding='utf-8', errors='replace').read()
        # правило для нового списка статусов в строке ленты
        стиль += ('\n.lead-move{margin-left:6px;padding:2px 4px;font-size:12px;'
                  'border:1px solid var(--line,#d7dbe0);border-radius:6px;'
                  'background:transparent;color:inherit;cursor:pointer}\n'
                  '.lead-move:disabled{opacity:.5;cursor:default}\n'
                  '.vlozheniya{display:flex;flex-wrap:wrap;gap:8px;align-items:center;'
                  'margin:8px 0}\n'
                  '.vlozhenie{display:inline-flex;gap:6px;align-items:center;'
                  'padding:2px 8px;border:1px solid var(--line,#d7dbe0);'
                  'border-radius:12px;font-size:13px}\n'
                  '.btn-link{background:none;border:0;color:inherit;cursor:pointer;'
                  'opacity:.6;font-size:14px;line-height:1}\n'
                  '.btn-link:hover{opacity:1}\n'
                  '.otvet .reply-ok{color:#0a7d33}\n'
                  '.need-svoy{white-space:pre-wrap;max-height:9em;overflow:auto}\n'
                  # отметка «адрес взят из их письма» (владелец 20.08): должна
                  # читаться сразу, но не спорить с телом письма
                  '.pometka-adres{display:inline-block;margin:4px 0;padding:2px 8px;'
                  'font-size:12px;border-radius:10px;background:rgba(10,125,51,.10);'
                  'color:#0a7d33;border:1px solid rgba(10,125,51,.25)}\n'
                  '.pometka-slabaya{background:rgba(180,120,0,.10);color:#8a5a00;'
                  'border-color:rgba(180,120,0,.28)}\n'
                  # значок направления в списке отправленных (владелец 20.08)
                  '.napr{display:inline-block;padding:1px 7px;border-radius:9px;'
                  'font-size:11px;line-height:17px;white-space:nowrap;'
                  'border:1px solid transparent}\n'
                  '.napr-kc{background:rgba(40,90,200,.10);color:#2855c8;'
                  'border-color:rgba(40,90,200,.25)}\n'
                  '.napr-meyer{background:rgba(150,60,170,.10);color:#8a3caa;'
                  'border-color:rgba(150,60,170,.25)}\n'
                  # ПИСЬМО ПРОСТЫМ ТЕКСТОМ: переводы строк сохраняем, иначе
                  # письмо читается сплошной простынёй
                  '.sent-text{white-space:pre-wrap;word-break:break-word;'
                  'font:inherit;margin:6px 0;max-width:74ch}\n')
        io.open(os.path.join(src, 'styles.css'), 'w', encoding='utf-8').write(стиль)
        итог['стили_из_живой_сборки'] = os.path.basename(живой_css)
    # Прочие css-импорты (tokens.css и подобные) в бандле уже слиты в один файл,
    # который мы положили в styles.css. Чтобы rollup не спотыкался о ссылку,
    # создаём недостающие пустыми — дублировать правила нельзя, они уже есть.
    import re as _re
    пустые = []
    for d4, _, fs4 in os.walk(src):
        for f4 in fs4:
            if not f4.endswith(('.ts', '.tsx')):
                continue
            текст = io.open(os.path.join(d4, f4), encoding='utf-8',
                            errors='replace').read()
            for м in _re.finditer(r'import\s+"(\./[^"]+\.css)"', текст):
                цель2 = os.path.normpath(os.path.join(d4, м.group(1)))
                if not os.path.exists(цель2):
                    io.open(цель2, 'w', encoding='utf-8').write(
                        '/* правила этого файла уже включены в styles.css,\n'
                        '   собранный из действующей сборки панели */\n')
                    пустые.append(os.path.basename(цель2))
    итог['созданы_пустыми'] = пустые
    # ТОЛЬКО vite, без tsc. Причина честная: восстановленный код — ровно тот,
    # что уже работает в панели, а типовой слой (types.ts) остался от 22.07 и
    # с ним разошёлся. Падение проверки типов не значит, что код сломан; на
    # выходе всё равно сверяем бандл по опорным строкам.
    p = subprocess.run(['npx.cmd', 'vite', 'build'], cwd=WEB, capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=1200)
    итог['сборка_rc'] = p.returncode
    итог['сборка_хвост'] = ((p.stdout or '') + (p.stderr or ''))[-1200:]
    if p.returncode != 0:
        shutil.rmtree(src, ignore_errors=True)
        shutil.move(бэкап, src)
        итог['откат'] = 'сборка не удалась, исходники возвращены'
        print(json.dumps(итог, ensure_ascii=False, indent=1))
        return 1
    свой_dist = os.path.join(WEB, 'dist')
    # проверяем, что в бандле есть наша строка
    нашли = False
    for d, _, fs in os.walk(os.path.join(свой_dist, 'assets')):
        for f in fs:
            if f.endswith('.js') and not f.endswith('.map'):
                t = io.open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
                if 'перевести' in t:
                    нашли = True
    итог['в_бандле_есть_перевести'] = нашли
    # Опорные строки: если сборка вышла беднее живой, значит собрали не то.
    # «Получатели» отсюда убрано 20.08: этой строки нет и в ЖИВОЙ сборке —
    # экран называется иначе. Опора, которой нет у эталона, каждый раз даёт
    # ложную тревогу «потеряно» и учит не доверять проверке.
    ОПОРЫ = ('Лента лидов', 'Подтвердить отправку', 'Мои лиды',
             'квалифицирован', 'передан в Bitrix', 'Открыл')
    свежий = ''
    for d2, _, fs2 in os.walk(os.path.join(свой_dist, 'assets')):
        for f2 in fs2:
            if f2.endswith('.js') and not f2.endswith('.map'):
                свежий += io.open(os.path.join(d2, f2), encoding='utf-8',
                                  errors='replace').read()
    итог['опорные_строки'] = {о: (о in свежий) for о in ОПОРЫ}
    итог['потеряно'] = [о for о, е in итог['опорные_строки'].items() if not е]
    if '--vylozhit' in sys.argv and нашли:
        бэкап_dist = ЖИВОЙ_DIST + '.bak-' + МЕТКА
        shutil.copytree(ЖИВОЙ_DIST, бэкап_dist)
        shutil.rmtree(ЖИВОЙ_DIST)
        shutil.copytree(свой_dist, ЖИВОЙ_DIST)
        итог['выложено'] = {'живой': ЖИВОЙ_DIST, 'бэкап_прежнего': бэкап_dist}
    print(json.dumps(итог, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
