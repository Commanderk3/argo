import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_NAME = "argo"
DB_USER = "postgres"
DB_PASS = "12345"
DB_HOST = "localhost"

# Step 1: connect to default 'postgres' DB
conn = psycopg2.connect(dbname="postgres", user=DB_USER, password=DB_PASS, host=DB_HOST)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Step 2: create argo db if not exists
cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'")
exists = cur.fetchone()

if not exists:
    cur.execute(f"CREATE DATABASE {DB_NAME}")
    print(f"✅ Database {DB_NAME} created.")
else:
    print(f"ℹ️ Database {DB_NAME} already exists.")

cur.close()
conn.close()

# Step 3: connect to argo and reset schema
conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST)
cur = conn.cursor()
cur.execute("DROP SCHEMA public CASCADE;")
cur.execute("CREATE SCHEMA public;")
conn.commit()
cur.close()
conn.close()

print("✅ Database reset (clean schema).")
