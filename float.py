import os
import psycopg2

# ==== CONFIG ====
BASE_DIR = "./incois"   # path to your incois directory
DB_CONFIG = {
    "dbname": "argo_db",
    "user": "postgres",
    "password": "chenn@1",
    "host": "localhost",
    "port": 5432
}

def get_float_ids(base_dir):
    """Scan directory and return list of WMO IDs (float IDs)."""
    float_ids = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    return sorted(float_ids, key=lambda x: int(x))

def insert_float_ids(float_ids):
    """Insert float IDs into PostgreSQL floats table."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for fid in float_ids:
        try:
            cur.execute(
                """
                INSERT INTO floats (wmo_id, dac_center)
                VALUES (%s, %s)
                ON CONFLICT (wmo_id) DO NOTHING;
                """,
                (fid, "incois")
            )
        except Exception as e:
            print(f"Error inserting {fid}: {e}")

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    float_ids = get_float_ids(BASE_DIR)
    print(f"Found {len(float_ids)} float IDs")

    insert_float_ids(float_ids)
    print("✅ Float IDs inserted into database")
