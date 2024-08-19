import json
from pydantic import BaseModel

from app.models import Answer, Document, Entity, Question_Answer, Question_Answer_Display
import app.transformers_util as transformers_util



## Models to be used in the Gemini API responses
class Citation(BaseModel):
    start_str: str
    end_str: str

class DocumentCitation(BaseModel):
    document_id: int
    citations: list[Citation]

    def get_citations(self) -> list[dict]:
        """"Return the citations as a list of dictionaries for stroing as JSON in DB"""
        return [c.__dict__ for c in self.citations]


class FoundEntity(BaseModel):
    name: str
    type: str
    description: str

class FoundQuestionAnswer(BaseModel):
    question: str
    answer: str
    citiation: list[Citation]

## Prompts class
class SummarizePrompt(BaseModel):
    """
    Prompt model for summarizing an article
    """

    what_this_article_is_about: str
    key_learning_from_article: str
    key_points: list[str]
    citations_sentances: list[Citation]
    meta_answer: str

    
    @classmethod
    def build_prompt(cls, text: str):
        """
        Build the prompt for the summarize task.

        Args:
            text (str): The text of the document/article.

        Returns:
            str: The prompt for the summarize task.
        """
        # Prompt for summarizing an article
        return """You are a researcher tasked with summarizing the article into what the article is about, key learnings, and critical points. 
        Please ensure that your responses are socially unbiased and positive in nature. If the ask does not make any sense, or is not factually coherent, 
        or you don't know the answer explain why. Please don't share false information. 
        Use the meta_answer field to indicate if you were able to complete the task by writing "SUCCESS", or explanation why not  
        Ensure you include citations of the most essential sentences/text you relied on to answer the questions. 
        To reduce the number of tokens in the response, use the begging and end of the string to reference the citation. 
        Article: {BODY}""".format(BODY=text)

    def populate_document(self, document: Document) -> Document:
        """
        Populate the document with the prompt data.

        Args:
            document (Document): The document to populate.

        Returns:
            Document: The populated document.
        """
        document.is_about = self.what_this_article_is_about
        document.learning_from_document = self.key_learning_from_article
        document.summary_bullet_points = self.key_points
        document.summary_citations = [c.__dict__ for c in self.citations_sentances]

        return document




class EntitiesPrompt(BaseModel):
    """
    Prompt model for extracting entities from an article
    """

    entities: list[FoundEntity]

    
    @classmethod
    def build_prompt(cls, text: str):
        """
        Build the prompt for the summarize task.

        Args:
            text (str): The text of the document/article.

        Returns:
            str: The prompt for the summarize task.
        """
        # Prompt for summarizing an article
        return """You are a researcher tasked with identifying the most relevent entities (such as people, products, companies, locations, events, etc.) 
        to the article subjects. Try to focus on the most important entities. Include the name, type, and description of each entity or topic. 
        Merge entities with name variation for example Voter and Voters, or Anti-Woke and anti-wokeness. Deduplicates entities on name and do not include irrelevant entities.
        Response most be valid JSON. Ensure that your responses are socially unbiased and positive in nature.
        If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
        If you don't know the answer, please don't share false information. 
        Article: {BODY}""".format(BODY=text)
    

    def entities_builder(self) -> list[Entity]:
        """
        Build the SQLModel Entities from the LLM results

        Returns:
            list[Entity]: The populated entities.
        """
        entities = []
        temps = [Entity(**entity.model_dump()) for entity in self.entities]
        for temp in temps:
            ## temp.name doesn't alreasy exist in entities entity.name
            if temp.name not in [entity.name for entity in entities]:
                entities.append(temp)

        return entities


class TopicPrompt(BaseModel):
    """
    Prompt model for extracting entities from an article
    """

    topics: list[FoundEntity]

    
    @classmethod
    def build_prompt(cls, text: str):
        """
        Build the prompt extracting topics from article.

        Args:
            text (str): The text of the document/article.

        Returns:
            str: The prompt for the summarize task.
        """
        # Prompt for summarizing an article
        return """You are a researcher tasked with identifying the most relevent topic (such as Politics, Finance, Economy, Religion, etc.) 
        to the article subjects. Try to focus on the most important topics. Include the name, type='topic' and description of each topic. 
        Merge topic by name, for example Voter and Voters, or Anti-Woke and anti-wokeness. Deduplicates topics on name and do not include irrelevant topics.
        Response most be valid JSON. Ensure that your responses are socially unbiased and positive in nature.
        If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
        If you don't know the answer, please don't share false information. 
        Article: {BODY}""".format(BODY=text)
    
    def entities_builder(self) -> list[Entity]:
        """
        Build the SQLModel Entities from the LLM results

        Returns:
            list[Entity]: The populated entities.
        """
        entities = []
        temps = [Entity(**entity.model_dump()) for entity in self.topics]
        for temp in temps:
            ## temp.name doesn't alreasy exist in entities entity.name
            if temp.name not in [entity.name for entity in entities]:
                entities.append(temp)

        return entities


