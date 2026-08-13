// Кубик ZennoPoster 7.9: обход САЙТА, а не одной главной.
//
// Зачем: дельфин поднимает профиль на КАЖДУЮ страницу (10-30 с на страницу) и по факту
// доходит только до главной — внутренние адреса конвейер берёт по ссылкам с неё, и каждый
// снова идёт через всю цепочку фолбэков. Зенка держит один инстанс и может пройти по
// сайту сама: главная -> контакты -> о компании -> руководство. Замер 12.08: 100 адресов
// за 9,7 с каждый, то есть 4 страницы на сайт обойдутся примерно за 25-40 с против
// нескольких минут у дельфина.
//
// Ограничения 7.9, проверены на этом сервере (не менять на «привычное»):
//   * LoadProfile и DocumentText НЕ работают -> HTML берём через FindElementByTag("html",0)
//     и GetAttribute("outerhtml");
//   * общий замок для списков — SyncObjects.ListSyncer;
//   * в лог числа пишутся с запятой (24,9) — парсер результата это учитывает.
//
// НАСТРАИВАТЬ В ПРОЕКТЕ НИЧЕГО НЕ НАДО (владелец 13.08: «чтобы сам создал нужные файлы
// и переменные»). Кубик сам создаёт папки, сам берёт задание из файла очереди и сам
// подхватывает прокси. Списки и переменные проекта используются, ТОЛЬКО если они уже
// заведены, — иначе берутся значения по умолчанию. От оператора требуется одно:
// поставить число потоков и включить повтор выполнения.
//
// ПАПКА ОБМЕНА (создаётся сама): C:\seostat\drop\zenno
//   ochered.txt   — очередь заданий «ИНН;адрес», её наполняет zenno_most.py --ochered
//   proxy.txt     — прокси построчно, необязателен (нет файла -> идём напрямую)
//   gotovo\       — сюда кладём результат, эту папку слушает zenno_most.py --priyom
//   ne_otkrylis.txt — сайты, которые не дались даже Зенке (для разбора, не для повтора)
//
// ВЫХОД (на компанию):
//   <ИНН>_0.html, <ИНН>_1.html ...  — сырой HTML каждой открытой страницы
//   <ИНН>.urls.txt                  — адреса в том же порядке, по строке на файл
//   <ИНН>.err.txt                   — если что-то не открылось: адрес и причина
// JSON намеренно не собираем: экранировать HTML в C# руками — источник битых файлов.

// --- пути и настройки: переменная проекта, если заведена, иначе умолчание ---
Func<string, string, string> nastroyka = delegate(string imya, string po_umolchaniyu)
{
    try
    {
        string v = project.Variables[imya].Value;
        if (!string.IsNullOrEmpty(v)) return v;
    }
    catch { }        // переменной в проекте нет — это штатный случай, не ошибка
    return po_umolchaniyu;
};

string koren_obmena = nastroyka("papka_obmena", @"C:\seostat\drop\zenno");
string papka = nastroyka("papka_vyhod", System.IO.Path.Combine(koren_obmena, "gotovo"));
string fajl_ocheredi = nastroyka("fajl_ocheredi",
                                 System.IO.Path.Combine(koren_obmena, "ochered.txt"));
string fajl_proxy = nastroyka("fajl_proxy",
                              System.IO.Path.Combine(koren_obmena, "proxy.txt"));
System.IO.Directory.CreateDirectory(koren_obmena);
System.IO.Directory.CreateDirectory(papka);
if (!System.IO.File.Exists(fajl_ocheredi))
    System.IO.File.WriteAllText(fajl_ocheredi, "", System.Text.Encoding.UTF8);

int predel = 3;
if (!int.TryParse(nastroyka("stranic_max", "3"), out predel) || predel <= 0) predel = 3;

