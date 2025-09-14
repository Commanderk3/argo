import os
import psycopg2
import xarray as xr
import numpy as np
from datetime import datetime
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DAC_BASE_DIR = os.getenv('DAC_BASE_DIR')
DB_CONFIG = {
    "dbname": os.getenv('DB_NAME'),
    "user": os.getenv('DB_USER'),
    "password": os.getenv('DB_PASSWORD'),
    "host": os.getenv('DB_HOST'),
    "port": os.getenv('DB_PORT')
}

def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dacs (
        dac_id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS floats (
        float_id SERIAL PRIMARY KEY,
        wmo_id VARCHAR(50) UNIQUE NOT NULL,
        dac_id INT REFERENCES dacs(dac_id) ON DELETE SET NULL,
        platform_type TEXT,
        float_serial_no TEXT,
        firmware_version TEXT,
        project_name TEXT,
        pi_name TEXT,
        data_centre TEXT,
        wmo_inst_type TEXT,
        launch_date TIMESTAMP,
        launch_latitude DOUBLE PRECISION,
        launch_longitude DOUBLE PRECISION,
        end_mission_date TIMESTAMP,
        created_at TIMESTAMP DEFAULT now()
    );""")
    conn.commit()
    cur.close()

def scan_dacs(base_dir):
    dacs = []
    for dac_name in os.listdir(base_dir):
        dac_path = os.path.join(base_dir, dac_name)
        if not os.path.isdir(dac_path):
            continue
        wmos = [d for d in os.listdir(dac_path) if os.path.isdir(os.path.join(dac_path, d))]
        if wmos:
            dacs.append((dac_name, sorted(wmos, key=lambda x: int(x) if x.isdigit() else x)))
    return dacs

def decode_char_array(arr):
    """Decode byte/string arrays safely"""
    if arr is None:
        return None
    try:
        if hasattr(arr, 'dtype') and arr.dtype.kind in ('S', 'U'):
            if isinstance(arr, np.ndarray):
                # Handle array of bytes/strings
                decoded = []
                for item in arr.ravel():
                    if isinstance(item, bytes):
                        decoded.append(item.decode('utf-8', 'ignore').strip())
                    else:
                        decoded.append(str(item).strip())
                return ' '.join(decoded).replace('\x00', '').strip()
            else:
                return str(arr).replace('\x00', '').strip()
        elif isinstance(arr, bytes):
            return arr.decode('utf-8', 'ignore').strip()
        else:
            return str(arr).strip()
    except Exception as e:
        print(f"Warning: Could not decode {arr}: {e}")
        return str(arr).strip() if arr is not None else None

def safe_get_scalar(ds, varname, decoder=None):
    """Extract a single value safely from NetCDF variables"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle scalar variables
        if var_data.size == 1:
            raw = var_data.values.item()
        else:
            # For arrays, take the first value
            raw = var_data.values[0] if len(var_data.values) > 0 else None
        
        if raw is None:
            return None
        
        # Handle masked arrays
        if np.ma.is_masked(raw):
            return None
        
        # Apply decoder if provided
        if decoder:
            return decoder(raw)
        
        # Return appropriate type
        if isinstance(raw, (np.floating, float)) and np.isnan(raw):
            return None
        elif isinstance(raw, (np.integer, int, float)):
            return float(raw)
        else:
            return str(raw)
            
    except Exception as e:
        print(f"Warning: Could not get {varname}: {e}")
        return None

def parse_argo_date(date_str):
    """Parse Argo date strings in various formats"""
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Remove any null bytes and strip
        date_str = date_str.replace('\x00', '').strip()
        
        # Handle different date formats
        if len(date_str) == 14:  # YYYYMMDDHHMMSS
            return datetime.strptime(date_str, '%Y%m%d%H%M%S')
        elif len(date_str) == 12:  # YYYYMMDDHHMM
            return datetime.strptime(date_str, '%Y%m%d%H%M')
        elif len(date_str) == 8:  # YYYYMMDD
            return datetime.strptime(date_str, '%Y%m%d')
        elif 'T' in date_str:  # ISO format
            return datetime.fromisoformat(date_str.replace('Z', ''))
        else:
            # Try to parse with regex
            match = re.search(r'(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?', date_str)
            if match:
                groups = match.groups()
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                hour = int(groups[3]) if groups[3] else 0
                minute = int(groups[4]) if groups[4] else 0
                second = int(groups[5]) if groups[5] else 0
                return datetime(year, month, day, hour, minute, second)
    except Exception as e:
        print(f"Warning: Could not parse date '{date_str}': {e}")
    
    return None

def extract_float_metadata(meta_file):
    """Read metadata from a NetCDF meta file using proper variable access."""
    data = {}
    
    try:
        with xr.open_dataset(meta_file) as ds:
            # Extract metadata from variables (not global attributes)
            data['platform_type'] = safe_get_scalar(ds, 'PLATFORM_TYPE', decode_char_array)
            data['float_serial_no'] = safe_get_scalar(ds, 'FLOAT_SERIAL_NO', decode_char_array)
            data['firmware_version'] = safe_get_scalar(ds, 'FIRMWARE_VERSION', decode_char_array)
            data['project_name'] = safe_get_scalar(ds, 'PROJECT_NAME', decode_char_array)
            data['pi_name'] = safe_get_scalar(ds, 'PI_NAME', decode_char_array)
            data['data_centre'] = safe_get_scalar(ds, 'DATA_CENTRE', decode_char_array)
            data['wmo_inst_type'] = safe_get_scalar(ds, 'WMO_INST_TYPE', decode_char_array)
            
            # Handle dates - these are usually stored as strings in variables
            launch_date_str = safe_get_scalar(ds, 'LAUNCH_DATE', decode_char_array)
            data['launch_date'] = parse_argo_date(launch_date_str)
            
            end_mission_str = safe_get_scalar(ds, 'END_MISSION_DATE', decode_char_array)
            data['end_mission_date'] = parse_argo_date(end_mission_str)
            
            # Numeric values
            data['launch_latitude'] = safe_get_scalar(ds, 'LAUNCH_LATITUDE')
            data['launch_longitude'] = safe_get_scalar(ds, 'LAUNCH_LONGITUDE')
            
            # Debug: Print what we found
            print(f"Metadata extracted from {os.path.basename(meta_file)}:")
            for key, value in data.items():
                if value is not None:
                    print(f"  {key}: {value}")
            
    except Exception as e:
        print(f"⚠️ Failed to read {meta_file}: {e}")
        import traceback
        traceback.print_exc()
    
    return data

def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_tables(conn)
    cur = conn.cursor()

    dacs = scan_dacs(DAC_BASE_DIR)
    total = 0
    successful = 0
    
    for dac_name, wmos in dacs:
        print(f"Processing DAC: {dac_name} with {len(wmos)} floats")
        
        cur.execute("INSERT INTO dacs (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (dac_name,))
        cur.execute("SELECT dac_id FROM dacs WHERE name=%s;", (dac_name,))
        dac_id = cur.fetchone()[0]

        for wmo in wmos:
            meta_file = os.path.join(DAC_BASE_DIR, dac_name, wmo, f"{wmo}_meta.nc")
            
            if not os.path.exists(meta_file):
                print(f"⚠️ Meta file not found: {meta_file}")
                # Insert basic record anyway
                cur.execute("""
                    INSERT INTO floats (wmo_id, dac_id) VALUES (%s, %s)
                    ON CONFLICT (wmo_id) DO NOTHING;
                """, (wmo, dac_id))
                continue

            print(f"Processing WMO: {wmo}")
            metadata = extract_float_metadata(meta_file)

            try:
                cur.execute("""
                    INSERT INTO floats (
                        wmo_id, dac_id, platform_type, float_serial_no,
                        firmware_version, project_name, pi_name, data_centre,
                        wmo_inst_type, launch_date, launch_latitude, 
                        launch_longitude, end_mission_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (wmo_id) DO UPDATE
                    SET platform_type = COALESCE(EXCLUDED.platform_type, floats.platform_type),
                        float_serial_no = COALESCE(EXCLUDED.float_serial_no, floats.float_serial_no),
                        firmware_version = COALESCE(EXCLUDED.firmware_version, floats.firmware_version),
                        project_name = COALESCE(EXCLUDED.project_name, floats.project_name),
                        pi_name = COALESCE(EXCLUDED.pi_name, floats.pi_name),
                        data_centre = COALESCE(EXCLUDED.data_centre, floats.data_centre),
                        wmo_inst_type = COALESCE(EXCLUDED.wmo_inst_type, floats.wmo_inst_type),
                        launch_date = COALESCE(EXCLUDED.launch_date, floats.launch_date),
                        launch_latitude = COALESCE(EXCLUDED.launch_latitude, floats.launch_latitude),
                        launch_longitude = COALESCE(EXCLUDED.launch_longitude, floats.launch_longitude),
                        end_mission_date = COALESCE(EXCLUDED.end_mission_date, floats.end_mission_date);
                """, (
                    wmo, dac_id,
                    metadata.get('platform_type'),
                    metadata.get('float_serial_no'),
                    metadata.get('firmware_version'),
                    metadata.get('project_name'),
                    metadata.get('pi_name'),
                    metadata.get('data_centre'),
                    metadata.get('wmo_inst_type'),
                    metadata.get('launch_date'),
                    metadata.get('launch_latitude'),
                    metadata.get('launch_longitude'),
                    metadata.get('end_mission_date')
                ))
                
                if any(metadata.values()):  # If we got any metadata
                    successful += 1
                total += 1
                
            except Exception as e:
                print(f"⚠️ Error inserting float {wmo}: {e}")
                conn.rollback()
                # Insert basic record anyway
                cur.execute("""
                    INSERT INTO floats (wmo_id, dac_id) VALUES (%s, %s)
                    ON CONFLICT (wmo_id) DO NOTHING;
                """, (wmo, dac_id))
                conn.commit()

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Inserted/updated {total} floats across {len(dacs)} DACs.")
    print(f"✅ Successfully extracted metadata for {successful} floats.")

if __name__ == "__main__":
    seed()