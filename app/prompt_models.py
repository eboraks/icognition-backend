import re
from typing import Optional, List, Dict
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
        entities = []
        temps = [Entity(**entity.model_dump()) for entity in self.entities_and_topics]
        for temp in temps:
            ## temp.name doesn't alreasy exist in entities entity.name
            if temp.name not in [entity.name for entity in entities]:
                entities.append(temp)

        return entities

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

        _user_content_2_task = """Use the examples above to identify the ten most important entities and topic 
            mentioned in the article. Include short description of each. Deduplicate entities and topics using the name field. 
            Here are some examples of entities and topics types:  
                entities: (companies, people, location, event, products....), 
                topics: (marketing, politics, business strategy)
                theories: (free markets capatalism, gender dynamics...)
            Use the JSON format above to output your answer. Only output valid JSON format. 
            Reduce the length of the answer to make sure the JSON is valid."""

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
                "whatThisArticleIsAbout" : "This blog post is about the importance of mobile game soft launch",
                "oneSentenceSummary" : "Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "summaryInNumericBulletPoints" : [
                "1. Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "2. Getting soft launch require planning, strategy and expirements.",
                ],
            }}"""

        _user_content_2_task = """Use the examples above to answer the following questions.
        1. One short sentance explaining what the article is about, and what can be learned from it. 
        2. Summarize the article in one sentence. Limit the answer to twenty words.
        3. Summarize the article up to six bullet-points. Weave into the points entities that are the subject of the article and key learnings. Each point should have up to tweenty words. 
        Keep a ratio of 1:2 between bullet points and paragraphs.
        
        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]
    

class DocumentPromptVerbatim(DocumentPrompt):
    
    whatThisArticleIsAbout: Optional[str]
    oneSentenceSummary: Optional[str] 
    summaryInNumericBulletPoints: Optional[List[str]]
    ## bulletPointsSourceLocation: Optional[List[list[int]]]
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
        bullet_points = [point.bullet_point.strip() for point in self.summaryInNumericBulletPoints]
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
                "whatThisArticleIsAbout" : "This blog post is about the importance of mobile game soft launch",
                "oneSentenceSummary" : "Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                "summaryInNumericBulletPoints" : [
                    "Mobile game soft launch is a process of releasing a game to a limited audience for testing.",
                    "bullet_point": "Getting soft launch require planning, strategy and expirements.",
                    ],
            }}"""

        _user_content_2_task = """Use the examples above to answer the following questions.
        1. One short sentance explaining what the article is about, and what can be learned from it. 
        2. Summarize the article in one sentence. Limit the answer to twenty words.
        3. Summarize the article up to six bullet-points. Weave into the points entities that are the subject of the article and key learnings. 
        Include the source_location of the bullet points in the artilce with the index of where the text start and end. Each point should have up to tweenty words.
        Each point should have up to tweenty words. Keep a ratio of 1:2 between bullet points and paragraphs.
        
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
        Come up with a name that describe the topic in the sentences. If the topic name is a proper noun then include common noun to describe what the proper noun is. 
        Also, include description of the topic and key words that are mention in the subtopics. Use the previous JSON output example. 
        
        Here are some examples:
        The topic name needs to aggregate and describe the information from the subtopics. Here are some examples:  
        Sentences: 
        - distraction-free virtual meetings - Virtual meetings that are free from distractions and interruptions
        - distraction-free meetings - Meetings that are free from distractions and interruptions, allowing for better engagement and productivity
        - virtual meetings - Meetings held through video conferencing technology
        Answer: Topic name "Virtual Meeting Management"

        Sentences:
        Vector indexes - Vector indexes are a way of organizing and searching for vectors in a high-dimensional space, based on their similarity to a given query vector.
        Vector search retrieval methods - Vector search retrieval methods are a way of searching for information based on the similarity of vectors in a high-dimensional space.
        vector database - A vector database is a type of database that stores and retrieves vector data, which can be used for semantic search and other machine learning tasks 
        Answer: Vector Databases
        
        Use the JSON format above to output your answer. Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid."""

        _user_content_3_subtopics = """Subtopics: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_subtopics}
        ]
    
class RAGPrompt(BaseModel):
    """
    Model for subtopic prompts.
    """

    answer: str
    document_ids_used_for_answer: list[int]
    usage: str | None
    
    @classmethod
    def get_messages(cls, contexts: list[str], question: str):
        """
        Get the list of messages for the subtopic prompt.

        Args:
            body (str): The body of the document.

        Returns:
            list[dict]: The list of messages for the subtopic prompt.
        """
        _system_content = """You are a researcher task with answering questions using articles.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_instructions = """Using the following article(s), answer the question. If possible answer using multiple articles that best answer the question. 
        Format the answer with html tags (p, li, br, href links) make the answer readable in a webpage.  
        Include the source article(s) in the answer as <a href> link using Article_Name and URL. 
        Use the field 'document_ids_used_for_answer' to report Article_ID used to answer the question."""
        
        _user_context = "Articles:\n"
        for c in contexts:
            _user_context += """Article_ID: {ID}, Article_Name: {TITLE}, Article: {CONTEXT}\n""".format(
                ID=c['doc_id'], TITLE=c['doc_title'], CONTEXT=c['text'], URL=c['url'])

        _user_question = """Question: {QUESTION}""".format(QUESTION=question)

        
        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_instructions},
            {"role": "user", "content": _user_context},
            {"role": "user", "content": _user_question}
        ]



