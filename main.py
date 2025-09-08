import xarray as xr
import pandas as pd
import psycopg2
import numpy as np
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# PostgreSQL settings
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'dbname': 'argo_db',
    'user': 'postgres',
    'password': 'chenn@1'
}

def connect_db():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Database connection established")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return None

def create_table(conn):
    """Create the database table for testing"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DROP TABLE IF EXISTS test_argo_profiles;
                
                CREATE TABLE test_argo_profiles (
                    id SERIAL PRIMARY KEY,
                    platform_number TEXT NOT NULL,
                    cycle_number INTEGER NOT NULL,
                    direction CHAR(1),
                    juld TIMESTAMP NOT NULL,
                    latitude FLOAT NOT NULL,
                    longitude FLOAT NOT NULL,
                    position_qc CHAR(1),
                    profile_pres_qc CHAR(1),
                    profile_temp_qc CHAR(1),
                    profile_psal_qc CHAR(1),
                    pres FLOAT[],
                    pres_qc CHAR(1)[],
                    temp FLOAT[],
                    temp_qc CHAR(1)[],
                    psal FLOAT[],
                    psal_qc CHAR(1)[],
                    file_path TEXT NOT NULL
                );
            """)
            conn.commit()
            logger.info("Created test_argo_profiles table")
            return True
    except Exception as e:
        logger.error(f"Error creating table: {e}")
        return False

def decode_bytes(value):
    """Decode byte strings to regular strings"""
    if isinstance(value, bytes):
        return value.decode('utf-8').strip()
    elif isinstance(value, np.ndarray) and value.dtype.kind in ['S', 'U']:
        return str(value).strip()
    return value

def store_sample_data():
    """Store sample data from the test file"""
    file_path = r"./test/20240101_prof.nc"
    
    # Connect to database
    conn = connect_db()
    if not conn:
        return
    
    if not create_table(conn):
        conn.close()
        return
    
    try:
        with xr.open_dataset(file_path) as ds:
            # Get the number of profiles
            n_profiles = ds.dims['N_PROF']
            logger.info(f"Found {n_profiles} profiles in the test file")
            
            # Store first 5 profiles as sample data
            sample_count = min(5, n_profiles)
            logger.info(f"Storing first {sample_count} profiles as sample data")
            
            success_count = 0
            
            for i in range(sample_count):
                try:
                    # Extract scalar values for this profile
                    platform_number = decode_bytes(ds.PLATFORM_NUMBER.values[i])
                    cycle_number = int(ds.CYCLE_NUMBER.values[i])
                    direction = decode_bytes(ds.DIRECTION.values[i]) if hasattr(ds, 'DIRECTION') else None
                    
                    # Handle JULD (convert to datetime)
                    juld = pd.to_datetime(ds.JULD.values[i])
                    
                    latitude = float(ds.LATITUDE.values[i])
                    longitude = float(ds.LONGITUDE.values[i])
                    
                    # Extract QC values
                    position_qc = decode_bytes(ds.POSITION_QC.values[i]) if hasattr(ds, 'POSITION_QC') else None
                    profile_pres_qc = decode_bytes(ds.PROFILE_PRES_QC.values[i]) if hasattr(ds, 'PROFILE_PRES_QC') else None
                    profile_temp_qc = decode_bytes(ds.PROFILE_TEMP_QC.values[i]) if hasattr(ds, 'PROFILE_TEMP_QC') else None
                    profile_psal_qc = decode_bytes(ds.PROFILE_PSAL_QC.values[i]) if hasattr(ds, 'PROFILE_PSAL_QC') else None
                    
                    # Extract profile data arrays, handling NaN values
                    def extract_profile_data(var_name, i):
                        if hasattr(ds, var_name):
                            data = ds[var_name].values[i]
                            # Convert NaN to None for PostgreSQL, take first 10 values for sample
                            return [float(x) if not pd.isna(x) else None for x in data[:10]]
                        return None
                    
                    pres = extract_profile_data('PRES', i)
                    temp = extract_profile_data('TEMP', i)
                    psal = extract_profile_data('PSAL', i)
                    
                    # Extract QC arrays (first 10 values)
                    def extract_qc_data(qc_name, i):
                        if hasattr(ds, qc_name):
                            qc_data = ds[qc_name].values[i]
                            # Convert bytes to strings and handle NaN
                            return [decode_bytes(x) if not pd.isna(x) else None for x in qc_data[:10]]
                        return None
                    
                    pres_qc = extract_qc_data('PRES_QC', i)
                    temp_qc = extract_qc_data('TEMP_QC', i)
                    psal_qc = extract_qc_data('PSAL_QC', i)
                    
                    # Insert the profile
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO test_argo_profiles (
                                platform_number, cycle_number, direction, juld, latitude, longitude,
                                position_qc, profile_pres_qc, profile_temp_qc, profile_psal_qc,
                                pres, pres_qc, temp, temp_qc, psal, psal_qc, file_path
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            platform_number, cycle_number, direction, juld, latitude, longitude,
                            position_qc, profile_pres_qc, profile_temp_qc, profile_psal_qc,
                            pres, pres_qc, temp, temp_qc, psal, psal_qc, file_path
                        ))
                    
                    success_count += 1
                    logger.info(f"Stored profile {i+1}: {platform_number}, cycle {cycle_number}")
                    
                except Exception as e:
                    logger.error(f"Error processing profile {i}: {e}")
                    continue
            
            conn.commit()
            logger.info(f"Successfully stored {success_count} sample profiles")
            
            # Display the stored data
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT platform_number, cycle_number, juld, latitude, longitude 
                    FROM test_argo_profiles 
                    ORDER BY id
                """)
                results = cur.fetchall()
                
                print("\n=== STORED SAMPLE DATA ===")
                for i, row in enumerate(results, 1):
                    print(f"Profile {i}: Platform {row[0]}, Cycle {row[1]}, Date {row[2]}, Location ({row[3]:.4f}, {row[4]:.4f})")
            
            return True
            
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        return False
    finally:
        conn.close()
        logger.info("Database connection closed")

if __name__ == "__main__":
    store_sample_data()