import psycopg2
import pandas as pd

from langchain_core.tools import tool
from config import DB_CONFIG

# Define the SQL query tool
@tool
def execute_sql_query(sql_query: str) -> str:
    """
    Execute a SQL query on the Argo database and return the results.
    Use this when you need to retrieve specific data from the database.
    """
    try:
        # Connect to the database - let the connection attempt determine if config is valid
        conn = psycopg2.connect(**DB_CONFIG)
        
        # Execute the query
        df = pd.read_sql_query(sql_query, conn)
        
        # Close the connection
        conn.close()
        
        if df.empty:
            return "Query executed successfully but returned no results."
        
        # Convert to string for response
        result_str = f"Query returned {len(df)} rows.\n\nFirst 50 rows:\n{df.head(50).to_string()}"
        return result_str
        
    except psycopg2.OperationalError as e:
        return f"Database connection error: {str(e)}. Please check your database configuration in DB_CONFIG and ensure PostgreSQL is running."
    except Exception as e:
        return f"Error executing query: {str(e)}"