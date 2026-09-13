from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from lxml import etree
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


# ======================
# 安全時間處理（關鍵修復）
# ======================
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
# 頁面
# ======================
url = "https://ticket.ibon.com.tw/Index/entertainment"
driver.get(url)
time.sleep(8)

response = driver.page_source
xml = etree.HTML(response)

names = xml.xpath('//h2/text()')
links = xml.xpath('//*[@id="content"]/div/div/app-activity-for-index/div/owl-carousel-o/div/div/owl-stage/div/div/div//a/@href')


# ======================
# artist 清洗
# ======================
def extract_artist(name):
    if not name:
        return ""

    name = re.sub(r"\s+", " ", name).strip()
    name = re.split(r"\s+in\s+", name, flags=re.IGNORECASE)[0].strip()
    name = re.sub(r"\b20\d{2}\b", "", name)
    name = re.sub(r"(TOUR|CONCERT|FANMEETING|LIVE|WORLD|ASIA|SHOW|FEST|SPECIAL|ANNIVERSARY)",
                  "", name, flags=re.IGNORECASE)
    name = re.sub(r"[《》【】()\[\]（）<>：:|·–—\-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ======================
# 🔥 票價解析（增強穩定版）
# ======================
def parse_ticket_prices(raw):
    if not raw:
        return []

    raw = re.sub(r"（.*?）", "", raw)
    raw = raw.replace("票價", "").strip()

    if "$" not in raw:
        return []

    items = raw.split("/")

    result = []

    for item in items:
        item = item.strip()
        if not item or "$" not in item:
            continue

        parts = item.split("$")
        if len(parts) < 2:
            continue

        ticket_type = parts[0].strip() or "一般票"

        price_match = re.findall(r"\d+", parts[1])
        if not price_match:
            continue

        price = int("".join(price_match))
        result.append((ticket_type, price))

    return result


# ======================
# 詳情解析
# ======================
def parse_detail_fields(text):
    activity_date = ""
    venue = ""
    price = ""
    ticket_type = "一般票"

    if not text:
        return activity_date, venue, price, ticket_type

    m1 = re.search(r'演出日期\s*[:：]\s*(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m1:
        y, m, d = m1.group(1), m1.group(2).zfill(2), m1.group(3).zfill(2)

        m_time = re.search(r'演出時間\s*[:：]\s*(\d{1,2})[:：](\d{2})', text)
        if m_time:
            hh, mm = m_time.group(1).zfill(2), m_time.group(2).zfill(2)
        else:
            hh, mm = "00", "00"

        activity_date = f"{y}-{m}-{d} {hh}:{mm}:00"

    m2 = re.search(r'演出場地地址\s*[:：]\s*(.+)', text)
    if m2:
        venue = m2.group(1).split("<")[0].strip()

    m3 = re.search(r'活動票價\s*[:：]\s*(.+)', text)
    if m3:
        price = m3.group(1).strip()

    return activity_date, venue, price, ticket_type


# ======================
# 售票時間
# ======================
def parse_open_time(text):
    if not text:
        return ""

    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})[:：](\d{2})', text)
    if not m:
        return ""

    return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)} {m.group(4).zfill(2)}:{m.group(5).zfill(2)}:00"


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

        rows = xml.xpath('//table[contains(@class,"infobox")]//tr')

        country = ""

        for r in rows:
            th = "".join(r.xpath("./th//text()")).strip()
            if th in ["國家", "來源地", "出身地"]:
                country = "".join(r.xpath("./td//text()")).strip()
                break

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

        for r in rows:
            th = "".join(r.xpath("./th//text()")).strip()
            if "類型" in th or "音樂" in th:
                classify = "、".join(r.xpath("./td//a/text()"))
                break

        ps = xml.xpath('//*[@id="mw-content-text"]//p')

        txt = []
        for p in ps:
            t = "".join(p.xpath(".//text()")).strip()
            t = re.sub(r"\[\d+\]", "", t)
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
# 主迴圈
# ======================
for name, link in zip(names, links):

    try:
        url = "https://ticket.ibon.com.tw" + link

        driver.get(url)
        time.sleep(5)

        html = driver.page_source

        activity_date, venue, price_raw, ticket_type = parse_detail_fields(html)
        issuance = parse_open_time(html)

        artist = extract_artist(name)
        language, classify, outline = get_wiki_info(artist)

        # ======================
        # VENUE
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
        # EVENT
        # ======================
        cursor.execute("""
            INSERT INTO events(
                venue_id,name,source_site,
                ticket_sale_time,event_time,
                event_url,scraped_at
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s)
        """, (
            venue_id,
            name,
            "ibon",
            safe_dt(issuance),
            safe_dt(activity_date),
            url,
            now()
        ))
        conn.commit()

        event_id = cursor.lastrowid

        # ======================
        # TICKET（🔥最終修復）
        # ======================
        tickets = parse_ticket_prices(price_raw)

        if not tickets:
            cursor.execute("""
                INSERT INTO event_tickets(event_id,ticket_type,price)
                VALUES(%s,%s,%s)
            """, (event_id, "未解析票種", -1))
        else:
            for t_type, price in tickets:
                cursor.execute("""
                    INSERT INTO event_tickets(event_id,ticket_type,price)
                    VALUES(%s,%s,%s)
                """, (event_id, t_type, price))

        # ======================
        # ARTIST
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
        # BRIDGE
        # ======================
        cursor.execute("""
            INSERT IGNORE INTO event_artists(event_id,artist_id)
            VALUES(%s,%s)
        """, (event_id, artist_id))

        conn.commit()

        # ======================
        # DEBUG 輸出
        # ======================
        print("=========== DEBUG ===========")
        print("活動:", name)
        print("藝人:", artist)
        print("日期:", activity_date)
        print("售票:", issuance)
        print("場館:", venue)
        print("票價RAW:", price_raw)
        print("解析票價:", tickets)
        print("============================")

        print("OK:", name)

    except Exception as e:
        print("ERROR:", name, e)
        conn.rollback()


driver.quit()