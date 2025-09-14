"""
seed_profiles.py
Seeds profile-level metadata from NetCDF files.
Fixed juld extraction and date handling.
"""

import os
import psycopg2
import xarray as xr
import numpy as np
from datetime import datetime, timedelta
import re
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

def ensure_profiles_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        profile_id SERIAL PRIMARY KEY,
        float_id INT REFERENCES floats(float_id) ON DELETE CASCADE,
        cycle_number INT,
        direction VARCHAR(4),
        juld TIMESTAMP,
        juld_qc VARCHAR(5),
        juld_location TIMESTAMP,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        position_qc VARCHAR(5),
        data_mode VARCHAR(5),
        vertical_sampling_scheme TEXT,
        date_creation TIMESTAMP,
        date_update TIMESTAMP,
        file_name TEXT,
        UNIQUE(float_id, cycle_number)
    );
    """)
    conn.commit()
    cur.close()

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

def extract_juld(ds, varname="JULD"):
    """Extract JULD from NetCDF robustly - handle both scalar and array values"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle different dimensionalities
        if var_data.dims == ('N_PROF',):
            # Array with one value per profile
            val = var_data.values[0] if len(var_data.values) > 0 else None
        else:
            # Scalar value
            val = var_data.values.item() if var_data.values.size == 1 else var_data.values
        
        if val is None or np.ma.is_masked(val) or np.isnan(val):
            return None
        
        # Convert to float and handle large values
        val = float(val)
        
        # Handle Julian date conversion (nanoseconds since 1950-01-01)
        base_date = datetime(1950, 1, 1)
        try:
            # For very large values (~1.75e+18) - these are NANOSECONDS
            if val > 1e17:  # Nanoseconds range
                # Convert nanoseconds to days: 1 day = 86400 * 1e9 nanoseconds
                days = val / (86400.0 * 1e9)
                return base_date + timedelta(days=days)
            else:  # Assume days (standard Argo format)
                return base_date + timedelta(days=val)
        except (ValueError, OverflowError):
            print(f"Warning: Invalid Julian date value {val} for {varname}")
            return None
            
    except Exception as e:
        print(f"Error extracting {varname}: {e}")
        return None

def safe_get_scalar(ds, varname, decoder=None, index=0):
    """Extract a single value safely with optional index for arrays"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle array variables
        if var_data.dims and len(var_data.dims) > 0:
            if var_data.dims[0] == 'N_PROF' and len(var_data.values) > index:
                raw = var_data.values[index]
            else:
                raw = var_data.values
        else:
            raw = var_data.values
        
        if raw is None or (hasattr(raw, 'size') and raw.size == 0):
            return None
        
        # Handle masked arrays
        if np.ma.is_masked(raw):
            return None
        
        # Handle scalar values
        if hasattr(raw, 'item'):
            raw = raw.item()
        
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

def insert_profile(conn, float_id, file_path, file_name):
    """Insert a single profile. Commits per file."""
    try:
        ds = xr.open_dataset(file_path)
        cur = conn.cursor()

        # Get platform number to verify we're processing the right float
        platform_number = safe_get_scalar(ds, "PLATFORM_NUMBER", decode_char_array)
        if platform_number:
            platform_number = platform_number.strip()
        
        cycle_number = safe_get_scalar(ds, "CYCLE_NUMBER")
        direction = safe_get_scalar(ds, "DIRECTION", decode_char_array)
        juld = extract_juld(ds, "JULD")
        juld_qc = safe_get_scalar(ds, "JULD_QC", decode_char_array)
        juld_location = extract_juld(ds, "JULD_LOCATION")
        latitude = safe_get_scalar(ds, "LATITUDE")
        longitude = safe_get_scalar(ds, "LONGITUDE")
        position_qc = safe_get_scalar(ds, "POSITION_QC", decode_char_array)
        data_mode = safe_get_scalar(ds, "DATA_MODE", decode_char_array)
        vss = safe_get_scalar(ds, "VERTICAL_SAMPLING_SCHEME", decode_char_array)

        # Handle global attributes
        date_creation = parse_argo_date(ds.attrs.get("DATE_CREATION"))
        date_update = parse_argo_date(ds.attrs.get("DATE_UPDATE"))

        print(f"Processing: {file_name}, Cycle: {cycle_number}, JULD: {juld}")

        cur.execute("""
            INSERT INTO profiles
            (float_id, cycle_number, direction, juld, juld_qc, juld_location,
             latitude, longitude, position_qc, data_mode, vertical_sampling_scheme,
             date_creation, date_update, file_name)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (float_id, cycle_number) DO UPDATE
            SET direction = COALESCE(EXCLUDED.direction, profiles.direction),
                juld = COALESCE(EXCLUDED.juld, profiles.juld),
                juld_qc = COALESCE(EXCLUDED.juld_qc, profiles.juld_qc),
                juld_location = COALESCE(EXCLUDED.juld_location, profiles.juld_location),
                latitude = COALESCE(EXCLUDED.latitude, profiles.latitude),
                longitude = COALESCE(EXCLUDED.longitude, profiles.longitude),
                position_qc = COALESCE(EXCLUDED.position_qc, profiles.position_qc),
                data_mode = COALESCE(EXCLUDED.data_mode, profiles.data_mode),
                vertical_sampling_scheme = COALESCE(EXCLUDED.vertical_sampling_scheme, profiles.vertical_sampling_scheme),
                date_creation = COALESCE(EXCLUDED.date_creation, profiles.date_creation),
                date_update = COALESCE(EXCLUDED.date_update, profiles.date_update),
                file_name = COALESCE(EXCLUDED.file_name, profiles.file_name);
        """, (float_id, cycle_number, direction, juld, juld_qc, juld_location,
              latitude, longitude, position_qc, data_mode, vss,
              date_creation, date_update, file_name))

        conn.commit()
        cur.close()
        ds.close()
        
    except Exception as e:
        print(f"⚠️ Error inserting profile {file_path}: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()

def fill_profiles():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_profiles_table(conn)

    cur = conn.cursor()
    cur.execute("SELECT float_id, wmo_id FROM floats")
    floats = cur.fetchall()
    cur.close()

    for float_id, wmo in floats:
        print(f"Processing float: {wmo}")
        
        # Check both possible directory structures
        profiles_dir = os.path.join(BASE_DIR, str(wmo), "profiles")
        if not os.path.isdir(profiles_dir):
            profiles_dir = os.path.join(BASE_DIR, str(wmo))
            if not os.path.isdir(profiles_dir):
                print(f"Directory not found for WMO {wmo}")
                continue

        # Process all NetCDF files
        nc_files = [f for f in os.listdir(profiles_dir) if f.endswith('.nc')]
        print(f"Found {len(nc_files)} NetCDF files for WMO {wmo}")
        
        for fname in nc_files:
            file_path = os.path.join(profiles_dir, fname)
            print(f"  Processing: {fname}")
            insert_profile(conn, float_id, file_path, fname)

    conn.close()
    print("✅ Profiles seeding completed.")

if __name__ == "__main__":
    fill_profiles()