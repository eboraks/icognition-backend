
import json
import re
from datetime import datetime
from datetime import timedelta
from typing import Optional
import google.generativeai as genai
from google.generativeai import caching, chat_async
from pydantic import BaseModel
import app.getters as getter
import asyncio
import pprint
import os


GCP_KEY = os.getenv("GCP_AI_KEY")

_model_name = "gemini-1.5-flash-001"  # "gemini-1.5-pro-001"


class citation(BaseModel):
    start_str: str
    end_str: str
    start_index: int
    end_index: int


class QuestionAnswer(BaseModel):
    question: str
    answer: str
    citiation: list[citation]


class Topic(BaseModel):
    name: str
    description: str
    type: str

class Entity(BaseModel):
    name: str
    description: str
    type: str

class AggResponse(BaseModel):
    topics: list[Topic]
    entities: list[Entity]


async def generate_response(messages):
    response = await chat_async.generate(model="gemini-pro", messages=messages)
    return response.candidates[0].message

def create_cache(_content):
     return caching.CachedContent.create(model=_model_name,
                                    system_instruction="You are a researcher task with answering questions about an articles",
                                    contents=_content, 
                                    ttl=timedelta(minutes=10),)

class Citation(BaseModel):
    start_str: str
    end_str: str


class SummarizePrompt(BaseModel):
    """
    Prompt model for summarizing an article
    """

    what_this_article_is_about: Optional[str]
    key_learning_from_article: Optional[str]
    key_points: Optional[list[str]]
    citations_sentances: Optional[list[Citation]]


class ArticleSummary(BaseModel):
    what_article_is_about: str
    key_learning_from_article: str
    key_points: list[str]


class ArticlesSummaries(BaseModel):
    summaries: list[ArticleSummary]

async def generate_summary(text: str):

    genai.configure(api_key=GCP_KEY)
    model = genai.GenerativeModel(_model_name )

    response = await model.generate_content_async(
        """You are a researcher tasked with summarizing the an article into what the article is about, key learnings and key points. 
            Article: """ + text, 
            generation_config={"response_mime_type": "application/json",  "response_schema": SummarizePrompt})
    
    print(response.text)
    answers = SummarizePrompt.model_validate_json(response.text)

    print(answers)

    
        

    


async def find_questions_and_answers():

    model = genai.GenerativeModel(_model_name )

    response = await model.generate_content_async(
        "You are a researcher tasked with identifying the important questions and answers an article(s) address. Article: " + doc.original_text, 
            generation_config={"response_mime_type": "application/json",  "response_schema": list[QuestionAnswer]})
    
    responses = json.loads(response.text)

    for r in responses:
        print(r['question'])
        print(r['answer'])
        citation = r['citiation']
        for c in citation:
            print(f"Start: {c['start_str']}")
            print(f"End: {c['end_str']}")
            
            
        print("\n")


def save_doc_text(document_id: int):

    doc = getter.get_document_by_id(document_id)

    with open(f"data/{doc.title}.txt", "w") as f:
        f.write(f"{doc.title}\n")
        f.write(f"{doc.original_text}\n")


async def main():

    docs_ids = [120, 121, 122, 123, 124]

    for doc_id in docs_ids:
        save_doc_text(doc_id)
    # doc = getter.get_document_by_id(109)

    # models/gemini-1.0-pro-latest, models/gemini-1.5-pro-latest
    # model = genai.GenerativeModel(_model_name )
    
    # await generate_summary(doc.original_text)
        
if __name__ == "__main__":
    start_time = datetime.now()
    asyncio.run(main())
    end_time = datetime.now()
    print('Duration: {}'.format(end_time - start_time))