// --- задание: сначала список проекта (если оператор его завёл), иначе файл очереди ---
// Строку ЗАБИРАЕМ из файла целиком под общим замком: два потока не должны получить
// одну компанию. Читаем всё, берём первую, остальное пишем обратно — на очереди в
// десятки тысяч строк это дешевле любых блокировок по смещению.
string stroka = "";
lock (SyncObjects.ListSyncer)
{
    bool vzyato_iz_spiska = false;
    try
    {
        if (project.Lists["sajty"].Count > 0)
        {
            stroka = project.Lists["sajty"][0];
            project.Lists["sajty"].RemoveAt(0);
            vzyato_iz_spiska = true;
        }
    }
    catch { }        // списка sajty в проекте нет — работаем прямо с файлом
    if (!vzyato_iz_spiska)
    {
        try
        {
            var vse = System.IO.File.ReadAllLines(fajl_ocheredi, System.Text.Encoding.UTF8);
            int pervaya = -1;
            for (int i = 0; i < vse.Length; i++)
            {
                if (vse[i].Trim().Length > 0) { pervaya = i; break; }
            }
            if (pervaya >= 0)
            {
                stroka = vse[pervaya].Trim();
                var ostatok = new List<string>();
                for (int i = 0; i < vse.Length; i++)
                {
                    if (i != pervaya && vse[i].Trim().Length > 0) ostatok.Add(vse[i]);
                }
                System.IO.File.WriteAllLines(fajl_ocheredi, ostatok.ToArray(),
                                             System.Text.Encoding.UTF8);
            }
        }
        catch (Exception e)
        {
            project.SendWarningToLog("очередь недоступна: " + e.Message, true);
        }
    }
}
if (stroka.Length == 0)
{
    project.SendInfoToLog("очередь пуста — поток завершён", true);
    return -1;
}

var chasti = stroka.Split(';');
string inn = chasti[0].Trim();
string url = (chasti.Length > 1 ? chasti[1] : chasti[0]).Trim();
if (url.Length == 0) return -1;
if (!url.StartsWith("http")) url = "http://" + url;

// --- прокси: список проекта, иначе файл; пусто -> идём напрямую ---
string proxy = "";
lock (SyncObjects.ListSyncer)
{
    try
    {
        if (project.Lists["proxy"].Count > 0)
        {
            proxy = project.Lists["proxy"][0].Trim();
            project.Lists["proxy"].RemoveAt(0);
            project.Lists["proxy"].Add(proxy);      // по кругу
        }
    }
    catch { }
    if (proxy.Length == 0 && System.IO.File.Exists(fajl_proxy))
    {
        try
        {
            var pl = new List<string>();
            foreach (string s in System.IO.File.ReadAllLines(fajl_proxy))
                if (s.Trim().Length > 0) pl.Add(s.Trim());
            if (pl.Count > 0)
            {
                // разные потоки должны брать разные адреса, общего счётчика нет —
                // выбираем по случайному числу, засеянному уникальным Guid
                int i = new Random(Guid.NewGuid().GetHashCode()).Next(pl.Count);
                proxy = pl[i];
            }
        }
        catch { }
    }
}
if (proxy.Length > 0) instance.SetProxy(proxy);

instance.ClearCookie();
instance.ClearCache();

var oshibki = new System.Text.StringBuilder();

// Открыть адрес и вернуть HTML. Пустая строка = не открылось (причина ушла в лог и в .err).
Func<string, string> vzyat = delegate(string adres)
{
    try
    {
        instance.ActiveTab.Navigate(adres, "");
        instance.ActiveTab.WaitDownloading();
        var he = instance.ActiveTab.FindElementByTag("html", 0);
        if (he == null || he.IsVoid)
        {
            oshibki.AppendLine(adres + " -> пустой документ");
            return "";
        }
        return he.GetAttribute("outerhtml");
    }
    catch (Exception e)
    {
        oshibki.AppendLine(adres + " -> " + e.Message);
        project.SendWarningToLog(inn + " " + adres + ": " + e.Message, true);
        return "";
    }
};

var adresa = new List<string>();
var htmly = new List<string>();

