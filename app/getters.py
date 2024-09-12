from app.db_connector import get_engine
from app.models import Source, Document, Document_Entity_Link, DocumentPublic, Entity, Question_Answer, SubTopic, SubTopic_Document_Link, SubTopic_Embedding_Link, Embedding, SubTopic_Entity_Link, SubTopicDisplay, TreeNode
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import (
    and_,
    select,
    text,
)

import app.html_parser as html_parser
engine = get_engine()


def get_document_public_by_id(document_id: str) -> DocumentPublic:
    with Session(engine) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id))
        if doc is None:
            raise ValueError(f"Document with id {document_id} not found")
        session.add_all(doc.entities)
        
        return doc.to_public()
    
def get_document_by_id(document_id: str) -> Document:
    with Session(engine) as session:
        doc = session.scalar(select(Document).where(Document.id == document_id))
        if doc is None:
            raise ValueError(f"Document with id {document_id} not found")
        
        return doc

def get_documents_by_ids(document_ids: set[int]) -> list[Document]:
    """Method that retrieves documents from the database by ID.

    Args:
        document_ids (list[int]): The list of document IDs.

    Returns:
        list[Document]: The list of documents.
    """
    with Session(engine) as session:
        documents = session.scalars(select(Document).where(Document.id.in_(document_ids))).all()

    return documents

def get_documents() -> list[Document]:
    session = Session(engine)
    docs = session.scalars(select(Document)).all()
    session.close()
    return docs

def get_document_by_source_id(source_id) -> Document:
    session = Session(engine)
    doc = session.scalar(
        select(Document)
        .join(Source, Source.document_id == Document.id)
        .where(Source.id == source_id)
    )
    session.add_all(doc.entities)
    session.add_all(doc.subtopics)
    session.close()
    return doc

def get_documents_by_user_id(user_id: str, document_status = "Done") -> list[Document]:
    
    with Session(engine) as session:
        docs = session.scalars(
            select(Document)
            .options(joinedload(Document.entities))
            .join(Source, Source.document_id == Document.id)
            .where(and_(
                Source.user_id == user_id,
                Document.status == document_status))
            .order_by(Source.update_at.desc())
        ).unique().all()
    
    return docs



def get_documents_public_by_user_id(user_id: str, document_status = "Done") -> list[DocumentPublic]:
    results = []
    with Session(engine) as session:

        docs = session.scalars(
            select(Document)
            .options(joinedload(Document.entities))
            .join(Source, Source.document_id == Document.id)
            .where(and_(
                Source.user_id == user_id,
                Document.status == document_status))
            .order_by(Source.update_at.desc())
            
        ).unique().all()

    for doc in docs:
        results.append(doc.to_public())

    session.close()
    return results

def get_document_by_url(url) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.url == url))
    session.close()
    return doc


def get_documents_ids() -> list[int]:
    session = Session(engine)
    docs_ids = session.scalars(select(Document.id))
    session.close()
    return docs_ids


def get_entities_by_document_id(document_id) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity).join(Document_Entity_Link, Document_Entity_Link.entity_id == Entity.id).where(Document_Entity_Link.document_id == document_id)
    ).all()
    session.close()
    return entities

def get_entities_ids_by_document_id(document_id) -> list[int]:
    session = Session(engine)
    entities_ids = session.scalars(
        select(Document_Entity_Link.entity_id).where(Document_Entity_Link.document_id == document_id)
    ).all()
    session.close()
    return entities_ids

def get_entities_by_ids(entity_ids: set[int]) -> list[Entity]:
    """Method that retrieves entities from the database by ID.

    Args:
        entity_ids (list[int
    """
    with Session(engine) as session:
        entities = session.scalars(select(Entity).where(Entity.id.in_(entity_ids))).unique().all()

    return entities   

