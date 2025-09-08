import os
import psycopg2
import xarray as xr

# ==== CONFIG ====
BASE_DIR = "./incois"
DB_CONFIG = {
    "dbname": "argo_db",
    "user": "postgres",
    "password": "chenn@1",
    "host": "localhost",
    "port": 5432
}

def get_float_dirs(base_dir):
    """Return list of float directories (WMO IDs)."""
    return [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]

def insert_profile(conn, float_id, file_path, file_name):
    """Extract info from profile .nc file and insert into DB."""
    try:
        ds = xr.open_dataset(file_path)

        cycle_number = int(ds["CYCLE_NUMBER"].values[0]) if "CYCLE_NUMBER" in ds else None
        juld = str(ds["JULD"].values[0]) if "JULD" in ds else None
        latitude = float(ds["LATITUDE"].values[0]) if "LATITUDE" in ds else None
        longitude = float(ds["LONGITUDE"].values[0]) if "LONGITUDE" in ds else None
        direction = str(ds["DIRECTION"].values[0]) if "DIRECTION" in ds else None
        data_mode = str(ds["DATA_MODE"].values[0]) if "DATA_MODE" in ds else None
        vss = str(ds["VERTICAL_SAMPLING_SCHEME"].values[0]) if "VERTICAL_SAMPLING_SCHEME" in ds else None

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO profiles 
                (float_id, cycle_number, juld, latitude, longitude, direction, data_mode, vertical_sampling_scheme, file_name)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING;
            """,
            (float_id, cycle_number, juld, latitude, longitude, direction, data_mode, vss, file_name)
        )
        cur.close()

        ds.close()
    except Exception as e:
        print(f"⚠️ Error reading {file_path}: {e}")

def fill_profiles():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    float_dirs = get_float_dirs(BASE_DIR)
    print(f"Found {len(float_dirs)} floats")

    for wmo_id in float_dirs:
        # Get float_id from DB
        cur.execute("SELECT float_id FROM floats WHERE wmo_id=%s", (wmo_id,))
        result = cur.fetchone()
        if not result:
            print(f"⚠️ Float {wmo_id} not found in DB")
            continue
        float_id = result[0]

        profiles_dir = os.path.join(BASE_DIR, wmo_id, "profiles")
        if not os.path.isdir(profiles_dir):
            continue

        for fname in os.listdir(profiles_dir):
            if fname.endswith(".nc"):
                file_path = os.path.join(profiles_dir, fname)
                insert_profile(conn, float_id, file_path, fname)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Profiles inserted into DB")

if __name__ == "__main__":
    fill_profiles()
