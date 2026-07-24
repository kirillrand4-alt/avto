# Ранбук: nginx-редиректор доменов-двойников (вариант А)

Цель: все 14 доменов из `../config/domains.json` отдают **301 → https://целевой-сайт**
(КЦ → prokompressor.ru, Meyer → meyer-corp.ru / vsefotoseparatory.ru) и по http, и по
https. Конфиг уже сгенерирован: `redirects-nginx.conf` (перегенерация —
`python3 sender/tools/gen_redirects_nginx.py`).

Почта (MX/SPF/DKIM/DMARC) этим НЕ затрагивается: редиректор живёт только на
A-записях. Делать можно в любой момент, независимо от правок DMARC.

## Что нужно

- Linux-сервер с белым IPv4 и открытыми портами **80 и 443** (подойдёт тот же,
  где панель сендера, или parsercompressor.online). root/sudo.
- IP сервера: `curl -4 ifconfig.me` (или из ЛК хостера).
- Windows-сервер тоже возможен (nginx for Windows + win-acme), но проще
  разместить редиректор на Linux-машине.

## ⚡ Быстрый путь: одной командой (`setup-redirects.sh`)

Вся серверная часть (шаги 2-5 ниже) упакована в идемпотентный установщик
`setup-redirects.sh`. Руками остаётся ТОЛЬКО шаг 1 (A-записи у регистраторов).

```bash
# 1) скопировать на сервер ДВА файла из sender/deploy/:
scp seo-texts/sender/deploy/setup-redirects.sh \
    seo-texts/sender/deploy/redirects-nginx.conf user@SERVER:/tmp/
# (или через дроп: drop_client.sh up + скачать на сервере curl-ом)

# 2) запустить:
ssh user@SERVER
cd /tmp && sudo bash setup-redirects.sh
```

Что делает: ставит nginx+certbot (если нет) → кладёт конфиг (443 выключен до
серта) → поднимает http-301 → открывает 80/443 в ufw → DNS-preflight (какие
домены уже смотрят на сервер) → выпускает Let's Encrypt ТОЛЬКО на доехавшие →
включает https → ставит хук автопродления. Чужие сайты на сервере не трогает.

Домены «не доехали» в DNS? Не страшно: скрипт выпустит серт на готовые, а когда
A-записи доедут — **просто перезапустить его же**, он до-выпустит остальные
(`--expand`). Email для Let's Encrypt можно задать: `LE_EMAIL=you@mail sudo -E bash setup-redirects.sh`.

Шаги 2-5 ниже — тот же процесс вручную (для понимания/отладки).

## Шаг 1. A-записи у всех 14 доменов → IP сервера

В DNS-редакторе каждого регистратора добавить/заменить:

```
A    @      <IP сервера>
A    www    <IP сервера>
```

⚠️ Трогать ТОЛЬКО записи A (и AAAA — удалить, если сервер без IPv6).
MX, TXT (SPF, DKIM, verification, DMARC), CNAME почты — НЕ трогать.

Где лежит редактор зоны (названия пунктов могут немного отличаться):

- **RU-CENTER (3 домена)**: nic.ru → «Услуги» → DNS-хостинг → зона домена →
  добавить записи (сейчас зона пустая — просто добавить A @ и www).
- **Beget (4)**: панель → «Домены и поддомены» → домен → «Записи DNS/DNS» →
  ЗАМЕНИТЬ текущую A (45.130.41.238 — заглушка хостинга) на IP сервера.
  Если панель предупредит «сайт перестанет открываться с хостинга» — это
  ожидаемо, сайт нам и не нужен.
- **REG.RU (4)**: ЛК → домен → «DNS-серверы и управление зоной» → добавить
  A @ и www (сейчас A нет вовсе).
- **Timeweb (3)**: панель → «Домены и поддомены» → домен → настройки DNS →
  ЗАМЕНИТЬ парковочную A (92.53.96.223) на IP сервера.

Распространение обычно минуты, максимум пару часов. Проверить не отходя:
`curl -sS "https://dns.google/resolve?name=kompressor-trade.ru&type=A"` —
в ответе должен быть IP сервера. Либо `python3 sender/tools/check_domains.py` —
у доменов появится ваша A.

## Шаг 2. nginx на сервере

```bash
sudo apt update && sudo apt install -y nginx          # если ещё не стоит
sudo mkdir -p /var/www/acme                           # webroot для Let's Encrypt
```