class IdentifyQuestionsAnswerPrompt(BaseModel):
    
    questions_answers: list[FoundQuestionAnswer]
    meta_answer: str

    @classmethod
    def build_prompt(cls, body: str):
        """
        Get the list of messages for the document prompt.

        Args:
            body (str): The body of the document.
            
        Returns:
            Prompt: str: The prompt for the summarize task.
        """ 

        # Prompt
        return """You are a researcher tasked with identifying the essential questions and answers an article(s) addresses. 
        Please ensure that your responses are socially unbiased and positive in nature.
        If the article does address any question, or is not factually coherent, or you don't know the answer explain why in the meta_answer field.
        Use the meta_answer field to indicate if you were able to complete the task by writing "SUCCESS", or explanation why not.
        Please don't share false information. Ensure to include citations with each question and answer. 
        To reduce the number of tokens, include the start and ending strings that can be used to identify the text.
        Article: {BODY}""".format(BODY=body)


    def questions_answers_builder(self, document_id: int) -> list[Question_Answer]:
        """
        Build the SQLModel Answers from the LLM results

        Returns:
            list[Answer]: The populated answers.
        """
        qans = []
        for qa in self.questions_answers:
            answer = Question_Answer(document_id=document_id, 
                                     question=qa.question, 
                                     answer=qa.answer, 
                                     citations=[c.__dict__ for c in qa.citiation], 
                                     question_vector= transformers_util.generate_embeddings(qa.question))
            qans.append(answer)

        return qans  
 
    
class AskQuestionPrompt(BaseModel):
    """
    Model for subtopic prompts.
    """
    answer: str
    meta_answer: str
    documents_citations: list[DocumentCitation]
    
    @classmethod
    def build_prompt(cls, docs: list[Document], question: str):
        """
        Build question from for the RAG task.
        Args:
            docs (list[Document]): The list of documents to use for the task.
            question (str): The question to answer.

        Returns:
            list[dict]: The list of messages for the subtopic prompt.
        """
        
        _articles = "Articles:\n"
        for d in docs:
            _articles += """Article_ID: {ID}, Article_Name: {TITLE}, Article: {CONTEXT}\n""".format(
                ID=d.id, TITLE=d.title, CONTEXT=d.original_text, URL=d.url)

        return """You are a researcher task with answering questions using articles. 
            Compose your answer from as many articles as you need. Keep your answer short, concise and informative.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            Use the meta_answer field to indicate if you were able to complete the task by writing "SUCCESS", or explanation why not.
            If you don't know the answer, please don't share false information.
            Ensure you include citations of the most essential sentences/text you relied on to answer the questions. 
            To reduce the number of tokens in the response, use the begging and end of the string to reference the citation.\n 
            Question: {QUESTION}\n {ARTICLES}""".format(QUESTION=question, ARTICLES=_articles) 
    
    def question_answer_builder(self, question: str) -> Question_Answer_Display: 
        return Question_Answer_Display(question=question, answer=self.answer, citations=[dc.__dict__ for dc in self.documents_citations])
    


class ProjectTaskPrompt(BaseModel):
    
    description: str
    explanation: str
    meta_answer: str
    documents_citations: list[DocumentCitation]

    @classmethod
    def build_prompt(cls, docs: list[Document], description: str):
        """
        Build question from for the RAG task.
        Args:
            docs (list[Document]): The list of documents to use for the task.
            description (str): The description of the task.

        Returns:
            list[dict]: The list of messages for the subtopic prompt.
        """
        
        _articles = "Articles:\n"
        for d in docs:
            _articles += """Article_ID: {ID}, Article_Name: {TITLE}, Article: {CONTEXT}\n""".format(
                ID=d.id, TITLE=d.title, CONTEXT=d.original_text, URL=d.url)

        return """You are a researcher task with answering questions using articles. Keep your answer short, concise and informative.  
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            Use the meta_answer field to indicate if you were able to complete the task by writing "SUCCESS", or explanation why not.
            If you don't know the answer, please don't share false information.
            Ensure you include citations of the most essential sentences/text you relied on to answer the questions. 
            To reduce the number of tokens in the response, use the begging and end of the string to reference the citation.\n 
            Description: {DESCRIPTION}\n {ARTICLES}""".format(DESCRIPTION=description, ARTICLES=_articles)


        



