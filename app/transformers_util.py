from sentence_transformers import SentenceTransformer, util
from app.models import Document, Entity, Document_Embeddings


# Other model that were tested, they more all less all the same - all-mpnet-base-v2, all-MiniLM-L6-v2, all-MiniLM-L12-v2, paraphrase-multilingual-MiniLM-L12-v2
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device='cpu')
model.encode("Encode this on startup to avoid latency")

def get_util():
    return util

def get_model():
    return model

def generate_embeddings(term: str) -> list[float]:
    return model.encode(term,  show_progress_bar=True, convert_to_tensor=True)


async def get_entity_embeddings(entities: list[Entity]) -> list[Entity]:
    for entity in entities:
        entity.embedding = model.encode(f"{entity.name} ({entity.type}) {entity.description}", convert_to_tensor=True)
    return entities




async def get_document_embeddings(
    documents: list[Document],
) -> list[Document_Embeddings]:

    results = []
    for document in documents:

        if document.title:
            results.append(
                Document_Embeddings(
                    document_id=document.id,
                    field="title",
                    embeddings=model.encode(document.title),
                )
            )

        if document.short_summary:
            results.append(
                Document_Embeddings(
                    document_id=document.id,
                    field="short_summary",
                    embeddings=model.encode(document.short_summary),
                )
            )
        if document.summary_bullet_points:
            for bullet_point in document.summary_bullet_points:
                results.append(
                    Document_Embeddings(
                        document_id=document.id,
                        field="summary_bullet_points",
                        embeddings=model.encode(bullet_point),
                    )
                )

    return results
