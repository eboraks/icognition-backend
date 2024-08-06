import re
from typing import Optional, List, Dict
from pydantic import BaseModel

from app.models import Answer, Document, Entity

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

    entities_and_topics: Optional[List[Entity]]
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
            mentioned in the article. Include general concise description that isn't specific for this article. Deduplicate entities and topics using the name field. 
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
    

class ResponseWithIndex(BaseModel):
    """
    Model for responses with index.
    """

    answer: str
    sentences_indicies: List[int]
    sentences_relevance_score: Optional[List[float]]

class SourceSentence(BaseModel):
    """
    Model for source sentences.
    """

    indix: int = None
    sentence: str = None
    questions: set[str] = None
    relevance_score: Optional[float] = None
    

class DocumentPromptVerbatim(DocumentPrompt):

    ## Model schema that us used by the json schema
    whatThisArticleIsAbout: Optional[ResponseWithIndex]
    learningsFromTheArticle: Optional[ResponseWithIndex] 
    summaryInBulletPoints: Optional[List[ResponseWithIndex]]
    usage: Optional[str]


    
    def populate_document(self, document: Document) -> Document:
        """
        Populate the document with the prompt data.

        Args:
            document (Document): The document to populate.

        Returns:
            Document: The populated document.
        """
        document.is_about = self.whatThisArticleIsAbout.answer
        document.learning_from_document = self.learningsFromTheArticle.answer
        bullet_points = [re.sub(r"[1-9]{,2}\.", "", bullet_point.answer).strip() for bullet_point in self.summaryInBulletPoints]
        document.summary_bullet_points = bullet_points
        document.llm_service_meta = self.usage


        return document

    def to_answers(self, sentences: List[str]):
        results = {}
        sents = {}

        if self.whatThisArticleIsAbout:

            for sent_index in self.whatThisArticleIsAbout.sentences_indicies:
                if sent_index in sents:
                    sents[sent_index].questions.add("whatThisArticleIsAbout")
                else:
                    sents[sent_index] = SourceSentence(indix=sent_index, sentence=sentences[sent_index], questions={"whatThisArticleIsAbout"})
 
            answer = Answer(question="What is this article about?", answer=self.whatThisArticleIsAbout.answer)
            results["whatThisArticleIsAbout"] = answer
        
        if self.learningsFromTheArticle:

            for sent_index in self.learningsFromTheArticle.sentences_indicies:
                if sent_index in sents:
                    sents[sent_index].questions.add("learningsFromTheArticle")
                else:
                    sents[sent_index] = SourceSentence(indix=sent_index, sentence=sentences[sent_index], questions={"learningsFromTheArticle"})
 
            answer = Answer(question="What are the learnings from this article?", answer=self.learningsFromTheArticle.answer)
            results["learningsFromTheArticle"] = answer

        if self.summaryInBulletPoints:
            points = []
            for key, point in enumerate(self.summaryInBulletPoints):

                for sent_index in point.sentences_indicies:
                    if sent_index in sents:
                        sents[sent_index].questions.add(f"Point {key + 1}")
                    else:
                        sents[sent_index] = SourceSentence(indix=sent_index, sentence=sentences[sent_index], questions={f"Point {key + 1}"})

                answer = Answer(question=f"Point {key + 1}", answer=point.answer)
                points.append(answer)
            results["summaryInBulletPoints"] = points

        results["source_sentences"] = sents

        return results

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
                "whatThisArticleIsAbout" : {"This blog post is about the importance of mobile game soft launch", "sentences_indicies": [0, 1,5,14,15]},
                "learningsFromTheArticle" : {"Mobile game soft launch is a process of releasing a game to a limited audience for testing.", "sentences_indicies": [1, 2,4,8,9]},   
                "summaryInBulletPoints" : [
                    {"Mobile game soft launch is a process of releasing a game to a limited audience for testing.", "sentences_indicies": [1, 2]},
                    {"bullet_point": "Getting soft launch require planning, strategy and expirements.", "sentences_indicies": [3,4,..]},
                    ],
            }}"""

        _user_content_2_task = """Use the examples above to answer the following questions. 
        Use the sentences_indicies to identify all the sentences used to answer the question.
        1. One short sentance explaining what the article is about, and what can be learned from it. Limit the answer to thirty words. Include at least five sentences_indicies. 
        2. Summarize the key learning from the article. Limit the answer to thirty words. Include at least five sentences_indicies.
        3. Summarize the article up to six bullet-points. Weave into the points entities that are the subject of the article and key learnings. Limit the answer to tweenty words for each point.  
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


