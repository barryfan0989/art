from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from lxml import etree
import time
import re
import requests
from urllib.parse import quote
from datetime import datetime
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
    if not v or str(v).strip() == "":
        return None
    return v


# ======================
# Chrome
# ======================
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(options=options)


# ======================
# 列表頁（滾動載入）
# ======================
driver.get("https://www.indievox.com/activity")
time.sleep(5)


def get_list():
    html = driver.page_source
    xml = etree.HTML(html)

    links = xml.xpath('//div[@class="thumbnails activity"]/a/@href')
    names = xml.xpath('//div[@class="thumbnails activity"]/a/div[2]/div[2]//text()')

    data = []
    for name, link in zip(names, links):
        name = name.strip()
        if not link.startswith("http"):
            link = "https://www.indievox.com" + link
        data.append((name, link))
    return data


all_data = []
last_count = 0
no_change = 0

while True:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    try:
        btn = driver.find_element(By.XPATH,
            '//*[@id="activityListTab"]//a[contains(@class,"btn")]'
        )
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(3)
    except:
        pass

    data = get_list()

    for item in data:
        if item not in all_data:
            all_data.append(item)

    if len(all_data) == last_count:
        no_change += 1
    else:
        no_change = 0

    last_count = len(all_data)

    if no_change >= 3:
        break


# ======================
# artist
# ======================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.IGNORECASE)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)

    name = re.sub(
        r"(TOUR|CONCERT|LIVE|SHOW|FEST|SPECIAL|ANNIVERSARY|FANMEETING)",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# ======================
# detail parse
# ======================
def parse_detail(url):
    driver.get(url)
    time.sleep(3)

    html = driver.page_source

    activity_date = ""
    price = ""
    ticket_type = "一般票"
    venue = ""

    # 日期 + 時間
    date_match = re.search(r"日期[：:]\s*(\d{1,2})\.(\d{1,2})", html)
    time_match = re.search(r"時間[：:]\s*([0-9]{1,2}:[0-9]{2})", html)

    if date_match and time_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        hh_mm = time_match.group(1)
        activity_date = f"2026-{month:02d}-{day:02d} {hh_mm}:00"

    # venue
    m2 = re.search(r"演出場地地址\s*[:：]\s*(.+)", html)
    if m2:
        venue = m2.group(1).split("<")[0].strip()

    # price raw
    m3 = re.search(r"活動票價\s*[:：]\s*(.+)", html)
    if m3:
        price = m3.group(1).strip()

    return activity_date, venue, price, ticket_type


# ======================
# ticket parse（關鍵修復）
# ======================
def parse_ticket_price(raw):
    if not raw:
        return []

    raw = re.sub(r"（.*?）", "", raw)
    parts = raw.split("/")

    result = []

    for p in parts:
        p = p.strip()
        nums = re.findall(r"\d{3,5}", p)

        if not nums:
            continue

        price = int(nums[-1])
        ttype = re.sub(r"\d+.*", "", p).strip() or "一般票"

        result.append((ttype, price))

    return result


# ======================
# wiki
# ======================
def get_wiki_info(artist):
    language = ""
    classify = ""
    outline = ""

    if not artist:
        return language, classify, outline

    try:
        url = f"https://zh.wikipedia.org/zh-tw/{quote(artist)}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW,zh-Hant;q=0.9,zh;q=0.8"}, timeout=15).text
        xml = etree.HTML(html)

        country = "".join(xml.xpath('//table[contains(@class,"infobox")]//tr[th[contains(text(),"國家") or contains(text(),"來源")]]/td//text()'))

        if "日本" in country:
            language = "日語"
        elif "韓國" in country:
            language = "韓語"
        elif "中國" in country or "台灣" in country or "臺灣" in country or "香港" in country:
            language = "華語"
        elif "美國" in country or "英國" in country:
            language = "英語"
        else:
            language = "華語"

        classify = "、".join(xml.xpath('//table[contains(@class,"infobox")]//tr[th[contains(text(),"類型")]]//a/text()'))

        ps = xml.xpath('//*[@id="mw-content-text"]//p')
        tmp = []
        for p in ps:
            t = "".join(p.xpath(".//text()")).strip()
            t = re.sub(r"\[\d+\]", "", t)
            if any(err in t for err in ["可能出現此提示", "維基百科目前還沒有名為", "本頁面目前沒有內容"]):
                continue
            if len(t) > 10:
                tmp.append(t)
            if len(tmp) >= 3:
                break

        outline = "\n".join(tmp)

    except:
        pass

    return language, classify, outline


# ======================
# MAIN INSERT
# ======================
Source = "https://www.indievox.com/activity"

for i, (name, link) in enumerate(all_data, 1):

    try:
        print(f"\n[{i}] {name}")

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
            "indievox",
            safe_dt(activity_date),
            link,
            now()
        ))
        conn.commit()

        event_id = cursor.lastrowid

        # ======================
        # tickets
        # ======================
        tickets = parse_ticket_price(price_raw)

        if not tickets:
            cursor.execute("""
                INSERT INTO event_tickets(event_id,ticket_type,price)
                VALUES(%s,%s,%s)
            """, (event_id, "未解析", -1))
        else:
            for ttype, price in tickets:
                cursor.execute("""
                    INSERT INTO event_tickets(event_id,ticket_type,price)
                    VALUES(%s,%s,%s)
                """, (event_id, ttype, price))

        # ======================
        # artist
        # ======================
        cursor.execute("SELECT id FROM artists WHERE name=%s", (artist,))
        a = cursor.fetchone()

        if a:
            artist_id = a[0]
        else:
            cursor.execute("""
                INSERT INTO artists(name,wiki_intro)
                VALUES(%s,%s)
            """, (artist, outline))
            conn.commit()
            artist_id = cursor.lastrowid

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