Скопировать `redirects-nginx.conf` на сервер:

```bash
# с машины, где клонирован репозиторий:
scp seo-texts/sender/deploy/redirects-nginx.conf user@SERVER:/tmp/
sudo mv /tmp/redirects-nginx.conf /etc/nginx/conf.d/redirects.conf
```

(альтернатива — через дроп: `bash seo-texts/server/drop_client.sh up ...` и
скачать на сервере curl-ом с `X-Drop-Token`).

**Пока сертификата нет — закомментировать весь блок `server { listen 443 ... }`**
в конце файла (иначе `nginx -t` упадёт на отсутствующих файлах серта):

```bash
sudo nano /etc/nginx/conf.d/redirects.conf   # блок 443 → закомментировать
sudo nginx -t && sudo systemctl reload nginx
```

Проверка http-половины (домен должен уже смотреть на сервер, шаг 1):

```bash
curl -I http://kompressor-trade.ru/
# HTTP/1.1 301 Moved Permanently
# Location: https://prokompressor.ru/
```

Если на сервере уже крутятся другие сайты (например, дроп на
parsercompressor.online) — конфликта нет: наши `server_name` перечислены явно
и чужие хосты не перехватывают. Единственное — если 80-й порт занят другим
веб-сервером (не nginx), редиректор надо ставить туда, где nginx главный.

## Шаг 3. Сертификат Let's Encrypt (один на все 28 имён)

```bash
sudo apt install -y certbot
```

К этому моменту **все** A-записи должны уже указывать на сервер — Let's Encrypt
ходит на `http://домен/.well-known/acme-challenge/` каждого имени. Готовая
команда лежит в шапке `redirects-nginx.conf` (certonly --webroot -w /var/www/acme
-d … все 14 доменов + www). Скопировать и выполнить с sudo.

- Какой-то домен ещё «не доехал» → либо подождать DNS, либо временно убрать его
  `-d` из команды, а после доезда добавить: та же команда + `--expand`.
- Проверка: `sudo certbot certificates` — сертификат
  `compressor-pro-systems.ru` с 28 Domains и датой Expiry.

## Шаг 4. Включить https-половину

```bash
sudo nano /etc/nginx/conf.d/redirects.conf   # раскомментировать блок 443
sudo nginx -t && sudo systemctl reload nginx
curl -I https://kompressor-trade.ru/         # 301 → https://prokompressor.ru/
```

## Шаг 5. Автопродление

Пакетный certbot ставит таймер сам: `systemctl list-timers | grep certbot`.
Добавить перезагрузку nginx после продления:

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo certbot renew --dry-run       # репетиция продления, должно пройти чисто
```

## Шаг 6. Финальная проверка

```bash
python3 sender/tools/check_domains.py
```

У всех 14 доменов должна исчезнуть претензия к редиректу (остальные пункты —
DMARC, пустые RU-CENTER, лишний MX kompressor-expert.ru — закрываются по
чек-листу `../DOMAINS-SETUP.md`).

## Траблшутинг

| Симптом | Причина / лечение |
|---|---|
| `nginx -t`: cannot load certificate | блок 443 раскомментирован до выпуска серта → закомментировать, выпустить серт (шаг 3), вернуть |
| certbot: Invalid response / NXDOMAIN | A-запись домена ещё не доехала или не создана → проверить через dns.google, подождать |
| certbot: Timeout during connect | порт 80 закрыт фаерволом → `sudo ufw allow 80,443/tcp` и/или фаервол в ЛК хостера |
| curl: Connection refused | nginx не слушает 80 (не перезагружен) или фаервол |
| nginx warning: conflicting server name | домен уже упомянут в другом conf-файле → убрать дубль |
| Beget/Timeweb всё ещё кажет заглушку | DNS-кэш, подождать TTL; проверить, что A реально заменили, а не добавили вторую |
| https ругается на серт у одного домена | имени нет в серте (пропустили `-d`) → повторить certbot с `--expand` |

## Добавление нового домена потом

1. Внести в `sender/config/domains.json`.
2. `python3 sender/tools/gen_redirects_nginx.py > sender/deploy/redirects-nginx.conf`,
   залить на сервер, `nginx -t && reload` (nginx стерпит имя без серта на 443,
   но https заработает только после шага 3).
3. A-записи домена → сервер; certbot-команду из шапки + `--expand`.
4. `check_domains.py` — убедиться.
