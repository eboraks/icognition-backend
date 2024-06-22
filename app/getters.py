from app.db_connector import get_engine
from app.models import Bookmark, Document, Document_Entity_Link, DocumentDisplay, Entity, SubTopic, SubTopic_Document_Link, SubTopic_Embedding_Link, Embedding, SubTopic_Entity_Link, SubTopicDisplay, TreeNode
from sqlalchemy.orm import Session
from sqlalchemy import (
    and_,
    select,
    func,
    text,
)

import app.html_parser as html_parser
engine = get_engine()


def get_document_by_id(document_id) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.id == document_id))
    if doc is None:
        raise ValueError(f"Document with id {document_id} not found")
    session.add_all(doc.entities)
    session.add_all(doc.subtopics)
    session.close()
    return doc

def get_documents_by_ids(document_ids: set[int]) -> list[Document]:
    """Method that retrieves documents from the database by ID.

    Args:
        document_ids (list[int]): The list of document IDs.

    Returns:
        list[Document]: The list of documents.
    """
    with Session(engine) as session:
        documents = session.scalars(select(Document).where(Document.id.in_(document_ids))).unique().all()

    return documents

def get_document_by_bookmark_id(bookmark_id) -> Document:
    session = Session(engine)
    doc = session.scalar(
        select(Document)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.id == bookmark_id)
    )
    session.add_all(doc.entities)
    session.add_all(doc.subtopics)
    session.close()
    return doc

def get_documents_by_user_id(user_id: str, document_status = "Done") -> list[Document]:
    session = Session(engine)
    docs = session.scalars(
        select(Document)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(and_(
            Bookmark.user_id == user_id,
            Document.status == document_status))
        .order_by(Bookmark.update_at.desc())
    ).unique().all()
    session.close()
    return docs

def get_documents_display_by_user_id(user_id: str, document_status = "Done") -> list[DocumentDisplay]:
    results = []
    session = Session(engine)
    docs = session.scalars(
        select(Document)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(and_(
            Bookmark.user_id == user_id,
            Document.status == document_status))
        .order_by(Bookmark.update_at.desc())
    ).unique().all()

    for doc in docs:
        results.append(doc.to_display())

    session.close()
    return results

def get_document_by_url(url) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.url == url))
    session.close()


def get_documents_ids() -> list[int]:
    session = Session(engine)
    docs_ids = session.scalars(select(Document.id))
    session.close()
    return docs_ids


def get_entities_by_document_id(document_id) -> Entity:
    session = Session(engine)
    entities = session.scalars(
        select(Entity).where(Entity.document_id == document_id)
    ).all()
    session.close()
    return entities

def get_entities_by_ids(entity_ids: set[int]) -> list[Entity]:
    """Method that retrieves entities from the database by ID.

    Args:
        entity_ids (list[int
    """
    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.id.in_(entity_ids))).unique().all()

    return entities   


def get_bookmarks_by_user_id(user_id: str) -> list[Bookmark]:
    session = Session(engine)
    bookmarks = session.scalars(
        select(Bookmark)
        .where(Bookmark.user_id == user_id)
        .order_by(Bookmark.update_at.desc())
    ).all()
    session.close()
    return bookmarks


def get_bookmark_by_document_id(document_id: int) -> Bookmark:
    session = Session(engine)
    bookmark = session.scalar(
        select(Bookmark).where(Bookmark.document_id == document_id)
    )
    session.close()
    return bookmark


def get_bookmark_by_url(user_id: str, url: str) -> Bookmark:
    url = html_parser.clean_url(url)
    session = Session(engine)
    bookmark = session.scalar(select(Bookmark).where(
        and_(Bookmark.url == url, Bookmark.user_id == user_id)))
    session.close()
    return bookmark


def get_bookmark_document(id: int) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.bookmark_id == id))
    session.close()
    return doc


def get_bookmark_by_id(id: int) -> Bookmark:
    session = Session(engine)
    bookmark = session.scalar(select(Bookmark).where(Bookmark.id == id))
    session.close()
    return bookmark


def get_entities_by_document_id(document_id) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)\
            .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)\
            .where(Document_Entity_Link.document_id == document_id)
    ).all()
    session.close()
    return entities


def get_entities_names_by_user_id(user_id: str) -> list[str]:
    session = Session(engine)
    entities = session.scalars( 
        select(Entity.name)
        .join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id)
        .join(Bookmark, Bookmark.document_id == Document_Entity_Link.document_id)
        .where(Bookmark.user_id == user_id).order_by(Entity.name).distinct()
    ).all()
    session.close()
    return entities


def get_entities_by_user_id_and_type(user_id: str, type: str) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document, Document.id == Entity.document_id)
        .join(Bookmark, Bookmark.document_id == Document.id)
        .where(Bookmark.user_id == user_id, Entity.type == type)
    ).all()
    session.close()
    return entities


def get_documenets_by_entity_id(entity_id: int) -> list[Document]:
    session = Session(engine)
    documents = session.scalars(
        select(Document)
        .join(Document_Entity_Link, Document_Entity_Link.document_id == Document.id)
        .where(Document_Entity_Link.entity_id == entity_id)
    ).all()
    session.close()
    return documents


def get_subtopics_display(user_id: str) -> list[SubTopicDisplay]:
    
    results = []
    with Session(engine) as session:
        
        stmt = select(SubTopic)\
            .join(SubTopic_Entity_Link, SubTopic_Entity_Link.subtopic_id == SubTopic.id)\
            .join(SubTopic_Document_Link, SubTopic_Document_Link.subtopic_id == SubTopic.id)\
            .where(SubTopic.user_id == user_id)
        
         
        subtopics_touples = session.scalars(stmt).unique().fetchall()
        
        ## TODO: Get a list of subtopics display
        for subt in subtopics_touples:
            results.append(subt.to_display())


    results.sort(key=lambda x: x.number_of_docs, reverse=True)
    return results