// Карта сайта. Зенка нужна ровно там, где питон сайт не берёт, — значит и robots.txt
// с sitemap.xml он тоже не возьмёт, и добывать их надо здесь же, браузером. Замер 13.08:
// карта есть у 72% доменов, robots.txt называет её у 66%, включая 11 нетиповых путей.
Func<string, List<string>> iz_karty = delegate(string domen)
{
    var naydeno = new List<string>();
    var karty = new List<string>();
    string rob = vzyat(domen + "/robots.txt");
    if (rob.Length > 0)
    {
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(
                     rob, "Sitemap:\\s*(\\S+)",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string s = m.Groups[1].Value.Trim();
            if (s.StartsWith("http") && !karty.Contains(s)) karty.Add(s);
        }
    }
    if (karty.Count == 0) karty.Add(domen + "/sitemap.xml");

    var slova_k = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                                 "o-nas", "rukovod", "staff", "team", "sotrudnik" };
    int razobrano = 0;
    for (int k = 0; k < karty.Count && razobrano < 4 && naydeno.Count < 6; k++)
    {
        string xml = vzyat(karty[k]);
        razobrano++;
        if (xml.Length == 0) continue;
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(xml, "<loc>([^<]{1,300})</loc>",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string loc = m.Groups[1].Value.Trim();
            string nl = loc.ToLower();
            // карта карт: вложенные sitemap разбираем тоже, но не больше четырёх штук
            if (nl.EndsWith(".xml") && !karty.Contains(loc) && karty.Count < 6)
            {
                karty.Add(loc);
                continue;
            }
            bool nuzhna = false;
            foreach (string s in slova_k) { if (nl.Contains(s)) { nuzhna = true; break; } }
            if (nuzhna && !naydeno.Contains(loc) && naydeno.Count < 6) naydeno.Add(loc);
        }
    }
    return naydeno;
};

// Типовые пути — только если своих контактных ссылок не нашлось. Их на сайте обычно
// нет вовсе, поэтому проверяем последними и без фанатизма (питон здесь делает «лёгкий
// заход» по той же причине: угадки — самая дорогая часть обхода).
var ugadki = new string[] { "/contacts/", "/kontakty/", "/contact/", "/about/",
                            "/o-kompanii/", "/company/staff/", "/company/", "/rukovodstvo/" };

