from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from lxml import etree
from urllib.parse import urljoin
from datetime import datetime
import time
import re
import pymysql


# ======================
# MySQL
# ======================
conn = pymysql.connect(
    host="ticketdb-ticket63.f.aivencloud.com",
    port=13599,
    user="avnadmin",
    password="AVNS_QqNVFqacdQinAgGmXY9",
    database="defaultdb",
    charset="utf8mb4"
)
cursor = conn.cursor()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_dt(v):
    return v if v and str(v).strip() else None


# ======================
# Chrome（極速模式）
# ======================
options = Options()
options.add_argument("--start-maximized")

# ⭐關鍵1：不等待頁面完全載入
options.page_load_strategy = "none"

# ⭐關鍵2：禁止圖片/媒體載入（提速）
prefs = {
    "profile.managed_default_content_settings.images": 2,
    "profile.managed_default_content_settings.media_stream": 2
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(options=options)
driver.set_page_load_timeout(15)

BASE_URL = "https://kktix.com"


# ======================
# list page（極速）
# ======================
def get_list(page):
    url = f"https://kktix.com/events?page={page}&search=%E8%A1%A8%E6%BC%94"

    driver.get(url)

    # ⭐只等 h2 出現，不等整頁載入
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.XPATH, '//li//h2'))
    )

    xml = etree.HTML(driver.page_source)

    names = xml.xpath('//li//h2//text()')
    links = xml.xpath('//li[@class="type-selling"]/a/@href')

    data = []
    for n, l in zip(names, links):
        n = n.strip()
        l = urljoin(BASE_URL, l)
        data.append((n, l))

    return data


# ======================
# detail page（極速解析）
# ======================
def parse_detail(url):
    driver.get(url)

    # ⭐只等 info 出現（核心資料區域）
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//ul[@class="info"]'))
    )

    xml = etree.HTML(driver.page_source)

    # ========= 日期 =========
    activity_date = ""
    raw = xml.xpath('//ul[@class="info"]/li/span/span[1]/text()')
    if raw:
        m = re.search(r'(\d{4})/(\d{2})/(\d{2}).*?(\d{2}):(\d{2})', raw[0])
        if m:
            y, mo, d, h, mi = m.groups()
            activity_date = f"{y}-{mo}-{d} {h}:{mi}:00"

    # ========= venue =========
    venue_raw = xml.xpath('//ul[@class="info"]/li[2]/span/text()[2]')

    def clean_venue(v):
        if not v:
            return ""
        t = v[0].strip()
        if "｜" in t:
            t = t.split("｜", 1)[-1]
        if "/" in t:
            t = t.split("/", 1)[-1]
        return t.strip()

    venue = clean_venue(venue_raw)

    # ========= price =========
    price = ""
    ticket_type = []

    h3 = xml.xpath('//h3')
    if h3:
        html = etree.tostring(h3[0], encoding="unicode")

        for t in ["預售票", "一般票", "身障席"]:
            if t in html:
                ticket_type.append(t)

        price = ",".join(re.findall(r'NT\$\d+', html))

    return activity_date, venue, price, ticket_type


# ======================
# artist clean
# ======================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.I)[0]
    name = re.sub(r"\b20\d{2}\b", "", name)
    name = re.sub(r"(TOUR|CONCERT|FANMEETING|LIVE|WORLD|ASIA|SHOW|FEST|SPECIAL|ANNIVERSARY)",
                  "", name, flags=re.I)
    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# ======================
# wiki（requests）
# ======================
def get_wiki_info(artist):
    language = ""
    classify = ""
    outline = ""

    if not artist:
        return language, classify, outline

    try:
        import requests
        from urllib.parse import quote

        url = f"https://zh.wikipedia.org/zh-tw/{quote(artist)}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh-Hant;q=0.9,zh;q=0.8"}, timeout=15).text
        xml = etree.HTML(html)

        country = ''.join(xml.xpath(
            '//*[@id="mw-content-text"]//table[1]//tr[4]/td//text()'
        )).strip()

        if "日本" in country:
            language = "日語"
        elif "韓國" in country:
            language = "韓語"
        elif "美國" in country or "英國" in country:
            language = "英語"
        else:
            language = "華語"

        classify = "、".join(xml.xpath(
            '//*[@id="mw-content-text"]//table[1]//tr[5]/td//a/text()'
        ))

        ps = xml.xpath('//*[@id="mw-content-text"]//p')

        txt = []
        for p in ps:
            t = ''.join(p.xpath('.//text()')).strip()
            t = re.sub(r'\[\d+\]', '', t)
            if any(err in t for err in ["可能出現此提示", "維基百科目前還沒有名為", "本頁面目前沒有內容"]):
                continue
            if len(t) > 10:
                txt.append(t)
            if len(txt) >= 4:
                break

        outline = "\n".join(txt)

    except:
        pass

    return language, classify, outline


# ======================
# main
# ======================
for page in range(1, 14):

    print(f"\n========== PAGE {page} ==========")

    data = get_list(page)

    for name, link in data:

        try:
            activity_date, venue, price_raw, ticket_type = parse_detail(link)

            artist = extract_artist(name)
            language, classify, outline = get_wiki_info(artist)

            # ======================
            # venue
            # ======================
            cursor.execute("SELECT id FROM venues WHERE name=%s", (venue,))
            v = cursor.fetchone()

            if v:
                venue_id = v[0]
            else:
                cursor.execute("""
                    INSERT INTO venues(name,address)
                    VALUES(%s,%s)
                """, (venue, venue))
                conn.commit()
                venue_id = cursor.lastrowid

            # ======================
            # event
            # ======================
            cursor.execute("""
                INSERT INTO events(
                    venue_id,name,source_site,
                    event_time,event_url,scraped_at
                )
                VALUES(%s,%s,%s,%s,%s,%s)
            """, (
                venue_id,
                name,
                "kktix",
                safe_dt(activity_date),
                link,
                now()
            ))
            conn.commit()

            event_id = cursor.lastrowid

            # ======================
            # tickets
            # ======================
            if not price_raw:
                cursor.execute("""
                    INSERT INTO event_tickets(event_id,ticket_type,price)
                    VALUES(%s,%s,%s)
                """, (event_id, "未解析", -1))
            else:
                for p in price_raw.split(","):
                    cursor.execute("""
                        INSERT INTO event_tickets(event_id,ticket_type,price)
                        VALUES(%s,%s,%s)
                    """, (
                        event_id,
                        ",".join(ticket_type) or "一般票",
                        p
                    ))

            # ======================
            # artist
            # ======================
            cursor.execute("SELECT id FROM artists WHERE name=%s", (artist,))
            a = cursor.fetchone()

            if a:
                artist_id = a[0]
            else:
                cursor.execute("""
                    INSERT INTO artists(name,wiki_intro,wiki_url)
                    VALUES(%s,%s,%s)
                """, (artist, outline, ""))
                conn.commit()
                artist_id = cursor.lastrowid

            # ======================
            # bridge
            # ======================
            cursor.execute("""
                INSERT IGNORE INTO event_artists(event_id,artist_id)
                VALUES(%s,%s)
            """, (event_id, artist_id))

            conn.commit()

            print("OK:", name)

        except Exception as e:
            print("ERROR:", name, e)
            conn.rollback()


driver.quit()