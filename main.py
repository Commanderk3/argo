from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
import psycopg2
from ai.agent import agent_executor

from config import DB_CONFIG

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# request schemas
class QueryRequest(BaseModel):
    query: str
    messages: List[Dict[str, str]]

@app.get("/")
async def root():
    return {"message": "Hello from Argo! Use the /chat endpoint to interact with the database."}    

@app.post("/chat")
async def chat(request: QueryRequest):
    query = request.query.strip()
    raw_messages = request.messages

    if not query:
        return {"error": "Empty query"}

    try:
        # Convert messages to LangChain format for chat history
        chat_history = convert_messages(raw_messages)
        
        # Use the agent to process the query
        result = agent_executor.invoke({
            "input": query,
            "chat_history": chat_history
        })
        
        return {
            "response": result["output"]
        }
    except Exception as e:
        # Handle parsing errors more gracefully
        error_msg = str(e)
        if "Could not parse tool input" in error_msg:
            return {
                "response": "I encountered an issue processing your request. Please try rephrasing your question or ask about something else."
            }
        return {"error": error_msg}

def convert_messages(raw_messages: List[Dict[str, str]]) -> List[BaseMessage]:
    converted = []
    for msg in raw_messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            # For assistant messages, we need to check if they contain tool calls
            # For now, we'll just add them as AIMessages
            converted.append(AIMessage(content=content))
    return converted

# Health check endpoint to verify database connection
@app.get("/health")
async def health_check():
    try:
        # Try to actually connect instead of checking placeholder values
        conn = psycopg2.connect(**DB_CONFIG)
        # Test with a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "healthy", "message": "Database connection successful"}
    except psycopg2.OperationalError as e:
        return {"status": "unhealthy", "message": f"Database connection failed: {str(e)}. Check DB_CONFIG settings."}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Unexpected error: {str(e)}"}