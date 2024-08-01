import re
from pydantic import BaseModel

from app.models import Answer, Document, Entity


## Models to be used in the Gemini API responses
class Citation(BaseModel):
    start_str: str
    end_str: str

class DocumentCitation(BaseModel):
    document_id: int
    citations: list[Citation]


class FoundEntity(BaseModel):
    name: str
    type: str
    description: str

class QuestionAnswer(BaseModel):
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
        Use the meta_answer field to indicate if you were able to complete the task, or explanation why not. 
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
        return """You are a researcher tasked with identifying entities (such as people, companies, locations, events, etc.) 
        and topics (such as politics, economy, finance, technology, etc.) mentioned in an article. Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            If you don't know the answer, please don't share false information. 
        Article: {BODY}""".format(BODY=text)

    


class IdentifyQuestionsAnswerPrompt(BaseModel):
    
    questions_answers: list[QuestionAnswer]
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
        Use the meta_answer field to indicate if you were able to complete the task, or explanation why not.
        Please don't share false information. Ensure to include citations with each question and answer. 
        To reduce the number of tokens, include the start and ending strings that can be used to identify the text.
        Article: {BODY}""".format(BODY=body)

 
    
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
            Please ensure that your responses are socially unbiased and positive in nature.
            If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
            Use the meta_answer field to indicate if you were able to complete the task, or explanation why not.
            If you don't know the answer, please don't share false information.\n. 
            Question: {QUESTION}\n {ARTICLES}""".format(QUESTION=question, ARTICLES=_articles) 

        



