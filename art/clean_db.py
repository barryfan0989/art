import pymysql
import sys

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

def clean_database():
    print("=== [DATABASE CLEANUP] ===")
    print("Connecting to the database...")
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)

    print("Connected successfully. Clearing old crawler data...")
    try:
        # Disable foreign key checks to allow truncating tables with relationships
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        
        # Tables to clean. We clean crawler tables and dependent tables to prevent orphaned rows
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
        conn.commit()
        print("Database cleanup completed successfully.")
        print("==========================")
    except Exception as e:
        print(f"Error occurred during cleanup: {e}", file=sys.stderr)
        conn.rollback()
        # Restore key checks in case of exception
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        except:
            pass
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    clean_database()
