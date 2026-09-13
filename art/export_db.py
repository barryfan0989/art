import pymysql
import json
from datetime import datetime
import os

# ======================
# MySQL Connection Configuration
# ======================
DB_CONFIG = {
    "host": "ticketdb-ticket63.f.aivencloud.com",
    "port": 13599,
    "user": "avnadmin",
    "password": "AVNS_QqNVFqacdQinAgGmXY9",
    "database": "defaultdb",
    "charset": "utf8mb4"
}

def datetime_serializer(obj):
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(f"Type {type(obj)} not serializable")

def export_to_json():
    print("Connecting to the database...")
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        print("Querying events and venues...")
        # 1. Fetch all events with venue info
        cursor.execute("""
            SELECT 
                e.id AS event_id,
                e.name AS event_name,
                e.source_site,
                e.ticket_sale_time,
                e.event_time,
                e.event_url,
                e.scraped_at,
                v.name AS venue_name,
                v.address AS venue_address,
                v.city AS venue_city,
                v.description AS venue_description
            FROM events e
            LEFT JOIN venues v ON e.venue_id = v.id
        """)
        events = {row['event_id']: row for row in cursor.fetchall()}
        
        # Initialize tickets and artists arrays for each event
        for ev in events.values():
            ev['tickets'] = []
            ev['artists'] = []
            
        print("Querying ticket details...")
        # 2. Fetch all tickets
        cursor.execute("SELECT event_id, ticket_type, price FROM event_tickets")
        for ticket in cursor.fetchall():
            ev_id = ticket['event_id']
            if ev_id in events:
                events[ev_id]['tickets'].append({
                    "ticket_type": ticket['ticket_type'],
                    "price": ticket['price']
                })
                
        print("Querying artist categories and news...")
        # Fetch categories (genres)
        cursor.execute("SELECT artist_id, genre FROM artist_categories")
        artist_genres = {}
        for row in cursor.fetchall():
            artist_genres.setdefault(row['artist_id'], []).append(row['genre'])

        # Fetch news
        cursor.execute("SELECT artist_id, title, url FROM artist_news")
        artist_news = {}
        for row in cursor.fetchall():
            artist_news[row['artist_id']] = {
                "recent_news_title": row['title'],
                "recent_news_url": row['url']
            }

        print("Querying event artist relationships...")
        # 3. Fetch all artists mapped to events
        cursor.execute("""
            SELECT ea.event_id, a.id AS artist_id, a.name, a.wiki_intro, a.wiki_url
            FROM event_artists ea
            JOIN artists a ON ea.artist_id = a.id
        """)
        for artist_link in cursor.fetchall():
            ev_id = artist_link['event_id']
            a_id = artist_link['artist_id']
            if ev_id in events:
                genres = artist_genres.get(a_id, [])
                genres_summary = " / ".join(genres) if genres else ""
                news = artist_news.get(a_id, {})
                
                events[ev_id]['artists'].append({
                    "name": artist_link['name'],
                    "wiki_intro": artist_link['wiki_intro'],
                    "wiki_url": artist_link['wiki_url'],
                    "artist_genres_summary": genres_summary,
                    "recent_news_title": news.get("recent_news_title", ""),
                    "recent_news_url": news.get("recent_news_url", "")
                })
                
        # Convert dict to list
        output_data = list(events.values())
        
        # Save one level up in the workspace root folder
        output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database_export.json"))
        
        print(f"Writing data to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2, default=datetime_serializer)
            
        print(f"Successfully exported {len(output_data)} events to database_export.json")
        
    finally:
        conn.close()

if __name__ == "__main__":
    export_to_json()
