"""
check_column_data_status.py
Show, for each table and column, how many rows have data, are NULL, or empty.
"""

import psycopg2

DB_CONFIG = {
    "dbname": "argo_db",
    "user": "postgres",
    "password": "12345",
    "host": "localhost",
    "port": 5432
}

TABLES = [
    "dacs",
    "floats",
    "sensors",
    "profiles",
    "measurements",
    "bgc_measurements",
    "trajectories"
]

def report_table(table, cur):
    print(f"\n--- Table: {table} ---")
    cur.execute(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = '{table}'
    """)
    columns = [row[0] for row in cur.fetchall()]

    for col in columns:
        # Count NULLs
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
        null_count = cur.fetchone()[0]

        # Count empty strings (for text-like columns)
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM {table} 
            WHERE {col} IS NOT NULL AND {col}::text = ''
        """)
        empty_count = cur.fetchone()[0]

        # Count data (non-null, non-empty)
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM {table} 
            WHERE {col} IS NOT NULL AND {col}::text <> ''
        """)
        data_count = cur.fetchone()[0]

        print(f"{col:30} | Data: {data_count:6} | NULL: {null_count:6} | Empty: {empty_count:6}")

def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for table in TABLES:
        report_table(table, cur)

    cur.close()
    conn.close()
    print("\n✅ Column data status report complete.")

if __name__ == "__main__":
    main()