def get_similar_entity_by_name_vector(user_id: str, vector, threshold: float = 0.78) -> Entity:
    
    with Session(engine) as session:
        query = text(
            """SELECT a.entity_id, a.cosine_similarity
                FROM (SELECT e.id AS entity_id, MAX(1 - (e.name_vector <=> :vector)) AS cosine_similarity 
                        FROM entity AS e
                        JOIN document_entity_link del ON del.entity_id = e.id
                        JOIN source b ON b.document_id = del.document_id
                        WHERE b.user_id = :user_id
                        GROUP BY 1) a
            WHERE a.cosine_similarity >= :threshold
            ORDER BY a.cosine_similarity DESC
            LIMIT 1"""
        )
        result = session.execute(query, {
            'vector':  str(vector.tolist()),
            'user_id': user_id,
            'threshold': threshold
        }).all()

        if len(result) > 0:
            entity_id = result[0][0]
            cosine_similarity = result[0][1]
            return {"entity_id": entity_id, "cosine_similarity": cosine_similarity}
            
        return None

    
def get_question_answer_by_document_id(document_id: int) -> list[Question_Answer]:
    session = Session(engine)
    qas = session.scalars(select(Question_Answer).where(Question_Answer.document_id == document_id)).all()
    session.close()
    return qas



def get_sources_by_user_id(user_id: str) -> list[Source]:
    session = Session(engine)
    sources = session.scalars(
        select(Source)
        .where(Source.user_id == user_id)
        .order_by(Source.update_at.desc())
    ).all()
    session.close()
    return sources


def get_source_by_document_id(document_id: str) -> Source:
    session = Session(engine)
    source = session.scalar(
        select(Source).where(Source.document_id == document_id)
    )
    session.close()
    return source


def get_source_by_url(user_id: str, url: str) -> Source:
    url = html_parser.clean_url(url)
    session = Session(engine)
    source = session.scalar(select(Source).where(
        and_(Source.url == url, Source.user_id == user_id)))
    session.close()
    return source


def get_source_document(id: int) -> Document:
    session = Session(engine)
    doc = session.scalar(select(Document).where(Document.source_id == id))
    session.close()
    return doc


def get_source_by_id(id: str) -> Source:
    session = Session(engine)
    source = session.scalar(select(Source).where(Source.id == id))
    session.close()
    return source


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
        .join(Source, Source.document_id == Document_Entity_Link.document_id)
        .where(Source.user_id == user_id).order_by(Entity.name).distinct()
    ).all()
    session.close()
    return entities


def get_entities_by_user_id_and_type(user_id: str, type: str) -> list[Entity]:
    session = Session(engine)
    entities = session.scalars(
        select(Entity)
        .join(Document, Document.id == Entity.document_id)
        .join(Source, Source.document_id == Document.id)
        .where(Source.user_id == user_id, Entity.type == type)
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


def get_embedding_by_id(embedding_id: int) -> Embedding:
    with Session(engine) as session:
        embedding = session.scalar(select(Embedding).where(Embedding.id == embedding_id))
    return embedding


def calculate_number_of_docs_thredhold(user_id: str) -> int:
    with Session(engine) as session:
        stmt = text("""
            SELECT count(distinct document_id) as docs_count
            FROM public.source
            WHERE user_id = :user_id
            """)
        docs_count = session.scalar(stmt, {"user_id": user_id})
        
        return int(docs_count / 10)

def get_entities_tree_nodes_by_user_id(user_id: str) -> list[TreeNode]:
    
    min_num_docs = calculate_number_of_docs_thredhold(user_id)
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
        JOIN public.source b ON b.document_id = l.document_id
            WHERE b.user_id = :user_id 
        GROUP BY 1) a
        WHERE a.docs_count > :min_num_docs
        """)

    with Session(engine) as session:
        types = session.execute(stmt, {"user_id": user_id, "min_num_docs": min_num_docs}).fetchall()

        for k, t in enumerate(types):
            top_node = TreeNode(label=t.type.title(), key=(t.type.title().replace(" ", "").lower()), doc_count=t.docs_count, doc_ids=[str(id) for id in t.docs_ids], children=[])
            for e_name in t.ents_names:
                ent_node = session.scalar(select(Entity).where(Entity.name == e_name)).to_node()
                if ent_node.doc_count > min_num_docs:
                    top_node.children.append(ent_node)
            # Only add the top node if it has children
            
            if len(top_node.children) > 0:
                results.append(top_node)
            
            
    return results




def get_filter_nodes_by_user_id(user_id: str) -> list[TreeNode]:
    
    filter_nodes = get_entities_tree_nodes_by_user_id(user_id)
    
    filter_nodes.sort(key=lambda x: x.doc_count, reverse=True)

    return filter_nodes