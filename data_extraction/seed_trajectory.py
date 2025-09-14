"""
seed_trajectories.py
Seeds trajectory-level metadata from NetCDF Rtraj files.
Fixed juld extraction with proper handling of different time units.
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

def ensure_traj_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trajectories (
        traj_id SERIAL PRIMARY KEY,
        float_id INT REFERENCES floats(float_id) ON DELETE CASCADE,
        juld TIMESTAMP,
        juld_adjusted TIMESTAMP,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        position_accuracy FLOAT,
        position_qc VARCHAR(5),
        cycle_number INT,
        measurement_code INT,
        satellite_name TEXT,
        pressure FLOAT,
        temperature FLOAT,
        salinity FLOAT,
        file_name TEXT
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

def extract_juld_value(val, varname=""):
    """Extract Julian date from value with proper unit handling"""
    if val is None or np.ma.is_masked(val) or np.isnan(val):
        return None
    
    try:
        val = float(val)
        
        # Handle different time units based on value magnitude
        base_date = datetime(1950, 1, 1)
        
        # For very large values (~1.75e+18) - these are NANOSECONDS
        if val > 1e17:  # Nanoseconds range
            # Convert nanoseconds to days: 1 day = 86400 * 1e9 nanoseconds
            days = val / (86400.0 * 1e9)
            return base_date + timedelta(days=days)
        elif val > 1e13:  # Likely in microseconds
            return base_date + timedelta(microseconds=val)
        elif val > 1e10:  # Likely in milliseconds
            return base_date + timedelta(milliseconds=val)
        elif val > 1e7:  # Likely in seconds
            # Check if this might be seconds since 1970 (Unix timestamp)
            try:
                return datetime.fromtimestamp(val)
            except:
                # Fall back to days since 1950
                return base_date + timedelta(days=val/86400.0)
        else:  # Assume days since 1950-01-01 (standard Argo format)
            return base_date + timedelta(days=val)
            
    except (ValueError, OverflowError, OSError) as e:
        print(f"Warning: Invalid Julian date value {val} for {varname}: {e}")
        return None
    
def extract_juld(ds, i, varname="JULD"):
    """Robust juld extraction per trajectory index"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle different dimensionalities
        if var_data.dims and 'N_MEASUREMENT' in var_data.dims:
            # Array with one value per measurement
            if i < len(var_data.values):
                val = var_data.values[i]
            else:
                return None
        else:
            # Scalar value or unexpected dimensionality
            val = var_data.values.item() if var_data.values.size == 1 else var_data.values
        
        return extract_juld_value(val, varname)
        
    except Exception as e:
        print(f"Error extracting {varname} at index {i}: {e}")
        return None

