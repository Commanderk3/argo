"""
seed_bgc_measurements.py
Insert biogeochemical (BGC) parameters per profile.
Handles missing values and masked arrays robustly.
"""

import os
import psycopg2
import xarray as xr
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = os.getenv('BASE_DIR')
DB_CONFIG = {
    "dbname": os.getenv('DB_NAME'),
    "user": os.getenv('DB_USER'),
    "password": os.getenv('DB_PASSWORD'),
    "host": os.getenv('DB_HOST'),
    "port": os.getenv('DB_PORT')
}

BGC_PARAMS = [
    "DOXY", "CHLA", "BBP700", "NITRATE", "PH_IN_SITU_TOTAL",
    "PH_ADJUSTED", "OXY2", "TEMP_DOXY", "PSAL_ADJUSTED"
]

def ensure_bgc_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bgc_measurements (
        bgc_id SERIAL PRIMARY KEY,
        profile_id INT REFERENCES profiles(profile_id) ON DELETE CASCADE,
        level_index INT,
        parameter TEXT,
        value DOUBLE PRECISION,
        qc VARCHAR(5),
        UNIQUE(profile_id, level_index, parameter)
    );
    """)
    conn.commit()
    cur.close()

def to_datetime_juld(val):
    try:
        v = float(np.squeeze(val))
        base = datetime(1950, 1, 1)
        return base + timedelta(days=v)
    except Exception:
        return None

def safe_get(arr, i):
    try:
        if arr is None:
            return None
        a = np.array(arr)
        if a.ndim == 2:
            val = a[0, i]
        elif a.ndim == 1:
            val = a[i]
        else:
            val = np.squeeze(a)
        if np.ma.is_masked(val) or val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except Exception:
        return None

def decode_qc(arr, i):
    try:
        if arr is None:
            return None
        a = np.array(arr)
        if a.ndim == 2:
            raw = a[0, i]
        elif a.ndim == 1:
            raw = a[i]
        else:
            raw = np.squeeze(a)
        if isinstance(raw, (bytes, bytearray)):
            s = raw.decode('utf-8', errors='ignore').replace("\x00", "").strip()
            return s[:5] if s else None
        s = str(raw).replace("\x00", "").strip()
        return s[:5] if s else None
    except Exception:
        return None

def insert_bgc_for_profile(conn, profile_id, file_path):
    try:
        ds = xr.open_dataset(file_path)
        cur = conn.cursor()

        # determine number of levels
        n_levels = 0
        for param in BGC_PARAMS:
            if param in ds.variables:
                a = np.array(ds.variables[param][:])
                if a.ndim == 2:
                    n_levels = max(n_levels, a.shape[1])
                elif a.ndim == 1:
                    n_levels = max(n_levels, a.shape[0])

        for param in BGC_PARAMS:
            if param not in ds.variables:
                continue
            values = ds.variables[param][:]
            qc_values = ds.variables.get(f"{param}_QC", None)

            for i in range(n_levels):
                val = safe_get(values, i)
                if val is None:
                    continue
                qc = decode_qc(qc_values, i)
                cur.execute("""
                    INSERT INTO bgc_measurements (profile_id, level_index, parameter, value, qc)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (profile_id, level_index, parameter) DO UPDATE
                        SET value = COALESCE(EXCLUDED.value, bgc_measurements.value),
                            qc = COALESCE(EXCLUDED.qc, bgc_measurements.qc);
                """, (profile_id, i, param, val, qc))

        conn.commit()
        cur.close()
        ds.close()
    except Exception as e:
        print(f"⚠️ Error inserting BGC for profile {file_path}: {e}")
        conn.rollback()

def fill_bgc():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_bgc_table(conn)

    cur = conn.cursor()
    cur.execute("SELECT profile_id, file_name, float_id FROM profiles JOIN floats USING(float_id)")
    rows = cur.fetchall()

    for profile_id, file_name, float_id in rows:
        # resolve file path
        cur2 = conn.cursor()
        cur2.execute("SELECT wmo_id FROM floats WHERE float_id=%s", (float_id,))
        wmo_res = cur2.fetchone()
        cur2.close()
        if not wmo_res:
            continue
        wmo = wmo_res[0]
        file_path = os.path.join(BASE_DIR, str(wmo), "profiles", file_name)
        if not os.path.exists(file_path):
            fallback = os.path.join(BASE_DIR, str(wmo), file_name)
            if os.path.exists(fallback):
                file_path = fallback
            else:
                continue
        insert_bgc_for_profile(conn, profile_id, file_path)

    cur.close()
    conn.close()
    print("✅ BGC measurements seeded.")

if __name__ == "__main__":
    fill_bgc()