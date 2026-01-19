import nbformat as nbf
import os

notebook_path = '/Users/eboraks/Projects/icognition/notebooks/langgraph_document_processing.ipynb'

with open(notebook_path, 'r') as f:
    nb = nbf.read(f, as_version=4)

# Update cell 1 (imports and setup)
setup_code = """import os
import sys
from typing import List, Dict, TypedDict, Optional, Literal
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
import asyncio

# Add backend to path to import models
sys.path.append(os.path.abspath('../backend'))
from app.models import LLMContentExtraction, PageType
from app.db.database import get_session
from app.services.prompt_service import PromptService
from app.services.prompt_utils import PromptType

# Load environment variables
if os.path.exists('../backend/.env'):
    load_dotenv('../backend/.env')
else:
    load_dotenv('.env')

api_key = os.getenv("GOOGLE_API_KEY")
llm_model_name = os.getenv("GEMINI_FLASH_MODEL")
if not api_key:
    print(\"WARNING: GOOGLE_API_KEY not found!\")

# Initialize LLM
llm = ChatGoogleGenerativeAI(model=llm_model_name, google_api_key=api_key)

# Helper to get prompts from DB
async def get_db_prompt(prompt_type: str):
    async for session in get_session():
        service = PromptService(session)
        return await service.get_latest_prompt(prompt_type)
"""

# Find cell by content or index. Cell 1 is index 1 (usually)
nb.cells[1].source = setup_code

# Update classifier node (index 4 in the original file I saw)
# Let's find cells by their content to be safe

classifier_code = """classifier_llm = llm.with_structured_output(DocTypeResult)

async def classify_doc(state: AgentState):
    print(\"--- CLASSIFYING DOCUMENT ---\")
    content = state[\"content\"]
    title = state.get(\"title\", \"\")
    
    # Create a list of allowed categories for the prompt
    categories = [e.value for e in PageType]
    
    # Fallback if classification prompt not in DB
    system_prompt = f\"You are an expert content classifier. Identify the type of document provided.\\\\nAllowed categories: {', '.join(categories)}.\"
    user_template = \"Title: {title}\\\\n\\\\nContent: {content}\"

    # Try to load from DB
    db_prompt = await get_db_prompt(\"Doc Analysis: Classifier\") # Assuming we'll add this type
    if db_prompt:
        system_prompt = db_prompt.system_prompt or system_prompt
        user_template = db_prompt.user_prompt or user_template
    
    prompt = ChatPromptTemplate.from_messages([
        (\"system\", system_prompt),
        (\"user\", user_template)
    ])
    
    result = await classifier_llm.ainvoke(prompt.format(content=content[:4000], title=title))
    print(f\"Classified as: {result.category} ({result.reasoning})\")
    
    return {\"doc_type\": result.category}"""

# Update specialized nodes (index 6)
specialized_nodes_code = """extraction_llm = llm.with_structured_output(LLMContentExtraction)

async def process_with_db_prompt(state: AgentState, prompt_type: str, agent_name: str):
    print(f\"--- PROCESSING AS {agent_name.upper()} ---\")
    content = state[\"content\"]
    title = state.get(\"title\", \"Untitled\")
    
    db_prompt = await get_db_prompt(prompt_type)
    if db_prompt:
        system_prompt = db_prompt.system_prompt or \"You are a helpful assistant.\"
        user_template = db_prompt.user_prompt
        try:
            user_prompt = user_template.format(content=content, title=title)
        except (KeyError, ValueError):
            user_prompt = f\"{user_template}\\\\n\\\\nContent: {content}\"
        
        prompt = ChatPromptTemplate.from_messages([
            (\"system\", system_prompt),
            (\"user\", user_prompt)
        ])
    else:
        # Fallback to hardcoded logic if DB fails
        prompt = ChatPromptTemplate.from_messages([
            (\"system\", f\"You are a {agent_name} analyst.\"),
            (\"user\", f\"Summarize this {agent_name} content: {content}\")
        ])
        
    result = await extraction_llm.ainvoke(prompt.format())
    result.agent_name = f\"{agent_name}Agent\"
    return {\"extraction\": result}

async def process_news(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_NEWS.value, \"News\")

async def process_blog(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_BLOG.value, \"Blog\")

async def process_product_doc(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_PRODUCT.value, \"ProductDoc\")

async def process_social_media(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_SOCIAL.value, \"SocialMedia\")

async def process_marketing(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_MARKETING.value, \"Marketing\")

async def process_book(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_BOOK.value, \"Book\")

async def process_generic(state: AgentState):
    return await process_with_db_prompt(state, PromptType.EXTRACT_GENERIC.value, \"Generic\")"""

# Update test calls to be async (index 8 and 10)
# Actually, I can just use a loop to find and replace

for cell in nb.cells:
    if cell.cell_type == 'code':
        if "classifier_llm = llm.with_structured_output(DocTypeResult)" in cell.source:
            cell.source = classifier_code
        elif "extraction_llm = llm.with_structured_output(LLMContentExtraction)" in cell.source:
            cell.source = specialized_nodes_code
        elif "app.stream(inputs)" in cell.source:
            # Wrap in async if needed, or just change to await if it's in a cell that allows await
            # Top-level await is allowed in some environments, but let's be safe
            cell.source = cell.source.replace("for output in app.stream(inputs):", "async for output in app.astream(inputs):")

with open(notebook_path, 'w') as f:
    nbf.write(nb, f)
