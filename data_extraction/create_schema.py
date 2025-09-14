import psycopg2

DB_CONFIG = {
    "dbname": "argo_db",
    "user": "postgres",
    "password": "12345",
    "host": "localhost",
    "port": 5432
}

def create_tables():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # DACS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dacs (
        dac_id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """)

    # FLOATS
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
        launch_date TIMESTAMP,
        launch_latitude DOUBLE PRECISION,
        launch_longitude DOUBLE PRECISION,
        end_mission_date TIMESTAMP,
        created_at TIMESTAMP DEFAULT now()
    );
    """)

    # SENSORS
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
        calib_comment TEXT,
        UNIQUE(float_id, sensor_name, sensor_model)
    );
    """)

    # PROFILES
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
        date_creation TEXT,
        date_update TEXT,
        file_name TEXT,
        UNIQUE(float_id, cycle_number)
    );
    """)

    # MEASUREMENTS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS measurements (
        meas_id SERIAL PRIMARY KEY,
        profile_id INT REFERENCES profiles(profile_id) ON DELETE CASCADE,
        level_index INT,
        pres DOUBLE PRECISION,
        pres_qc VARCHAR(5),
        pres_adjusted DOUBLE PRECISION,
        pres_adjusted_error DOUBLE PRECISION,
        temp DOUBLE PRECISION,
        temp_qc VARCHAR(5),
        temp_adjusted DOUBLE PRECISION,
        temp_adjusted_error DOUBLE PRECISION,
        psal DOUBLE PRECISION,
        psal_qc VARCHAR(5),
        psal_adjusted DOUBLE PRECISION,
        psal_adjusted_error DOUBLE PRECISION,
        UNIQUE(profile_id, level_index)
    );
    """)

    # BGC measurements
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

    # TRAJECTORIES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS trajectories (
        traj_id SERIAL PRIMARY KEY,
        float_id INT REFERENCES floats(float_id) ON DELETE CASCADE,
        juld TIMESTAMP,
        latitude DOUBLE PRECISION,
        longitude DOUBLE PRECISION,
        position_qc VARCHAR(5),
        satellite_name TEXT
    );
    """)

    # QC reference table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS qc_flags (
        qc_code VARCHAR(5) PRIMARY KEY,
        description TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Full schema created (or already existed).")

if __name__ == "__main__":
    create_tables()
