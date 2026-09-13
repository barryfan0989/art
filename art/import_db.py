import pymysql
import json
import sys
import os
import re

# ======================
# MySQL Connection Configuration
# ======================
DB_CONFIG = {
    "host": "ticketdb-ticket63.f.aivencloud.com",
    "port": 13599,
    "user": "avnadmin",
    "password": "AVNS_QqNVFqacdQinAgGmXY9",
    "database": "defaultdb",
    "charset": "utf8mb4",
    "autocommit": True
}

def parse_genre_and_language(genre_str):
    genre = genre_str.strip()
    if "台語" in genre or "臺語" in genre:
        lang = "台語"
    elif "日" in genre or "動漫" in genre or "聲優" in genre or "J-pop" in genre or "J-Rock" in genre:
        lang = "日語"
    elif "韓" in genre or "K-pop" in genre:
        lang = "韓語"
    elif "英" in genre or "西洋" in genre or "英文" in genre:
        lang = "英語"
    elif "泰" in genre:
        lang = "泰語"
    elif "華語" in genre or "國語" in genre or "流行" in genre or "經典" in genre or "民謠" in genre or "饒舌" in genre or "喜劇" in genre or "漫才" in genre or "獨立" in genre:
        lang = "華語"
    elif "印尼" in genre:
        lang = "印尼語"
    else:
        lang = "未指定"
    return genre, lang

def import_database():
    print("=== [DATABASE IMPORT] ===")
    
    # 1. Resolve paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.abspath(os.path.join(base_dir, "..", "database_export.json"))
    
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found at {json_path}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Loading JSON data from {json_path}...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    except Exception as e:
        print(f"Error parsing JSON file: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Found {len(events_data)} events to import.")
    
    # 2. Connect to the database
    print("Connecting to the database...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)
        
    print("Connected successfully.")
    
    # 3. Clean up the targeted tables
    try:
        print("Clearing targeted tables...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        
        tables_to_clean = [
            "event_artists",
            "event_tickets",
            "events",
            "artist_news",
            "artist_categories",
            "artists",
            "venues"
        ]
        
        for table in tables_to_clean:
            print(f" - Truncating table: {table}")
            cursor.execute(f"TRUNCATE TABLE `{table}`;")
            
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        print("Cleanup completed successfully.")
        
    except Exception as e:
        print(f"Error occurred during cleanup: {e}", file=sys.stderr)
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except:
            pass
        sys.exit(1)

    # 4. Import the data
    try:
        print("Importing data...")
        
        # Caches to avoid duplicate entries and lookup overhead
        venue_cache = {}  # name -> venue_id
        artist_cache = {}  # name -> artist_id
        
        imported_venues = 0
        imported_artists = 0
        imported_events = 0
        imported_tickets = 0
        imported_bridges = 0
        
        for index, item in enumerate(events_data, start=1):
            # A. Process Venue
            venue_name = item.get("venue_name")
            venue_id = None
            if venue_name and venue_name.strip():
                venue_name_clean = venue_name.strip()
                venue_key = venue_name_clean.lower()
                venue_address = item.get("venue_address") or ""
                venue_city = item.get("venue_city")
                if venue_city:
                    venue_city = venue_city.strip()
                venue_description = item.get("venue_description")
                if venue_description:
                    venue_description = venue_description.strip()
                
                if venue_key in venue_cache:
                    venue_id = venue_cache[venue_key]
                else:
                    cursor.execute(
                        "INSERT INTO venues (name, address, city, description) VALUES (%s, %s, %s, %s)",
                        (
                            venue_name_clean,
                            venue_address,
                            venue_city if venue_city else None,
                            venue_description if venue_description else None
                        )
                    )
                    venue_id = cursor.lastrowid
                    venue_cache[venue_key] = venue_id
                    imported_venues += 1
                
            # B. Process Event
            event_name = item.get("event_name")
            source_site = item.get("source_site")
            ticket_sale_time = item.get("ticket_sale_time")
            event_time = item.get("event_time")
            event_url = item.get("event_url")
            scraped_at = item.get("scraped_at")
            
            cursor.execute("""
                INSERT INTO events (
                    venue_id, name, source_site, ticket_sale_time, event_time, event_url, scraped_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                venue_id,
                event_name,
                source_site,
                ticket_sale_time if ticket_sale_time else None,
                event_time if event_time else None,
                event_url,
                scraped_at if scraped_at else None
            ))
            event_id = cursor.lastrowid
            imported_events += 1
            
            # C. Process Tickets
            tickets = item.get("tickets") or []
            for t in tickets:
                ticket_type = t.get("ticket_type") or "未解析"
                price = t.get("price")
                if price is None:
                    price = -1
                else:
                    try:
                        price = int(price)
                    except:
                        price = -1
                cursor.execute(
                    "INSERT INTO event_tickets (event_id, ticket_type, price) VALUES (%s, %s, %s)",
                    (event_id, ticket_type, price)
                )
                imported_tickets += 1
                
            # D. Process Artists and Bridges
            artists = item.get("artists") or []
            for a in artists:
                artist_name = a.get("name")
                if not artist_name:
                    continue
                artist_name_clean = artist_name.strip()
                artist_key = artist_name_clean.lower()
                wiki_intro = a.get("wiki_intro") or ""
                wiki_url = a.get("wiki_url") or ""
                    
                if artist_key in artist_cache:
                    artist_id = artist_cache[artist_key]
                else:
                    cursor.execute(
                        "INSERT INTO artists (name, wiki_intro, wiki_url) VALUES (%s, %s, %s)",
                        (artist_name_clean, wiki_intro, wiki_url)
                    )
                    artist_id = cursor.lastrowid
                    artist_cache[artist_key] = artist_id
                    imported_artists += 1
                    
                    # Process categories (genres)
                    genres_summary = a.get("artist_genres_summary")
                    if genres_summary:
                        parts = [p.strip() for p in re.split(r'[/,、|]+', genres_summary) if p.strip()]
                        for part in parts:
                            genre, lang = parse_genre_and_language(part)
                            cursor.execute(
                                "INSERT INTO artist_categories (artist_id, genre, language) VALUES (%s, %s, %s)",
                                (artist_id, genre, lang)
                            )
                            
                    # Process news
                    news_title = a.get("recent_news_title")
                    news_url = a.get("recent_news_url")
                    if news_title and news_url:
                        cursor.execute(
                            "INSERT INTO artist_news (artist_id, title, url) VALUES (%s, %s, %s)",
                            (artist_id, news_title.strip(), news_url.strip())
                        )
                    
                # Bridge
                cursor.execute(
                    "INSERT IGNORE INTO event_artists (event_id, artist_id) VALUES (%s, %s)",
                    (event_id, artist_id)
                )
                imported_bridges += 1
                
            if index % 50 == 0 or index == len(events_data):
                print(f"Progress: Processed {index}/{len(events_data)} events...")
                
        # Commit the transaction
        conn.commit()
        print("\nDatabase import completed successfully.")
        print(f"Summary of imported records:")
        print(f" - Venues: {imported_venues}")
        print(f" - Artists: {imported_artists}")
        print(f" - Events: {imported_events}")
        print(f" - Tickets: {imported_tickets}")
        print(f" - Event-Artist associations: {imported_bridges}")
        print("==========================")
        
    except Exception as e:
        print(f"\nError occurred during import: {e}", file=sys.stderr)
        conn.rollback()
        sys.exit(1)
        
    finally:
        if 'conn' in locals() and conn:
            try:
                conn.close()
            except:
                pass

if __name__ == "__main__":
    import_database()
