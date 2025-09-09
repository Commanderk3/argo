To create floats id table :
```sql
CREATE TABLE floats (
    float_id SERIAL PRIMARY KEY,
    wmo_id VARCHAR(10) UNIQUE NOT NULL,
    dac_center VARCHAR(50),
    platform_type VARCHAR(50),
    project_name TEXT,
    pi_name TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

To create profiles table:
```sql
CREATE TABLE profiles (
    profile_id SERIAL PRIMARY KEY,
    float_id INT REFERENCES floats(float_id),
    cycle_number INT,
    juld TIMESTAMP,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    direction CHAR(1),
    data_mode CHAR(1),  -- R or D
    vertical_sampling_scheme TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

To create measurements table :
```sql
CREATE TABLE measurements (
    measurement_id SERIAL PRIMARY KEY,
    profile_id INT REFERENCES profiles(profile_id),
    level_index INT,          -- depth row number
    pres REAL,
    temp REAL,
    psal REAL,
    pres_qc CHAR(1),
    temp_qc CHAR(1),
    psal_qc CHAR(1)
);
```

# 🔗 Relationships

**floats → profiles**

- One float (WMO ID) produces many profiles over its lifetime.
- Relationship: floats.float_id (PK) ↔ profiles.float_id (FK)

One-to-Many

**profiles → measurements**

- One profile file (e.g. R1900121_001.nc) contains many depth measurements (PRES/TEMP/PSAL rows).
- Relationship: profiles.profile_id (PK) ↔ measurements.profile_id (FK)

One-to-Many