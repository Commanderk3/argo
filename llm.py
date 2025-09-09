import google.generativeai as genai

# ==== CONFIG ====
API_KEY = ""
genai.configure(api_key=API_KEY)

MODEL = "gemini-1.5-flash"

SYSTEM_PROMPT = """
You are an assistant that converts user natural language questions into SQL queries
for a PostgreSQL database with these tables:

floats(float_id, wmo_id, dac_center, platform_type, project_name, pi_name, created_at)
profiles(profile_id, float_id, cycle_number, juld, latitude, longitude, direction, data_mode, vertical_sampling_scheme, file_name, created_at)
measurements(measurement_id, profile_id, level_index, pres, temp, psal, pres_qc, temp_qc, psal_qc)

Rules:
- Always output only a valid SQL query.
- Use proper joins between tables when needed.
- Restrict time to BETWEEN '2000-01-01' AND '2004-12-31' unless user specifies otherwise.
Important: Use profiles.juld for filtering by observation date, not created_at.
"""

def main():
    model = genai.GenerativeModel(MODEL)

    while True:
        user_input = input("\nAsk a question (or type 'exit'): ")
        if user_input.lower() in ["exit", "quit"]:
            break

        response = model.generate_content([SYSTEM_PROMPT, user_input])

        sql_query = response.text.strip()
        # Remove markdown code fences if present
        if sql_query.startswith("```"):
            sql_query = sql_query.strip("`")
            sql_query = sql_query.replace("sql", "", 1).strip()
        
        # Save clean SQL
        with open("query.sql", "w") as f:
            f.write(sql_query)
        

        print("\n✅ SQL query saved to query.sql. Run db_exec.py to execute it.")

if __name__ == "__main__":
    main()