def safe_get_numeric(ds, varname, index=0):
    """Extract a numeric value safely with optional index"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle array variables
        if var_data.dims and 'N_MEASUREMENT' in var_data.dims:
            if index < len(var_data.values):
                raw = var_data.values[index]
            else:
                return None
        else:
            # Scalar value
            raw = var_data.values.item() if var_data.values.size == 1 else var_data.values
        
        if raw is None or (hasattr(raw, 'size') and raw.size == 0):
            return None
        
        # Handle masked arrays
        if np.ma.is_masked(raw):
            return None
        
        # Handle scalar values
        if hasattr(raw, 'item'):
            raw = raw.item()
        
        # Convert to float if it's numeric
        if isinstance(raw, (np.integer, int, np.floating, float)):
            return float(raw)
        elif isinstance(raw, (bytes, str)):
            # Handle string/byte representations of numbers
            try:
                if isinstance(raw, bytes):
                    raw_str = raw.decode('utf-8', 'ignore').strip()
                else:
                    raw_str = str(raw).strip()
                
                # Clean up the string
                raw_str = raw_str.replace("b'", "").replace("'", "").strip()
                
                if raw_str and raw_str.lower() != 'nan' and raw_str != '':
                    return float(raw_str)
                else:
                    return None
            except (ValueError, UnicodeDecodeError):
                return None
        else:
            return None
            
    except Exception as e:
        print(f"Warning: Could not get numeric {varname}: {e}")
        return None

def safe_get_value(ds, varname, index=0, decoder=None):
    """Extract a value safely with optional index"""
    if varname not in ds.variables:
        return None
    
    try:
        var_data = ds[varname]
        
        # Handle array variables
        if var_data.dims and 'N_MEASUREMENT' in var_data.dims:
            if index < len(var_data.values):
                raw = var_data.values[index]
            else:
                return None
        else:
            # Scalar value
            raw = var_data.values.item() if var_data.values.size == 1 else var_data.values
        
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

def seed_trajectories():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_traj_table(conn)
    cur = conn.cursor()

    # Get float mapping
    cur.execute("SELECT float_id, wmo_id FROM floats")
    mapping = {str(row[1]): row[0] for row in cur.fetchall()}
    print(f"Found {len(mapping)} floats in database")

    processed_count = 0
    
    for wmo in os.listdir(BASE_DIR):
        float_dir = os.path.join(BASE_DIR, wmo)
        if not os.path.isdir(float_dir):
            continue

        # Find Rtraj file
        rtraj_files = [f for f in os.listdir(float_dir) if f.endswith("_Rtraj.nc")]
        if not rtraj_files:
            print(f"No Rtraj file found for WMO {wmo}")
            continue
        
        rtraj_file = os.path.join(float_dir, rtraj_files[0])
        float_id = mapping.get(wmo)
        
        if not float_id:
            print(f"No float_id found for WMO {wmo}")
            continue

        print(f"Processing trajectory file: {rtraj_file}")

        try:
            with xr.open_dataset(rtraj_file, decode_timedelta=False) as ds:
                # Get number of measurements
                if 'N_MEASUREMENT' in ds.sizes:
                    n_measurements = ds.sizes['N_MEASUREMENT']
                    print(f"Found {n_measurements} measurements in {rtraj_files[0]}")
                else:
                    print(f"No N_MEASUREMENT dimension in {rtraj_files[0]}")
                    continue

                for i in range(n_measurements):
                    # Extract all trajectory data
                    juld = extract_juld(ds, i, "JULD")
                    juld_adjusted = extract_juld(ds, i, "JULD_ADJUSTED")
                    lat = safe_get_numeric(ds, "LATITUDE", i)
                    lon = safe_get_numeric(ds, "LONGITUDE", i)
                    pos_accuracy = safe_get_numeric(ds, "POSITION_ACCURACY", i)
                    pos_qc = safe_get_value(ds, "POSITION_QC", i, decode_char_array)
                    cycle_num = safe_get_numeric(ds, "CYCLE_NUMBER", i)
                    meas_code = safe_get_numeric(ds, "MEASUREMENT_CODE", i)
                    sat_name = safe_get_value(ds, "SATELLITE_NAME", i, decode_char_array)
                    pressure = safe_get_numeric(ds, "PRES", i)
                    temperature = safe_get_numeric(ds, "TEMP", i)
                    salinity = safe_get_numeric(ds, "PSAL", i)

                    # Only insert if we have basic data
                    if juld is not None or lat is not None or lon is not None:
                        cur.execute("""
                            INSERT INTO trajectories 
                            (float_id, juld, juld_adjusted, latitude, longitude, 
                             position_accuracy, position_qc, cycle_number, measurement_code,
                             satellite_name, pressure, temperature, salinity, file_name)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """, (float_id, juld, juld_adjusted, lat, lon, pos_accuracy, 
                              pos_qc, cycle_num, meas_code, sat_name, pressure, 
                              temperature, salinity, rtraj_files[0]))
                
                processed_count += 1
                conn.commit()
                print(f"Processed {n_measurements} measurements from {rtraj_files[0]}")

        except Exception as e:
            print(f"⚠️ Error parsing Rtraj for {wmo}: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()

    cur.close()
    conn.close()
    print(f"✅ Trajectories seeded. Processed {processed_count} files.")

if __name__ == "__main__":
    seed_trajectories()