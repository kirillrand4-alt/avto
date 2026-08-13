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
// ВХОД (проект ZennoPoster):
//   список  sajty  — строки «ИНН;адрес» (адрес можно без http)
//   список  proxy  — строки socks5://user:pass@host:port (можно пустой список)
//   переменная  papka_vyhod  — куда складывать результат, напр. C:\seostat\drop\zenno
//   переменная  stranic_max   — сколько внутренних страниц брать сверх главной (по умолч. 3)
//
// ВЫХОД (на компанию):
//   <ИНН>_0.html, <ИНН>_1.html ...  — сырой HTML каждой открытой страницы
//   <ИНН>.urls.txt                  — адреса в том же порядке, по строке на файл
//   <ИНН>.err.txt                   — если что-то не открылось: адрес и причина
// JSON намеренно не собираем: экранировать HTML в C# руками — источник битых файлов.

string stroka = "";
lock (SyncObjects.ListSyncer)
{
    if (project.Lists["sajty"].Count == 0)
    {
        project.SendInfoToLog("список сайтов пуст — поток завершён", true);
        return -1;
    }
    stroka = project.Lists["sajty"][0];
    project.Lists["sajty"].RemoveAt(0);
}

var chasti = stroka.Split(';');
string inn = chasti[0].Trim();
string url = (chasti.Length > 1 ? chasti[1] : chasti[0]).Trim();
if (url.Length == 0) return -1;
if (!url.StartsWith("http")) url = "http://" + url;

string papka = project.Variables["papka_vyhod"].Value;
if (string.IsNullOrEmpty(papka)) papka = @"C:\seostat\drop\zenno";
System.IO.Directory.CreateDirectory(papka);

int predel = 3;
int.TryParse(project.Variables["stranic_max"].Value, out predel);
if (predel <= 0) predel = 3;

// прокси по кругу: взяли первый, вернули в конец списка
string proxy = "";
lock (SyncObjects.ListSyncer)
{
    if (project.Lists["proxy"].Count > 0)
    {
        proxy = project.Lists["proxy"][0].Trim();
        project.Lists["proxy"].RemoveAt(0);
        project.Lists["proxy"].Add(proxy);
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

    int vzyato = 0;
    foreach (string k in snachala)
    {
        if (vzyato >= predel) break;
        string h = vzyat(k);
        vzyato++;
        if (h.Length == 0) continue;
        adresa.Add(k);
        htmly.Add(h);
    }
}

// запись результата
for (int i = 0; i < htmly.Count; i++)
{
    System.IO.File.WriteAllText(
        System.IO.Path.Combine(papka, inn + "_" + i.ToString() + ".html"),
        htmly[i], System.Text.Encoding.UTF8);
}
System.IO.File.WriteAllLines(
    System.IO.Path.Combine(papka, inn + ".urls.txt"), adresa.ToArray(),
    System.Text.Encoding.UTF8);
if (oshibki.Length > 0)
{
    System.IO.File.WriteAllText(
        System.IO.Path.Combine(papka, inn + ".err.txt"),
        oshibki.ToString(), System.Text.Encoding.UTF8);
}

project.SendInfoToLog(inn + ": страниц " + htmly.Count.ToString()
                      + ", адрес " + url, true);
return htmly.Count;
