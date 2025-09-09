import psycopg2
import pandas as pd

# ==== CONFIG ====
DB_CONFIG = {
    "dbname": "argo_db",
    "user": "postgres",
    "password": "chenn@1",
    "host": "localhost",
    "port": 5432
}

def main():
    # Read query from file
    with open("query.sql", "r") as f:
        sql_query = f.read().strip()

    print("\n▶ Running SQL Query:")
    print(sql_query)

    conn = psycopg2.connect(**DB_CONFIG)
    df = pd.read_sql(sql_query, conn)
    conn.close()

    print("\n📊 Query Result:")
    print(df.to_string(index=False))

if __name__ == "__main__":
    main()
