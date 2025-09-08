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

def insert_measurements(conn, profile_id, file_path):
    """Extract PRES/TEMP/PSAL (+ QC) and insert into DB."""
    try:
        ds = xr.open_dataset(file_path)

        pres = ds["PRES"].values[0] if "PRES" in ds else []
        temp = ds["TEMP"].values[0] if "TEMP" in ds else []
        psal = ds["PSAL"].values[0] if "PSAL" in ds else []

        pres_qc = ds["PRES_QC"].values[0].astype(str) if "PRES_QC" in ds else []
        temp_qc = ds["TEMP_QC"].values[0].astype(str) if "TEMP_QC" in ds else []
        psal_qc = ds["PSAL_QC"].values[0].astype(str) if "PSAL_QC" in ds else []

        cur = conn.cursor()
        for i in range(len(pres)):
            # Skip missing data (NaNs)
            if pres[i] is None or (str(pres[i]) == "nan"):
                continue

            cur.execute(
                """
                INSERT INTO measurements 
                (profile_id, level_index, pres, temp, psal, pres_qc, temp_qc, psal_qc)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s);
                """,
                (
                    profile_id,
                    i,
                    float(pres[i]) if str(pres[i]) != "nan" else None,
                    float(temp[i]) if str(temp[i]) != "nan" else None,
                    float(psal[i]) if str(psal[i]) != "nan" else None,
                    pres_qc[i][0] if len(str(pres_qc[i])) > 0 else None,
                    temp_qc[i][0] if len(str(temp_qc[i])) > 0 else None,
                    psal_qc[i][0] if len(str(psal_qc[i])) > 0 else None,
                )
            )

        cur.close()
        ds.close()

    except Exception as e:
        print(f"⚠️ Error inserting measurements from {file_path}: {e}")

def fill_measurements():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT profile_id, file_name, wmo_id FROM profiles JOIN floats USING(float_id)")
    profiles = cur.fetchall()

    for profile_id, file_name, wmo_id in profiles:
        file_path = os.path.join(BASE_DIR, str(wmo_id), "profiles", file_name)
        if os.path.exists(file_path):
            insert_measurements(conn, profile_id, file_path)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Measurements inserted into DB")

if __name__ == "__main__":
    fill_measurements()