def get_subtopics(user_id: str) -> list[SubTopic]:
    """Method that retrieves subtopics from the database.

    Args:
        user_id (str): The user ID.

    Returns:
        list[SubTopic]: A list of subtopics.
    """
    subtopics = []
    with Session(engine) as session:
        stmt = select(SubTopic).where(SubTopic.user_id == user_id)
        subtopics = session.scalars(stmt).unique().all()
    return subtopics


def get_subtopics_nodes_by_user(user_id: str) -> list[TreeNode]:
    ## Get subtopic by user
    with Session(engine) as session:
        subtopics = session.scalars(
            select(SubTopic)\
            .join(SubTopic_Document_Link, SubTopic_Document_Link.subtopic_id == SubTopic.id)
            .where(and_(SubTopic.user_id == user_id, SubTopic_Document_Link.document_id != None))
        ).unique().all()
        
        nodes = []
        for subtopic in subtopics:
            nodes.append(subtopic.to_node())

        nodes.sort(key=lambda x: x.doc_count, reverse=True)

    return nodes



def get_document_subtopics(document_id: str) -> list[SubTopicDisplay]:
    
    results = []
    with Session(engine) as session:
        query = text(
                """SELECT s.id, s.name, s.description, 
                        COUNT(DISTINCT sdl.document_id) AS number_of_docs, 
                        json_agg(DISTINCT sdl.document_id)
                        FROM subtopic s
                        JOIN subtopic_document_link  sdl ON sdl.subtopic_id = s.id
                        WHERE sdl.document_id = '{DOC_ID}'
                    GROUP BY s.id, s.name, s.description
                    ORDER BY count(distinct sdl.document_id) DESC""".format(DOC_ID=document_id)
            )

        subtopics_touples = session.execute(query).fetchall()
        for touple in subtopics_touples:
            results.append(SubTopicDisplay.from_touple(touple))

    return results


def get_document_embeddings(document_id: int) -> list[Embedding]:
    with Session(engine) as session:
        embeddings = session.scalars(
            select(Embedding).where(Embedding.source_id == document_id)
        ).all()
    return embeddings

def get_entity_embeddings(entity_id: int) -> list[Embedding]:
    with Session(engine) as session:
        embeddings = session.scalars(
            select(Embedding).where(Embedding.source_id == entity_id)
        ).all()
    return embeddings

def get_documents_by_entity_id(entity_id: int) -> list[Document]:
    with Session(engine) as session:
        documents = session.scalars(select(Document)\
            .join(Document_Entity_Link, Document_Entity_Link.document_id == Document.id)\
            .where(Document_Entity_Link.entity_id == entity_id)).unique().all()
        
    return documents

def get_document_display_by_id(document_id: int, cosine_similarity: float = None) -> DocumentDisplay:
    """
        Method that retrieves a document display by ID.
        cosine_similarity: The cosine similarity value to be used find the document. This is mostly for testing purposes.
    """
    doc = get_document_by_id(document_id)
    display = doc.to_display(cosine_similarity=cosine_similarity)
    return display

def get_embedding_by_id(embedding_id: int) -> Embedding:
    with Session(engine) as session:
        embedding = session.scalar(select(Embedding).where(Embedding.id == embedding_id))
    return embedding


def get_entities_tree_nodes_by_user_id(user_id: str) -> list[TreeNode]:
    
    results = []
    stmt = text("""
        SELECT a.type, a.ents_count, a.docs_count, a.ents_names, a.docs_ids 
        FROM (SELECT e.type, 
            count(distinct e.name) as ents_count, 
            json_agg(distinct e.name) as ents_names,
            count(distinct l.document_id) as docs_count,
            json_agg(distinct l.document_id) as docs_ids
        FROM public.entity e
        JOIN public.document_entity_link l ON l.entity_id = e.id
        JOIN public.bookmark b ON b.document_id = l.document_id
            WHERE b.user_id = :user_id 
        GROUP BY 1) a
        WHERE a.ents_count > 10 AND a.docs_count > 10
        """)

    with Session(engine) as session:
        types = session.execute(stmt, {"user_id": user_id}).fetchall()

        for k, t in enumerate(types):
            top_node = TreeNode(label=t.type.title(), key=k, doc_count=t.docs_count, doc_ids=t.docs_ids, children=[])
            for e_name in t.ents_names:
                ent_node = session.scalar(select(Entity).where(Entity.name == e_name)).to_node()
                if ent_node.doc_count > 1:
                    top_node.children.append(ent_node)
            
            if len(top_node.children) > 0:
                results.append(top_node)
            
            
    return results




def get_filter_nodes_by_user_id(user_id: str) -> list[TreeNode]:
    
    filter_nodes = []
    
    # Get entities tree nodes by entity.type. Example 'person', 'organization', 'location'
    filter_nodes.extend(get_entities_tree_nodes_by_user_id(user_id))   

    # Get subtopics tree nodes as children of 'Areas Of Interest'
    # The reason this operation require session is that to_node() method requires session to load the subtopics related entities and documents
    with Session(engine) as session:
        
        areas_of_interest = TreeNode(label="Areas Of Interest", key=len(filter_nodes), children=[], doc_ids=[])
        subtopics = get_subtopics(user_id)
        for subtopic in subtopics:
            session.add(subtopic)
            area = subtopic.to_node()
            areas_of_interest.doc_count = len(area.doc_ids)
            areas_of_interest.doc_ids.extend(area.doc_ids)
            areas_of_interest.children.append(area)
        filter_nodes.append(areas_of_interest)

    filter_nodes.sort(key=lambda x: x.doc_count, reverse=True)

    return filter_nodes