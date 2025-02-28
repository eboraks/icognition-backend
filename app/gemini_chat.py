import asyncio
import json
import os
from pydantic import BaseModel
from google import genai
from google.genai.types import (
    CreateBatchJobConfig,
    CreateCachedContentConfig,
    EmbedContentConfig,
    FunctionDeclaration,
    GenerateContentConfig,
    Part,
    SafetySetting,
    Tool,
)

def load_schema_rdf() -> str:
    """Load the schema.org RDF file into a string"""
    try:
        with open('data/simple_schemaorg.rdf', 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading schema RDF: {str(e)}")
        return ""

# Load schema RDF into a string constant
SCHEMA_RDF = load_schema_rdf()

def load_contect_types() -> str:
    """Load the content types file into a string"""
    try:
        with open('data/content_types.json', 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading content types: {str(e)}")
        return ""

# Load content types into a string constant
CONTENT_TYPES = load_contect_types()

from app.getters import get_source_by_id

source = get_source_by_id("dc046e93-932d-414e-9d26-8682eb1388fb")

print(source.html_root_element)

client = genai.Client(api_key=os.getenv("GCP_AI_KEY"))

model_name = "models/gemini-2.0-flash"

system_instruction = """
  You are a research assistant that can help with analysis of the provided text.
  You will be provided with a text or HTML and you will need to extract information and analyze it and provide insights about the content.
"""

class Answer(BaseModel):
    long_answer: str
    short_answer: str
    citations: list[str]
    
class ContentType(BaseModel):
    content_type: str

class Topic(BaseModel):
    topics: list[str]
    
class Graph(BaseModel):
    subject: str
    predicate: str
    object: str
    

class Graphs(BaseModel):
    graphs: list[Graph]
    
class Type(BaseModel):
    type: str
    name: str
    description: str

class Types(BaseModel):
    types: list[Type]


async def process():
    chat = client.chats.create(model = model_name, 
                            config = GenerateContentConfig(
                                    system_instruction = system_instruction,
                                    response_mime_type = "application/json",
                                    response_schema = Answer,
                                    temperature = 0.5))

    response = chat.send_message("This is the content we are going to analyze: " + source.html_root_element)

    
    response = chat.send_message("Cateborize the type of the content, is it news article, blog post, product description, etc. Use the following content types as a reference: " + CONTENT_TYPES, 
                                    config = GenerateContentConfig(
                                    response_mime_type = "application/json",
                                    response_schema = Answer,
                                    temperature = 0.5))

    print('Content type:')
    answer = Answer.model_validate_json(response.text)
    print(answer.model_dump_json(indent=2))
    
    response = chat.send_message("What is the main idea, message or topic of the content?", config = GenerateContentConfig(
                                    response_mime_type = "application/json",
                                    response_schema = Answer,
                                    temperature = 0.5))
    
    
    print('Main idea:')
    answer = Answer.model_validate_json(response.text)
    print(answer.model_dump_json(indent=2))

    response = chat.send_message(f"Identify the types of the entities mentioned in the content using the schema.org RDF file. Describe the type in the context of the content. The schema.org RDF: {SCHEMA_RDF}", config = GenerateContentConfig(
                                     response_mime_type = "application/json",
                                    response_schema = Types,
                                    temperature = 0.5))
    
    print(response.text)
    
    types = json.loads(response.text)
    
    print(types)






## main function    
async def main():
    await process()


if __name__ == "__main__":
    asyncio.run(main())