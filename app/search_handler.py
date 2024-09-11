import logging, re, sys, os
from app.transformers_util import generate_embeddings
from app.db_connector import get_engine
from app.models import DocumentPublic, RagAnswerPublic, SearchResults
import app.getters as getter
import app.icog_util as util
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.icog_util import DocSummarizer
from app.prompt_models import RAGPrompt
from app.db_connector import get_engine
from app.gemini_prompts_models import AskQuestionPrompt
from app.gemini_client import GeminiClient


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

from app.together_api_client import (
    TogetherMixtralClient,
    ApiCallException,
)

env_vers = os.environ

engine = get_engine()

gemini_client = GeminiClient()

class MatchedDocument(BaseModel):
    id: str
    entity_id: str | None
    embedding_id: int
    cosine_similarity: float


class SearchHandler:
    def __init__(self):
        self._db_engine = get_engine()
        self._question_regex = r"(?:What|How|Tell me|Find|Who|Explain|Give).*\?"
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
            docs = getter.get_documents_public_by_user_id(user_id)
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
            for doc_id in rag_results.documents_used:
                docs.append(getter.get_document_public_by_id(doc_id)) 
            
            return SearchResults(documents_display=docs, rag_answer=rag_results)
                
        else:
            matched_docs = self.search_embeddings(user_id=user_id, search_term=query, threshold=0.5, max_results=10)
            return SearchResults(documents_display=self.docs_convert_matches_to_doc_public(matched_docs), rag_answer=None)
        

    async def test_rag_workflow(self) -> RagAnswerPublic:
        
        return RagAnswerPublic(
            answer='Netflix is a worldwide Internet TV company that offers a wide variety of TV shows, movies, documentaries, and anime, along with award-winning Netflix originals. It started as a DVD-by-mail service and has evolved over the years to become a streaming service with a huge library of content. The brand is well-known and trusted, and it aims to delight customers in hard-to-copy, margin-enhancing ways. The company continually experiments with its non-member site to identify which potential ideas resonate with customers and determine how to position new features they have already built.',
            documents_used=[132], 
            llm_service_meta={'prompt_tokens': 2890, 'completion_tokens': 330, 'total_tokens': 3220, 'duration': 4043})
        

    async def rag_workflow(self, user_id: str, search_term: str) -> RagAnswerPublic | str:
        
        matched_docs = self.search_embeddings(user_id=user_id, search_term=search_term, threshold=0.5, max_results=3)

        docs = []
        for doc in matched_docs:
            docs.append(getter.get_document_by_id(doc.id))    


        if len(docs) == 0:
            return f"No documents found for the search term '{search_term}'"

        try:
            generated_response = await gemini_client.generate_response(
                AskQuestionPrompt.build_prompt(docs, search_term), 
                AskQuestionPrompt)

            rag_answer = generated_response.question_answer_builder(question=search_term)

            logging.info(f"Generated RAG answer for search term {search_term}")
            return rag_answer
        except ApiCallException as e:
            logging.error(f"Error calling TogetherMixtral API: {str(e)}")
            return None
           
    def search_embeddings(self, user_id: str, search_term: str, threshold: float = 0.5, max_results: int = 20, attempts: int = 0) -> list[MatchedDocument]:
        """
        This function searches for document embeddings by search term
        """
        logging.info(f"Generate embeddings for term {search_term}")
        embedded_term = generate_embeddings(search_term) ## Generate embeddings for search term
        logging.info(f"Embeddings for term {search_term} are length is {len(embedded_term)}")

        # Get document with some embeddings that are closest to the search term
        logging.info(f"Searching for documents with embeddings closest to term {search_term}. Attempt {attempts} with threshold {threshold}")

        with Session(self._db_engine) as session:
            stmt = text("""SELECT a.emb_id, a.source_type, a.source_id, a.cosine_similarity
                    FROM (SELECT e.id AS emb_id, e.source_type, e.source_id, MAX(1 - (e.vector <=> :vector)) AS cosine_similarity 
                            FROM embedding AS e
                            WHERE e.user_id = :user_id
                            GROUP BY 1,2,3) a
                    WHERE a.cosine_similarity >= :threshold
                    GROUP BY 1, 2, 3, 4
                    ORDER BY a.cosine_similarity DESC
                    LIMIT :limit""")
            
            matches = session.execute(stmt, {"vector": str(embedded_term.tolist()), "user_id": user_id, "threshold": threshold, "limit": max_results}).all()
            
            logging.info(f"Found {len(matches)} matched embeddings for term {search_term}")

        ### If we don't have enough matches, we can try to lower the threshold, but only 2 times going from 0.5 to 0.3. 
        if(len(matches) < 10 and attempts <= 2):
            return self.search_embeddings(user_id=user_id, search_term=search_term, threshold=threshold-0.1, max_results=max_results, attempts=attempts+1)
        
        results = []
        for mat in matches:
            emb_id = mat[0]
            emb_source = mat[1]
            emb_source_id = mat[2]
            emb_cosine_similarity = mat[3]

            if emb_source == "entity":
                docs = getter.get_documents_by_entity_id(emb_source_id)
                for doc in docs:
                    results.append(MatchedDocument(id=doc.id, 
                                                   entity_id = str(emb_source_id), 
                                                   embedding_id=emb_id,
                                                   cosine_similarity=emb_cosine_similarity))
            
            if emb_source == "document":
                results.append(MatchedDocument(id=str(emb_source_id), 
                                                entity_id = None, 
                                                embedding_id=emb_id,
                                                cosine_similarity=emb_cosine_similarity))

        ## Remove duplicate documents, if there are any
        results = util.deduplicate_objects_list(results)
        
        return results
     
    def docs_convert_matches_to_doc_public(self, matched_docs: list[MatchedDocument]) -> list[DocumentPublic]:
        """
        This function returns a list of DocumentDisplay objects
        """
        logging.info(f"Get document display for matched documents")
        results = []
        for doc in matched_docs:
            public = getter.get_document_public_by_id(doc.id)
            public.cosine_similarity = doc.cosine_similarity
            results.append(public) 

        return results