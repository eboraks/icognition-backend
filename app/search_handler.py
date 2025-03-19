import logging, re, sys, os
import app.getters as getter
import app.icog_util as util
import uuid as uuid_pkg
from app.db_connector import get_engine
from app.models import Document, RagAnswerPublic, SearchResults
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.icog_util import DocSummarizer
from app.db_connector import get_engine
from app.gemini_prompts_models import AskQuestionPrompt
from app.gemini_client import GeminiClient
from app.log import get_logger


logging = get_logger()


env_vers = os.environ

engine = get_engine()

gemini_client = GeminiClient()


class MatchedDocument(BaseModel):
    id: uuid_pkg.UUID
    entity_id: uuid_pkg.UUID | None
    embedding_id: int
    cosine_similarity: float


class SearchHandler:
    def __init__(self):
        self._db_engine = get_engine()
        self._question_regex = r"(?:What|How|Tell me|Find|Who|Explain|Give|Where).*\?"
        self._summarizer = DocSummarizer()

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
                matched_docs = await self.search_embeddings(
                    user_id=user_id, search_term=query, threshold=0.5, max_results=3
                )
                _docs = [getter.get_document_by_id(doc.id) for doc in matched_docs]
                rag_results = await self.rag_workflow(docs=_docs, search_term=query)

            if type(rag_results) == str:
                return SearchResults(
                    documents_display=[], rag_answer=None, failure=rag_results
                )

            docs = []
            for doc_id in rag_results.documents_used:
                docs.append(getter.get_document_public_by_id(doc_id))

            return SearchResults(documents_display=docs, rag_answer=rag_results)

        else:
            docs = await self.search_aggregator(
                user_id=user_id, search_term=query, threshold=0.5, max_results=10
            )
            ##docs = [getter.get_document_by_id(doc.id) for doc in matched_docs]
            return SearchResults(
                documents_display=docs,
                rag_answer=None,
            )

    async def test_rag_workflow(self) -> RagAnswerPublic:

        return RagAnswerPublic(
            answer="Netflix is a worldwide Internet TV company that offers a wide variety of TV shows, movies, documentaries, and anime, along with award-winning Netflix originals. It started as a DVD-by-mail service and has evolved over the years to become a streaming service with a huge library of content. The brand is well-known and trusted, and it aims to delight customers in hard-to-copy, margin-enhancing ways. The company continually experiments with its non-member site to identify which potential ideas resonate with customers and determine how to position new features they have already built.",
            documents_used=[132],
            llm_service_meta={
                "prompt_tokens": 2890,
                "completion_tokens": 330,
                "total_tokens": 3220,
                "duration": 4043,
            },
        )

    async def rag_workflow(
        self, docs: list[Document], search_term: str
    ) -> RagAnswerPublic | str:

        if len(docs) == 0:
            return f"No documents found for the search term '{search_term}'"

        try:
            generated_response = await gemini_client.generate_response(
                AskQuestionPrompt.build_prompt(docs, search_term), AskQuestionPrompt
            )

            if generated_response.meta_answer != "SUCCESS":
                logging.error(
                    f"Error generating RAG answer for search term {search_term}"
                )
                logging.error(f"Error: {generated_response.meta_answer}")

            if generated_response.answer is None:
                logging.error(
                    f"Error generating RAG answer for search term {search_term}"
                )
                logging.error(f"Error: {generated_response}")

            rag_answer = generated_response.question_answer_builder(
                question=search_term
            )

            logging.info(f"Generated RAG answer for search term {search_term}")
            return rag_answer
        except Exception as e:
            logging.error(f"Error calling AI API: {str(e)}")
            logging.error(generated_response)
            return None

    def search_text(
        self, user_id: str, search_term: str, max_results: int = 20
    ) -> list[tuple]:

        with Session(self._db_engine) as session:
            stmt = text(
                """SELECT id, text, source_type, source_id, 1.0 AS cosine_similarity 
                    FROM public.embedding
                    WHERE search_vector @@ plainto_tsquery('english', :term)
                    AND source_type IN ('document')
                    AND user_id = :user_id
                    GROUP BY 1, 2, 3, 4
                    LIMIT :limit;"""
            )

            matches = session.execute(
                stmt,
                {
                    "term": search_term,
                    "user_id": user_id,
                    "limit": max_results,
                },
            ).all()

            logging.info(
                f"Found {len(matches)} matched text search for term {search_term}"
            )

        return matches

    async def search_embeddings(
        self,
        user_id: str,
        search_term: str,
        threshold: float = 0.5,
        max_results: int = 20,
        attempts: int = 0,
    ) -> list[tuple]:
        """
        This function searches for document embeddings by search term
        """
        logging.info(f"Generate embeddings for term {search_term}")
        embedded_term = await gemini_client.generate_embedding(
            search_term
        )  ## Generate embeddings for search term
        logging.info(
            f"Embeddings for term {search_term} are length is {len(embedded_term)}"
        )

        # Get document with some embeddings that are closest to the search term
        logging.info(
            f"Searching for documents with embeddings closest to term {search_term}. Attempt {attempts} with threshold {threshold}"
        )

        with Session(self._db_engine) as session:
            stmt = text(
                """SELECT a.emb_id, a.text, a.source_type, a.source_id, a.cosine_similarity
                    FROM (SELECT e.id AS emb_id, e.text, e.source_type, e.source_id, MAX(1 - (e.vector <=> :vector)) AS cosine_similarity 
                            FROM embedding AS e
                            WHERE e.user_id = :user_id
                            AND e.source_type IN ('document')
                            GROUP BY 1,2,3,4) a
                    WHERE a.cosine_similarity >= :threshold
                    GROUP BY 1, 2, 3, 4, 5
                    ORDER BY a.cosine_similarity DESC
                    LIMIT :limit"""
            )

            matches = session.execute(
                stmt,
                {
                    "vector": str(embedded_term),
                    "user_id": user_id,
                    "threshold": threshold,
                    "limit": max_results,
                },
            ).all()

            logging.info(
                f"Found {len(matches)} matched embeddings for term {search_term}"
            )

        ### If we don't have enough matches, we can try to lower the threshold, but only 2 times going from 0.5 to 0.3.
        if len(matches) < 5 and attempts <= 2:
            return await self.search_embeddings(
                user_id=user_id,
                search_term=search_term,
                threshold=threshold - 0.1,
                max_results=max_results,
                attempts=attempts + 1,
            )

        return matches

    async def search_aggregator(
        self,
        user_id: str,
        search_term: str,
        threshold: float = 0.5,
        max_results: int = 20,
        attempts: int = 1,
    ) -> list[Document]:

        priority = self.search_text(user_id=user_id, search_term=search_term)

        embeddings_results = await self.search_embeddings(
            user_id=user_id,
            search_term=search_term,
            threshold=threshold,
            max_results=max_results,
            attempts=attempts,
        )
        priority_ids = [emb[3] for emb in priority]
        for emb in embeddings_results:
            if emb[3] not in priority_ids:
                priority.append(emb)

        matched_docs = self.tuple_results_to_matched_documents(priority)

        docs = self.docs_convert_matches_to_doc(matched_docs)

        return docs

    def tuple_results_to_matched_documents(
        self, matches: list[tuple]
    ) -> list[MatchedDocument]:
        results = []
        for mat in matches:
            emb_id = mat[0]
            emb_source = mat[2]
            emb_source_id = mat[3]
            emb_cosine_similarity = mat[4]

            if emb_source == "entity":
                docs = getter.get_documents_by_entity_id(emb_source_id)
                for doc in docs:
                    results.append(
                        MatchedDocument(
                            id=doc.id,
                            entity_id=str(emb_source_id),
                            embedding_id=emb_id,
                            cosine_similarity=emb_cosine_similarity,
                        )
                    )

            if emb_source == "document":
                results.append(
                    MatchedDocument(
                        id=str(emb_source_id),
                        entity_id=None,
                        embedding_id=emb_id,
                        cosine_similarity=emb_cosine_similarity,
                    )
                )

        ## Remove duplicate documents, if there are any
        results = util.deduplicate_objects_list(results)

        return results

    def docs_convert_matches_to_doc(
        self, matched_docs: list[MatchedDocument], max_results: int = 20
    ) -> list[Document]:
        """
        This function returns a list of Document objects
        """
        logging.info(f"Get document display for matched documents")
        results = []
        for doc in matched_docs:
            document = getter.get_document_by_id(doc.id)
            document.cosine_similarity = doc.cosine_similarity
            results.append(document)

        ## Sort the results by cosine similarity DESC
        results = sorted(results, key=lambda x: x.cosine_similarity, reverse=True)

        ## Limit the results to max_results
        results = results[:max_results]

        return results
