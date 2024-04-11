import re
from sqlmodel import SQLModel, Field, ARRAY, Float, JSON, Integer, Relationship, String
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import TEXT, JSONB
from pgvector.sqlalchemy import Vector
from typing import Optional, List, Dict
from datetime import datetime
from pydantic import BaseModel

from app.models import Document, Entity, IdentifyEntity

class DocumentPrompt(BaseModel):
    """
    Base class for document prompts.
    """

    @classmethod
    def get_messages(cls, body: str) -> list[dict]:
        """
        Get the list of messages for the document prompt.

        Args:
            body (str): The body of the document.

        Returns:
            list[dict]: The list of messages for the document prompt.
        """
        raise NotImplementedError("Subclass must implement this method")

    def populate_document(cls, document: Document) -> Document:
        """
        Populate the document with the prompt data.

        Args:
            document (Document): The document to populate.

        Returns:
            Document: The populated document.
        """
        raise NotImplementedError("Subclass must implement this method")

    def generate_entities(cls) -> list[Entity]:
        """
        Generate a list of entities based on the prompt data.

        Returns:
            list[Entity]: The list of generated entities.
        """
        raise NotImplementedError("Subclass must implement this method")

class DocumentPromptTwo(DocumentPrompt):
    """
    Subclass of DocumentPrompt for DocumentPromptTwo.
    """

    entities_and_topics: Optional[List[IdentifyEntity]]
    usage: Optional[str]

    def populate_document(cls, document: Document) -> Document:
        """
        Populate the document with the prompt data.

        Args:
            document (Document): The document to populate.

        Returns:
            Document: The populated document.
        """
        document.short_summary = cls.oneSentenceSummary
        document.llm_service_meta = cls.usage

        return document

    def generate_entities(self) -> list[Entity]:
        """
        Generate a list of entities based on the prompt data.

        Returns:
            list[Entity]: The list of generated entities.
        """
        return [Entity(**entity.model_dump()) for entity in self.entities_and_topics]

    @classmethod
    def get_messages(cls, body: str):
        """
        Get the list of messages for the document prompt.

        Args:
            body (str): The body of the document.

        Returns:
            list[dict]: The list of messages for the document prompt.
        """
        _system_content = """You are a researcher task with answering questions about an article.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: {{
            "entities_and_topics" : [
            {{"name": "semiconductor", "type": "industry", "description": "Companies engaged in the design and fabrication of semiconductors and semiconductor devices"}},
            {{"name": "NBA", "type": "sport league", "description": "NBA is the national basketball league"}},
            {{"name": "Ford F150", "type": "vehicle", "description": "Article talks about the Ford F150 truck"}},
            {{"name": "mobile game soft launch", "type": "topic","description": "Mobile game soft launch is a process of releasing a game to a limited audience for testing."}},
            {{"name": "US Civil War", "type": "event", "description": "The American Civil War was a civil war in the United States between the Union and the Confederacy, which had been formed by states that had seceded from the Union. The central cause of the war was the dispute over whether slavery would be permitted to expand into the western territories, leading to more slave states, or be prevented from doing so, which many believed would place slavery on a course of ultimate extinction."}},
            {{"name": "Capitalism", "type": "thoery", "description": Capitalism is an economic system based on the private ownership of the means of production and their operation for profit. Central characteristics of capitalism include capital accumulation, competitive markets, price system, private property, property rights recognition, voluntary exchange, and wage labor."}}
            ]}"""

        _user_content_2_task = """Use the examples above to identify no more then ten entities (companies, people, location, event, products....), 
            topic (marketing, politics, business strategy) and theories (free markets capatalism, gender dynamics...) 
            mentioned in the article. Include short description of each.

        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]

class DocumentPromptOne(DocumentPrompt):
    """
    Subclass of DocumentPrompt for DocumentPromptOne.
    """

    whatThisArticleIsAbout: Optional[str]
    oneSentenceSummary: Optional[str] 
    summaryInNumericBulletPoints: Optional[List[str]]
    usage: Optional[str]

    def populate_document(self, document: Document) -> Document:
        """
        Populate the document with the prompt data.

        Args:
            document (Document): The document to populate.

        Returns:
            Document: The populated document.
        """
        document.is_about = self.whatThisArticleIsAbout
        document.short_summary = self.oneSentenceSummary
        bullet_points = [re.sub(r"[1-9]{,2}\.", "", bullet_point).strip() for bullet_point in self.summaryInNumericBulletPoints]
        document.summary_bullet_points = bullet_points
        document.llm_service_meta = self.usage

        return document

    @classmethod
    def get_messages(cls, body: str):
        """
        Get the list of messages for the document prompt.

        Args:
            body (str): The body of the document.

        Returns:
            list[dict]: The list of messages for the document prompt.
        """
        _system_content = """You are a researcher task with answering questions about an article.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: {{
                "whatThisArticleIsAbout" : "Mobile game soft launch",
                "oneSentenceSummary" : "Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "summaryInNumericBulletPoints" : [
                "1. Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "2. Getting soft launch require planning, strategy and expirements.",
                ],
            }}"""

        _user_content_2_task = """Use the examples above to answer the following questions.
        1. Three to fours words explaining what the article is about.
        2. Summarize the article in one sentence. Limit the answer to twenty words.
        3. Summarize the article up to six bullet-points. Each bullet-point need to have betweeen ten to tweenty words. Limit the number of bullet points must below six.
        
        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]

class SubTopicPrompt(BaseModel):
    """
    Model for subtopic prompts.
    """

    name: str
    description: str
    key_words: list[str] | None
    usage: str | None
    
    @classmethod
    def get_messages(cls, body: str):
        """
        Get the list of messages for the subtopic prompt.

        Args:
            body (str): The body of the document.

        Returns:
            list[dict]: The list of messages for the subtopic prompt.
        """
        _system_content = """You are a language expert responsible to catagorize subtopic sentances into topic. 
            You going to name topics from sentences, and entities you are given.    
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: {{
            "topic" :
            {{"name": "leadership", 
                "description": "Leadership the ability of an individual, group, or organization to "lead", influence, or guide other individuals, teams, or entire organizations."}},
                "key_words": ["leadership", "influence", "guide", "organization", "individual", "team"]
            }}"""

        _user_content_2_task = """Using the following sentences that are in the format of "[NAME] ([TYPE]) [DESCRIPTION]"
        Come up with a name that describe their topic in the sentences. The name should include a noun and a common noun. Also, include description of the topic 
        and key words that are mention in the subtopics. Use the previous JSON output example. 
        
        The topic name needs to aggregate and describe the information from the subtopics. Here are some examples:  
        1. Topic name "Virtual Meeting Management" should be create for the following subtopics:
        - distraction-free virtual meetings - Virtual meetings that are free from distractions and interruptions
        - distraction-free meetings - Meetings that are free from distractions and interruptions, allowing for better engagement and productivity
        - virtual meetings - Meetings held through video conferencing technology
        2. Topic name "Vector Databases" for the following subtopics:
        Vector indexes - Vector indexes are a way of organizing and searching for vectors in a high-dimensional space, based on their similarity to a given query vector.
        Vector search retrieval methods - Vector search retrieval methods are a way of searching for information based on the similarity of vectors in a high-dimensional space.
        vector database - A vector database is a type of database that stores and retrieves vector data, which can be used for semantic search and other machine learning tasks 

        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_subtopics = """Subtopics: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_subtopics}
        ]



