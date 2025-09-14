
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent

from config import EMBEDDING_MODEL, GOOGLE_API_KEY

from sql_executor import execute_sql_query


embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

llm = ChatGoogleGenerativeAI(
    model="models/gemini-2.0-flash",
    google_api_key=GOOGLE_API_KEY,
    temperature=0.7
)


# Database schema information
DB_SCHEMA = """
Database schema for Argo floats:
- floats(float_id, wmo_id, dac_center, platform_type, project_name, pi_name, created_at)
- profiles(profile_id, float_id, cycle_number, juld, latitude, longitude, direction, data_mode, vertical_sampling_scheme, file_name, created_at)
- measurements(measurement_id, profile_id, level_index, pres, temp, psal, pres_qc, temp_qc, psal_qc)

Important notes:
- Use profiles.juld for filtering by observation date, not created_at.
- Time is typically restricted to BETWEEN '2000-01-01' AND '2004-12-31' unless user specifies otherwise.
- Always use proper JOINs between tables when needed.
"""

# Create tools list
tools = [execute_sql_query]

# Create system prompt with database information
system_prompt = f"""You are an assistant for the Argo float database. You help users query information about oceanographic measurements from floats.

{DB_SCHEMA}

Guidelines:
1. Use the execute_sql_query tool when you need to retrieve specific data from the database.
2. For simple questions that don't require data retrieval, answer directly.
3. Always use proper SQL syntax and joins between tables when needed.
4. Be concise but helpful in your responses.
5. If the user asks for data that might be in the database, use the tool to query it.
"""

# Create the prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    ("ai", "{agent_scratchpad}"),
])

# Create the agent
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)