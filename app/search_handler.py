import logging, re, sys, os
import app.app_logic as app
from app.transformers_util import generate_embeddings
from app.db_connector import get_engine
from app.models import Document, Entity, DocumentDisplay, RagAnswerDisplay, SearchResults
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.icog_util import DocSummarizer
from app.prompt_models import RAGPrompt
from app.db_connector import get_engine


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app.together_api_client import (
    TogetherMixtralClient,
    ApiCallException,
)

env_vers = os.environ

engine = get_engine()



class MatchedDocument(BaseModel):
    document_id: int
    cosine_similarity: float


class SearchHandler:
    def __init__(self):
        self._db_engine = get_engine()
        self._question_regex = r"(?:What|How|Tell me|Find|Who).*\?"
        self._summarizer = DocSummarizer()
        self._mixtralClient = TogetherMixtralClient()


    async def __call__(self, user_id: str, query: str = None) -> SearchResults:
        """
        Searches for a query and returns a either a list of DocumentDisplay or RAG answer.

        Args:
            user_id (str): The ID of the user performing the search.
            query (str): The search query.

        Returns:
            list[DocumentDisplay]: for regular search or List[RAGPrompt] for question search

        """
        if not query:
            docs = self.get_documents_display_for_user_id(user_id)
            return SearchResults(documents_display=docs, rag_answer=None)

        is_question = re.match(self._question_regex, query, re.IGNORECASE)

        if is_question:
            if query == "what a test?":
                rag_results = await self.test_rag_workflow()
            else:
                rag_results =  await self.rag_workflow(user_id = user_id, search_term = query)
            
            if(type(rag_results) == str):
                return SearchResults(documents_display=[], rag_answer=None, failure=rag_results)

            docs = []
            if len(rag_results.documents_used) > 0:
                for doc_id in rag_results.documents_used:
                    display = app.get_document_display_by_id(doc_id)
                    docs.append(display) 
            
            return SearchResults(documents_display=docs, rag_answer=rag_results)
                
        else:
            matched_docs = self.search_embeddings(user_id=user_id, search_term=query, threshold=0.5, max_results=10)
            return SearchResults(documents_display=self.get_document_display(matched_docs), rag_answer=None)
        

    async def test_rag_workflow(self) -> RagAnswerDisplay:
        
        return RagAnswerDisplay(
            answer='Netflix is a worldwide Internet TV company that offers a wide variety of TV shows, movies, documentaries, and anime, along with award-winning Netflix originals. It started as a DVD-by-mail service and has evolved over the years to become a streaming service with a huge library of content. The brand is well-known and trusted, and it aims to delight customers in hard-to-copy, margin-enhancing ways. The company continually experiments with its non-member site to identify which potential ideas resonate with customers and determine how to position new features they have already built.',
            documents_used=[165], 
            llm_service_meta={'prompt_tokens': 2890, 'completion_tokens': 330, 'total_tokens': 3220, 'duration': 4043})
        

    async def rag_workflow(self, user_id: str, search_term: str) -> RagAnswerDisplay | str:
        docs = self.search_embeddings(user_id=user_id, search_term=search_term, threshold=0.5, max_results=3)

        if len(docs) == 0:
            return f"No documents found for the search term '{search_term}'"

        retrieved_contexts = []
        for doc in docs:
            td = app.get_document_by_id(doc.document_id)
            summary = self._summarizer(td.original_text)
            retrieved_contexts.append({"doc_id": td.id, "doc_title": td.title, "text": summary})

        messages_list = RAGPrompt.get_messages(contexts=retrieved_contexts, question=search_term)
        
        try:
            rag_answer = await self._mixtralClient.generate(messages=messages_list, model=RAGPrompt)

            answer_display = RagAnswerDisplay(
                answer=rag_answer.answer,
                documents_used=rag_answer.document_ids_used_for_answer,
                llm_service_meta=rag_answer.usage
            )
            logging.info(answer_display)
            return answer_display
        except ApiCallException as e:
            logging.error(f"Error calling TogetherMixtral API: {str(e)}")
            return None
           
    def search_embeddings(self, user_id: str, search_term: str, threshold: float = 0.5, max_results: int = 10) -> list[MatchedDocument]:
        """
        This function searches for document embeddings by search term
        """
        logging.info(f"Generate embeddings for term {search_term}")
        embedded_term = generate_embeddings(search_term) ## Generate embeddings for search term
        logging.info(f"Embeddings for term {search_term} are length is {len(embedded_term)}")

        # Get document with some embeddings that are closest to the search term
        logging.info(f"Searching for documents with embeddings closest to term {search_term}")

        with Session(self._db_engine) as session:
            stmt_docs = text("""SELECT a.document_id, a.cosine_similarity
                        FROM (SELECT de.document_id, MAX(1 - (de.embeddings <=> :vector)) AS cosine_similarity 
                            FROM document_embeddings AS de
                            JOIN bookmark ON de.document_id = bookmark.document_id
                            WHERE bookmark.user_id = :user_id 
                            GROUP BY de.document_id) a
                        WHERE a.cosine_similarity > :threshold
                        ORDER BY a.cosine_similarity DESC
                        LIMIT :limit""")
            
            matched_docs = session.execute(stmt_docs, {"vector": str(embedded_term.tolist()), "user_id": user_id, "threshold": threshold, "limit": max_results}).all()
            
            stmt_ents = text("""SELECT a.id, a.cosine_similarity
                        FROM (SELECT d.id, MAX(1 - (e.embedding <=> :vector)) AS cosine_similarity 
                            FROM document AS d
                            JOIN bookmark ON d.id = bookmark.document_id
                            JOIN entity e ON e.document_id = d.id 
                            WHERE bookmark.user_id = :user_id
                            AND e.embedding IS NOT NULL
                            GROUP BY d.id) a
                        WHERE a.cosine_similarity > :threshold
                        ORDER BY a.cosine_similarity DESC
                        LIMIT :limit""")
            matched_ents_docs = session.execute(stmt_ents, {"vector": str(embedded_term.tolist()), "user_id": user_id, "threshold": threshold, "limit": max_results}).all()

        ## Merge matched document and entity documents
        ids = [md[0] for md in matched_docs]
        for dt in matched_ents_docs:
            if dt[0] not in ids:
                matched_docs.append(dt)

        results = []
        for md in matched_docs:
            results.append(MatchedDocument(document_id=md[0], cosine_similarity=md[1]))

        logging.info(f"Found {len(matched_docs)} matched documents for term {search_term}")
    
        return results
     
    def get_document_display(self, matched_docs: list[MatchedDocument]) -> list[DocumentDisplay]:
        """
        This function returns a list of DocumentDisplay objects
        """
        logging.info(f"Get document display for matched documents")
        results = []
        for matched_docs in matched_docs:
            display = app.get_document_display_by_id(matched_docs.document_id)
            results.append(display) 

        return results
    
    def get_documents_display_for_user_id(self, user_id: str):

        docs = app.get_documents_by_user_id(user_id)
        results = []
        for doc in docs:
            display = app.get_document_display_by_id(doc.id)
            results.append(display)
        
        return results