"""
seed_measurements.py
Insert level-by-level measurements for each profile.
Creates measurements table if missing.
This script handles masked arrays / NaN and stores adjusted values if available.
"""
import os
import psycopg2
import xarray as xr
import numpy as np
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

def ensure_measurements_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS measurements (
        meas_id SERIAL PRIMARY KEY,
        profile_id INT REFERENCES profiles(profile_id) ON DELETE CASCADE,
        level_index INT,
        pres DOUBLE PRECISION,
        pres_qc CHAR(1),
        pres_adjusted DOUBLE PRECISION,
        pres_adjusted_error DOUBLE PRECISION,
        temp DOUBLE PRECISION,
        temp_qc CHAR(1),
        temp_adjusted DOUBLE PRECISION,
        temp_adjusted_error DOUBLE PRECISION,
        psal DOUBLE PRECISION,
        psal_qc CHAR(1),
        psal_adjusted DOUBLE PRECISION,
        psal_adjusted_error DOUBLE PRECISION,
        UNIQUE(profile_id, level_index)
    );
    """)
    conn.commit()
    cur.close()

def safe_get(arr, i, fallback=None):
    """Return numeric or None for arr[i]; handles masked arrays and shapes."""
    try:
        if arr is None:
            return fallback
        a = np.array(arr)
        # If 2D (nprof x nlevel) choose first profile row if present
        if a.ndim == 2:
            val = a[0, i]
        elif a.ndim == 1:
            val = a[i]
        else:
            val = np.squeeze(a)
        if np.ma.is_masked(val):
            return None
        if isinstance(val, (np.floating, float, np.float32, np.float64)):
            if np.isnan(val):
                return None
            return float(val)
        if val is None:
            return None
        return float(val)
    except Exception:
        try:
            v = a.flatten()[i]
            return None if np.isnan(v) else float(v)
        except Exception:
            return fallback

def decode_qc(arr, i):
    try:
        if arr is None:
            return None
        a = np.array(arr)
        if a.ndim == 2:
            raw = a[0,i]
        elif a.ndim == 1:
            raw = a[i]
        else:
            raw = np.squeeze(a)
        # raw might be bytes array or char
        if isinstance(raw, (bytes, bytearray)):
            s = raw.decode('utf-8', errors='ignore').replace("\x00","").strip()
            return s[:1] if s else None
        s = str(raw)
        s = s.replace("\x00","").strip()
        return s[:1] if s else None
    except Exception:
        return None

def insert_measurements_for_profile(conn, profile_id, file_path):
    try:
        ds = xr.open_dataset(file_path)
        cur = conn.cursor()

        pres = ds.variables["PRES"][:] if "PRES" in ds.variables else None
        pres_adj = ds.variables.get("PRES_ADJUSTED", None)
        pres_adj_err = ds.variables.get("PRES_ADJUSTED_ERROR", None)
        temp = ds.variables["TEMP"][:] if "TEMP" in ds.variables else None
        temp_adj = ds.variables.get("TEMP_ADJUSTED", None)
        temp_adj_err = ds.variables.get("TEMP_ADJUSTED_ERROR", None)
        psal = ds.variables["PSAL"][:] if "PSAL" in ds.variables else None
        psal_adj = ds.variables.get("PSAL_ADJUSTED", None)
        psal_adj_err = ds.variables.get("PSAL_ADJUSTED_ERROR", None)

        pres_qc = ds.variables.get("PRES_QC", None)
        temp_qc = ds.variables.get("TEMP_QC", None)
        psal_qc = ds.variables.get("PSAL_QC", None)

        # determine number of levels
        n_levels = 0
        if pres is not None:
            a = np.array(pres)
            if a.ndim == 2:
                n_levels = a.shape[1]
            elif a.ndim == 1:
                n_levels = a.shape[0]
        else:
            # fallback: try TEMP or PSAL
            for cand in (temp, psal):
                if cand is not None:
                    a = np.array(cand)
                    n_levels = a.shape[1] if a.ndim == 2 else a.shape[0]
                    break

        for i in range(n_levels):
            pres_v = safe_get(pres, i)
            temp_v = safe_get(temp, i)
            psal_v = safe_get(psal, i)

            pres_adj_v = safe_get(pres_adj, i)
            pres_adj_err_v = safe_get(pres_adj_err, i)
            temp_adj_v = safe_get(temp_adj, i)
            temp_adj_err_v = safe_get(temp_adj_err, i)
            psal_adj_v = safe_get(psal_adj, i)
            psal_adj_err_v = safe_get(psal_adj_err, i)

            pres_qc_v = decode_qc(pres_qc, i)
            temp_qc_v = decode_qc(temp_qc, i)
            psal_qc_v = decode_qc(psal_qc, i)

            # skip completely NaN rows
            if all(v is None for v in (pres_v, temp_v, psal_v, pres_adj_v, temp_adj_v, psal_adj_v)):
                continue

            cur.execute("""
                INSERT INTO measurements
                (profile_id, level_index, pres, pres_qc, pres_adjusted, pres_adjusted_error,
                 temp, temp_qc, temp_adjusted, temp_adjusted_error,
                 psal, psal_qc, psal_adjusted, psal_adjusted_error)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (profile_id, level_index) DO UPDATE
                    SET pres = COALESCE(EXCLUDED.pres, measurements.pres),
                        temp = COALESCE(EXCLUDED.temp, measurements.temp),
                        psal = COALESCE(EXCLUDED.psal, measurements.psal)
            """, (
                profile_id, i,
                pres_v, pres_qc_v, pres_adj_v, pres_adj_err_v,
                temp_v, temp_qc_v, temp_adj_v, temp_adj_err_v,
                psal_v, psal_qc_v, psal_adj_v, psal_adj_err_v
            ))

        conn.commit()
        cur.close()
        ds.close()
    except Exception as e:
        print(f"⚠️ Error inserting measurements for profile {file_path}: {e}")

def fill_measurements():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_measurements_table(conn)
    cur = conn.cursor()
    # profiles may have file_name stored
    cur.execute("SELECT profile_id, float_id, file_name FROM profiles JOIN floats USING(float_id)")
    rows = cur.fetchall()
    for profile_id, float_id, file_name in rows:
        # resolve file path
        float_dir = os.path.join(BASE_DIR, str(float_id))  # note: float_id may be numeric id not wmo; prefer to use wmo id stored earlier
        # Instead, query wmo_id per float_id
        # We'll get wmo from DB
        cur2 = conn.cursor()
        cur2.execute("SELECT wmo_id FROM floats WHERE float_id=%s", (float_id,))
        res = cur2.fetchone()
        cur2.close()
        if not res:
            continue
        wmo = res[0]
        file_path = os.path.join(BASE_DIR, str(wmo), "profiles", file_name)
        if not os.path.exists(file_path):
            # fallback - sometimes file is in top-level float dir
            fallback = os.path.join(BASE_DIR, str(wmo), file_name)
            if os.path.exists(fallback):
                file_path = fallback
            else:
                continue
        insert_measurements_for_profile(conn, profile_id, file_path)
    cur.close()
    conn.close()
    print("✅ Measurements seeded.")

if __name__ == "__main__":
    fill_measurements()