class CustomQuestionPrompt(DocumentPrompt):
    
    question: str
    answer: Optional[ResponseWithIndex]
    usage: Optional[str]

    def to_answer(self, sentences: List[str]):
        if self.answer:
            sents = [sentences[index] for index in self.answer.sentences_indicies] 
            return Answer(question=self.question, answer=self.answer.answer, sources=sents, relevance_score=self.answer.sentences_relevance_score)
        return None


    @classmethod
    def get_messages(cls, body: str, question: str):
        """
        Get the list of messages for the document prompt.

        Args:
            body (str): The body of the document.
            question (str): The question to answer.

        Returns:
            JSON Output: {{quesion: "What is the question?", answer: "The answer to the question."}}
        """ 

        _system_content = """You are a researcher task with answering questions about an article.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. 
            Shorten the answer to make sure the JSON is valid. Using sentences_indicies, the top 10 sentences used to answer the question. [/INST] 
            JSON Output: {{
                "question" : "What is the question?",
                "answer" : {"answer": "The answer to the question.", "sentences_indicies": [1, 2, 4, 8, 9], "sentences_relevance_score": [0.9, 0.8, 0.7, 0.6, 0.5]}
            }}"""

        _user_content_2_task = """Answer the following question using the article below. Keep the answer to the question short and concise.
        Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid.
        Question: {QUESTION}""".format(QUESTION=question)

        _user_content_3_article = """Article: {BODY}""".format(BODY=body)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task},
            {"role": "user", "content": _user_content_3_article}
        ]


class AnswerEntity(BaseModel):
    """
    Model for answer entities.
    """

    name: str
    type: str
    description: str
    synonymEntities: List[str]


class IdentifySynonymEntitiesPrompt(BaseModel):

    sameEntities: List[AnswerEntity]
    entityName: str

    @classmethod
    def get_messages(cls, entities: List[Entity]):
        """
        Get the prompt message for the identify synonym entities task.

        Args:
            list of entities: The list of entities to identify synonyms for.

        Returns:
            list[AnswerEntity]: The list of synonym entities.
        """ 

        _entities = list(dict)
        for entity in entities:
            _entities.append({"name": entity.name, "type": entity.type, "description": entity.description})

        _system_content = """You are a language expert task with identifying entities that are the same, or very similar in meaning.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If entities are not similar, don't inlcude them in the answer."""

        _user_content_1_examples = """Answers output must confirm to the this JSON format. Insure the JSON is valid. Shorten the answer to make sure the JSON is valid. [/INST] 
            JSON Output: [{
                "name" : "Artificial Intelligence",
                "type" : "technology",
                "description" : "The branch of computer science that deal with writing computer programs that can solve problems creatively",
                "synonymEntities" : ["AI", "AI Tech", "Deep Learning"]
            }]"""

        _user_content_2_task = """Identify the synonyms for the entity provided. Use the examples above to identify the synonyms for the entity. 
        Only output valid JSON format. Reduce the length of the answer to make sure the JSON is valid. Entities: {ENTITIES}""".format(ENTITIES=_entities)

        return [
            {"role": "system", "content": _system_content},
            {"role": "user", "content": _user_content_1_examples},
            {"role": "user", "content": _user_content_2_task}
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



