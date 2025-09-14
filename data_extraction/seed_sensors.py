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

def decode_char_array(arr):
    if arr is None:
        return ""
    try:
        a = np.array(arr)
        if a.dtype.kind in ('S','U'):
            return "".join([b.decode('utf-8','ignore') if isinstance(b,(bytes,bytearray,np.bytes_)) else str(b) for b in a.ravel()]).replace("\x00","").strip()
        return str(np.squeeze(a)).strip()
    except:
        return str(arr).strip()

def ensure_sensors_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sensors (
        sensor_id SERIAL PRIMARY KEY,
        float_id INT REFERENCES floats(float_id) ON DELETE CASCADE,
        sensor_name TEXT,
        sensor_maker TEXT,
        sensor_model TEXT,
        sensor_serial_no TEXT,
        parameter TEXT,
        parameter_units TEXT,
        calib_equation TEXT,
        calib_coefficient TEXT,
        UNIQUE(float_id, sensor_name, sensor_model)
    );
    """)
    conn.commit()
    cur.close()

def find_meta_file(float_dir):
    for fname in os.listdir(float_dir):
        if fname.endswith("_meta.nc"):
            return os.path.join(float_dir, fname)
    return None

def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_sensors_table(conn)
    cur = conn.cursor()

    # Map floats
    cur.execute("SELECT float_id, wmo_id FROM floats")
    mapping = {row[1]: row[0] for row in cur.fetchall()}

    for wmo in os.listdir(BASE_DIR):
        float_dir = os.path.join(BASE_DIR, wmo)
        if not os.path.isdir(float_dir):
            continue
        float_id = mapping.get(wmo)
        if not float_id:
            continue

        meta = find_meta_file(float_dir)
        if not meta:
            continue

        try:
            ds = xr.open_dataset(meta)
            if "SENSOR" in ds.variables:
                sensors = ds.variables["SENSOR"][:]
                makers = ds.variables.get("SENSOR_MAKER", None)
                models = ds.variables.get("SENSOR_MODEL", None)
                serials = ds.variables.get("SENSOR_SERIAL_NO", None)
                params = ds.variables.get("PARAMETER", None)
                units = ds.variables.get("PARAMETER_UNITS", None)
                eqs = ds.variables.get("CALIB_EQUATION", None)
                coefs = ds.variables.get("CALIB_COEFFICIENT", None)

                for idx, s in enumerate(sensors):
                    name = decode_char_array(s)
                    maker = decode_char_array(makers[idx]) if makers is not None else ""
                    model = decode_char_array(models[idx]) if models is not None else ""
                    serial = decode_char_array(serials[idx]) if serials is not None else ""
                    parameter = decode_char_array(params[idx]) if params is not None else ""
                    unit = decode_char_array(units[idx]) if units is not None else ""
                    equation = decode_char_array(eqs[idx]) if eqs is not None else ""
                    coefficient = decode_char_array(coefs[idx]) if coefs is not None else ""

                    cur.execute("""
                        INSERT INTO sensors 
                        (float_id, sensor_name, sensor_maker, sensor_model, sensor_serial_no, parameter, parameter_units, calib_equation, calib_coefficient)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (float_id, sensor_name, sensor_model) DO UPDATE 
                        SET parameter = EXCLUDED.parameter,
                            parameter_units = EXCLUDED.parameter_units,
                            calib_equation = EXCLUDED.calib_equation,
                            calib_coefficient = EXCLUDED.calib_coefficient;
                    """, (float_id, name, maker, model, serial, parameter, unit, equation, coefficient))

            ds.close()
            conn.commit()
        except Exception as e:
            print(f"⚠️ Error parsing meta for {wmo}: {e}")

    cur.close()
    conn.close()
    print("✅ Sensors seeded. All previously NULL calibration columns are now empty strings.")

if __name__ == "__main__":
    seed()