string glavnaya = vzyat(url);
if (glavnaya.Length > 0)
{
    adresa.Add(url);
    htmly.Add(glavnaya);

    // ссылки на страницы, где живут контакты. Порядок важен: по замеру окупаемости
    // (13.08) страница контактов даёт 853 адреса из 2157, «о компании» — 289,
    // руководство — 25. Поэтому сперва контакты, потом остальное.
    var slova = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                               "o-nas", "company", "rukovod", "staff", "team",
                               "sotrudnik", "rekvizit" };
    var re = new System.Text.RegularExpressions.Regex(
        "href\\s*=\\s*[\"']([^\"'#]{1,180})[\"']",
        System.Text.RegularExpressions.RegexOptions.IgnoreCase);

    Uri baza = new Uri(url);
    var vidno = new HashSet<string>();
    var kandidaty = new List<string>();

    foreach (System.Text.RegularExpressions.Match m in re.Matches(glavnaya))
    {
        string ssylka = m.Groups[1].Value.Trim();
        if (ssylka.Length == 0) continue;
        string nizhniy = ssylka.ToLower();
        if (nizhniy.StartsWith("mailto:") || nizhniy.StartsWith("tel:")
            || nizhniy.StartsWith("javascript:")) continue;

        bool podhodit = false;
        foreach (string s in slova) { if (nizhniy.Contains(s)) { podhodit = true; break; } }
        if (!podhodit) continue;

        string polnyy;
        try { polnyy = new Uri(baza, ssylka).ToString(); }
        catch { continue; }
        // чужие домены не трогаем: нам нужен сайт этой компании, а не соцсети
        try { if (new Uri(polnyy).Host != baza.Host) continue; } catch { continue; }
        if (polnyy == url) continue;
        if (vidno.Add(polnyy)) kandidaty.Add(polnyy);
    }

    // контактные страницы первыми, остальные следом
    var snachala = new List<string>();
    var potom = new List<string>();
    foreach (string k in kandidaty)
    {
        string n = k.ToLower();
        if (n.Contains("contact") || n.Contains("kontakt") || n.Contains("svyaz"))
            snachala.Add(k);
        else potom.Add(k);
    }
    snachala.AddRange(potom);

    // карта сайта: реальные страницы, а не придуманные адреса — идут сразу за ссылками
    string koren = baza.Scheme + "://" + baza.Host;
    foreach (string s in iz_karty(koren))
    {
        if (!vidno.Contains(s)) { vidno.Add(s); snachala.Add(s); }
    }
    // угадки — в самый хвост и только если контактной страницы так и нет
    bool est_kontakt = false;
    foreach (string s in snachala)
    {
        string n = s.ToLower();
        if (n.Contains("contact") || n.Contains("kontakt")) { est_kontakt = true; break; }
    }
    if (!est_kontakt)
    {
        foreach (string p in ugadki)
        {
            string polnyy = koren + p;
            if (!vidno.Contains(polnyy)) { vidno.Add(polnyy); snachala.Add(polnyy); }
        }
    }

    int vzyato = 0;
    var vtoroy = new List<string>();
    foreach (string k in snachala)
    {
        if (vzyato >= predel) break;
        string h = vzyat(k);
        vzyato++;
        if (h.Length == 0) continue;
        adresa.Add(k);
        htmly.Add(h);

        // ВТОРОЙ УРОВЕНЬ: у мульти-офисных сайтов карточки отделов и филиалов лежат
        // ПОД страницей контактов (/contacts/moscow, /contacts/otdel-prodazh), и с
        // главной на них ссылок нет. Собираем их со страниц контактов, обходим после.
        string nk = k.ToLower();
        if (!(nk.Contains("contact") || nk.Contains("kontakt") || nk.Contains("staff")
              || nk.Contains("rukovod"))) continue;
        foreach (System.Text.RegularExpressions.Match m in re.Matches(h))
        {
            string ss = m.Groups[1].Value.Trim();
            string ns = ss.ToLower();
            if (ns.StartsWith("mailto:") || ns.StartsWith("tel:")
                || ns.StartsWith("javascript:")) continue;
            bool podhodit2 = false;
            foreach (string s in slova) { if (ns.Contains(s)) { podhodit2 = true; break; } }
            if (!podhodit2) continue;
            string polnyy2;
            try { polnyy2 = new Uri(baza, ss).ToString(); } catch { continue; }
            try { if (new Uri(polnyy2).Host != baza.Host) continue; } catch { continue; }
            if (vidno.Add(polnyy2) && !vtoroy.Contains(polnyy2)) vtoroy.Add(polnyy2);
        }
    }

    // второй уровень: бюджет отдельный, staff-карточки первыми
    vtoroy.Sort(delegate(string a, string b)
    {
        bool sa = a.ToLower().Contains("staff") || a.ToLower().Contains("rukovod");
        bool sb = b.ToLower().Contains("staff") || b.ToLower().Contains("rukovod");
        return sa == sb ? 0 : (sa ? -1 : 1);
    });
    int vzyato2 = 0;
    foreach (string k in vtoroy)
    {
        if (vzyato2 >= predel) break;
        string h = vzyat(k);
        vzyato2++;
        if (h.Length == 0) continue;
        adresa.Add(k);
        htmly.Add(h);
    }
}

// Запись результата. Порядок важен: сперва html, ПОТОМ .urls.txt — приёмник ориентируется
// на список адресов, и если он появится раньше страниц, разбор подхватит половину.
for (int i = 0; i < htmly.Count; i++)
{
    System.IO.File.WriteAllText(
        System.IO.Path.Combine(papka, inn + "_" + i.ToString() + ".html"),
        htmly[i], System.Text.Encoding.UTF8);
}
if (htmly.Count > 0)
{
    System.IO.File.WriteAllLines(
        System.IO.Path.Combine(papka, inn + ".urls.txt"), adresa.ToArray(),
        System.Text.Encoding.UTF8);
}
else
{
    // Не далось даже Зенке. Пишем отдельно и НЕ возвращаем в очередь: молчаливый
    // повтор гоняет один и тот же мёртвый сайт по кругу, а видеть такие адреса надо.
    lock (SyncObjects.ListSyncer)
    {
        System.IO.File.AppendAllText(
            System.IO.Path.Combine(koren_obmena, "ne_otkrylis.txt"),
            inn + ";" + url + ";" + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + "\r\n",
            System.Text.Encoding.UTF8);
    }
}
if (oshibki.Length > 0)
{
    System.IO.File.WriteAllText(
        System.IO.Path.Combine(papka, inn + ".err.txt"),
        oshibki.ToString(), System.Text.Encoding.UTF8);
}

project.SendInfoToLog(inn + ": страниц " + htmly.Count.ToString()
                      + ", адрес " + url, true);
return htmly.Count;
