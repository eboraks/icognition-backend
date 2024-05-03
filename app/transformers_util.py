from sentence_transformers import SentenceTransformer, util
from app.models import Document, Entity


# Other model that were tested, they more all less all the same - all-mpnet-base-v2, all-MiniLM-L6-v2, all-MiniLM-L12-v2, paraphrase-multilingual-MiniLM-L12-v2
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device='cpu')
model.encode("Encode this on startup to avoid latency")

def get_util():
    return util

def get_model():
    return model

def generate_embeddings(term: str) -> list[float]:
    return model.encode(term,  show_progress_bar=False, convert_to_tensor=True)


async def get_entity_embeddings(entities: list[Entity]) -> list[Entity]:
    for entity in entities:
        entity.embedding = model.encode(f"{entity.name} ({entity.type}) {entity.description}", convert_to_tensor=True)
    return entities


