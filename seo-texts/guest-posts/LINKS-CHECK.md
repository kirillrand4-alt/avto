# Проверка оплаченных ссылок волны

Проверено 24 уникальных URL, на них ведут 31 ссылок из 24 статей. Проверялось: код ответа, редиректы, canonical, запрет индексации, соответствие страницы якорю.

**Итог: 22 из 24 чисто. Ни одного редиректа, ни одного чужого canonical, ни одной
страницы, закрытой от индексации. Каждый якорь соответствует H1 своей страницы.**

Две страницы отдают мне код 403 со страницей «Проверка браузера» — это WAF сайта против
датацентровых адресов, а не поломка. **Владелец проверил обе в Search Console 20.08:
«URL есть в индексе Google», «Эта страница проиндексирована», 20 элементов товаров
с микроразметкой.** То есть Googlebot получает настоящую страницу; проверить их снаружи
скриптом нельзя, и это нормально.

| URL | Статус | H1 страницы | Якоря, которые туда ведут |
|---|---|---|---|
| `abac-kompressor.ru/catalog/vintovye-kompressory/` | ок | Винтовые компрессоры | «винтовых компрессоров из Италии» — `vybor-vintovogo-kompressora-dlya-p`<br>«Итальянские винтовые компрессоры» — `kompressory-dlya-avtoservisa-vybor` |
| `ac-kompressor.ru/catalog/vintovye-kompressory/` | ок | Винтовые компрессоры Atlas Copco | «винтовой компрессор Atlas Copco» — `vintovye-kompressory-dlya-proizvod` |
| `ac-kompressor.ru/catalog/xas/` | ок | Дизельные передвижные компрессоры Atlas Copc | «дизельные компрессоры Atlas Copco XAS» — `dizelnye-peredvizhnye-kompressory-` |
| `berg-compressor.com/catalog/kompressory-s-pryamym-privodom/` | ок | Винтовые компрессоры BERG с прямым приводом | «компрессоры BERG» — `ot-peska-do-rtx-kak-proizvodyat-vi` |
| `berg-compressor.com/catalog/kompressory-s-resiverom-i-osushitelem/` | ок | Винтовые компрессоры BERG с ресивером и осуш | «винтовые компрессоры с осушителем» — `kompressor-dlya-pokrasochnogo-ucha`<br>«Винтовой компрессор с осушителем воздуха» — `kompressor-s-osushitelem-dlya-mont` |
| `berg-compressor.com/catalog/vintovye-kompressory/` | ок | Винтовые компрессоры BERG | «винтовые компрессоры BERG» — `kompressor-dlya-pokrasochnogo-ucha`<br>«BERG» — `krymskie-predpriyatiya-rossijskoe-` |
| `dali-kompressor.ru/catalog/ca/` | ок | Компрессоры Cross Air серии СА | «винтовые компрессоры CrossAir» — `podbor-vintovogo-kompressora-dlya-` |
| `dali-kompressor.ru/catalog/osushiteli/` | ок | Осушители воздуха Dali - адсорбционные и реф | «осушители воздуха» — `podbor-vintovogo-kompressora-dlya-` |
| `enger-air.ru/catalog/azotnye-ustanovki/generatory_azota/` | ок | Азотные установки | «генератор азота» — `azotnyye-generatory-princip-raboty` |
| `enger-air.ru/catalog/azotnye-ustanovki/membrannie/` | ок | Мембранные генераторы азота | «Мембранные азотные установки» — `azotnyye-generatory-princip-raboty` |
| `enger-air.ru/catalog/bezmaslyanye_kompressory/` | ок | Безмасляные компрессоры | «безмасляных компрессоров» — `oilless-compressors-plastic-produc` |
| `enger-air.ru/catalog/mks/` | ок | Модульная компрессорная станция – компрессор | «модульную компрессорную станцию МКС» — `modulnye-kompressornye-stantsii-vs` |
| `enger-air.ru/catalog/vintovye_kompressory/` | ок | Винтовые компрессоры | «промышленного винтового компрессора» — `modulnye-kompressornye-stantsii-vs`<br>«промышленные винтовые компрессоры» — `oilless-compressors-plastic-produc` |
| `prokompressor.ru/catalog/azotnye-stantsii/` | ок | Азотные станции и установки | «станции получения азота» — `azotnye-stantsii-v-metallurgii` |
| `prokompressor.ru/catalog/kislorodnye-stantsii/` | ок | Кислородные станции и установки | «кислородные станции» — `vysokogornye-oteli-kislorod-dlya-t` |
| `prokompressor.ru/catalog/kompressornye-stantsii-szhatogo-vozdukha/mks/` | ок | Модульные компрессорные станции | «Модульные компрессорные станции» — `vozdukhosnabzhenie-ochistnykh-soor` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/atlas-copco/` | ⚠ код 403 | Проверка браузера | «компрессоры Atlas Copco» — `kak-delayut-veshchi-udivitelnye-fa` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-naznacheniyu/dlya-tsekha/` | ок | Промышленные компрессоры для цеха | «промышленные компрессоры» — `szhatyy-vozdukh-ubivaet`<br>«компрессоры для производства» — `kak-delayut-metallicheskuyu-mebel-` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/tsentrobezhnye/` | ок | Центробежные компрессоры | «Центробежные компрессоры» — `vozdukhosnabzhenie-ochistnykh-soor` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/` | ок | Винтовые воздушные компрессоры | «винтовых компрессоров» — `vybor-vintovogo-kompressora-dlya-t`<br>«промышленный винтовой компрессор» — `rabota-na-proizvodstve-vostrebovan` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/dizelnye/` | ок | Дизельные винтовые компрессоры | «дизельные винтовые компрессоры» — `den-mashinostroitelya-oborudovanie` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/` | ок | Электрические винтовые компрессоры | «электрических винтовых компрессоров» — `vybor-vintovogo-kompressora-dlya-t` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/po-tipu/vysokogo-davleniya/` | ок | Компрессоры высокого давления | «промышленные компрессоры высокого давления» — `ral-industrial-color-system-for-de` |
| `prokompressor.ru/catalog/vozdushnye-kompressory/promyshlennye/` | ⚠ код 403 | Проверка браузера | «Компрессор промышленный» — `tsitaty-o-masterstve-i-professiona`<br>«производственные компрессоры» — `stars-before-fame-jobs` |

## Как перепроверить

```bash
cd seo-texts/guest-posts
JOBS_MODULE=wave-jobs python3 -c "
from gen_wave import JOBS
for j in JOBS:
    for u,_ in j['links']: print(u)" | sort -u | while read u; do
  printf '%s  %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{num_redirects}' -L --max-time 20 "$u")" "$u"
done
```

Две страницы prokompressor.ru при такой проверке всегда покажут 403 — см. выше.
