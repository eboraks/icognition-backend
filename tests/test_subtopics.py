import json
from app.transformers_util import get_util, get_model
from app.models import Document, SubTopic, SubTopic_Document_Link, SubTopic_Embedding_Link, SubTopic_Entity_Link, Entity
from app.db_connector import get_engine
import app.subtopics_util as subtopics_util
import app.getters as getter
import app.app_logic as app_logic
from sqlalchemy.orm import Session
from sqlalchemy import delete, select
import pytest 

user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'
engine = get_engine()


def test_clear_database():
    
    ## Clear the database before the test
    clear_database()


def clear_database():
    engine = get_engine()
    with Session(engine) as session:

        delete_entity_links = session.scalars(select(SubTopic_Entity_Link)).all()
        for link in delete_entity_links:
            session.delete(link)
        
        delete_document_link = session.scalars(select(SubTopic_Document_Link)).all()
        for link in delete_document_link:
            session.delete(link)

        delete_embedding_link = session.scalars(select(SubTopic_Embedding_Link)).all()
        for link in delete_embedding_link:
            session.delete(link)

        delete_subtopics = session.scalars(select(SubTopic)).all()
        for subtopic in delete_subtopics:
            session.delete(subtopic)
        
        session.commit()

@pytest.mark.asyncio
async def test_factory():

    ## Clear the database before the test
    clear_database()

    import app.subtopics_util as subtopics_util ## Need to be imported within async becuase it's calling aiohttp via togeter client
    engine = get_engine()
    ts_util = get_util()
    model = get_model()

    
    user_id = "yU13Hk9BwEQiREgh91YM6EFKR7M2"
    groups_1_2_clousters_names = ['Retrieval-Augmented Generation (RAG)', 'Basketball Career of Marquese Chriss', 
                         'Vector Search and Databases', "Nir Eyal's Books and Teachings"]
    ent_str_group_one = ['{"document_id":127,"name":"retrieval-augmented generation (RAG)","description":"Retrieval-augmented generation (RAG) is a technique used to enhance response accuracy and reliability of generative AI models by fetching facts from external sources.","type":"technology","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Retrieval-Augmented Generation (RAG)","description":"Retrieval-Augmented Generation (RAG) is a method of natural language processing that combines retrieval of information from an external source with generation of new text.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"University of Washington","description":"A public research university in Seattle, Washington, where Marquese Chriss played basketball for two years","type":"educational institution","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"Sacramento","description":"The capital city of California, where Marquese Chriss grew up and played football and basketball","type":"location","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Vector search retrieval methods","description":"Vector search retrieval methods are a way of searching for information based on the similarity of vectors in a high-dimensional space.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Vector indexes","description":"Vector indexes are a way of organizing and searching for vectors in a high-dimensional space, based on their similarity to a given query vector.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Hybrid retrieval approach","description":"Hybrid retrieval approach is a method of searching for information that combines multiple types of search methods, such as vector search and keyword search, to improve the accuracy and comprehensiveness of the results.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":133,"name":"Nir Eyal","description":"A former lecturer at Stanford and the bestselling author of Hooked: How to Build Habit-Forming Products and Indistractable: How to Control Your Attention and Choose Your Life","type":"people","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Hooked","description":"A book written by Nir Eyal about habit-forming products","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Nir Eyal","description":"Author of the article and expert on habit-forming products","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Hooked: How to Build Habit-Forming Products","description":"A book written by Nir Eyal about building products that people can\'t put down","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":134,"name":"Nir Eyal","description":"Author of the book \'Indistractable: How to Control Your Attention and Choose Your Life\'","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}']
    ent_str_group_two = ['{"document_id":132,"name":"RAG","description":"Retrieval Augmented Generation (RAG) is a framework that augments prompt with additional context for more relevant and recent LLM (Language Model) output","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"Lorenzo Romar","description":"The former head coach of the University of Washington men\'s basketball team, who coached Marquese Chriss for two years","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":132,"name":"vector database","description":"A vector database is a type of database that stores and retrieves vector data, which can be used for semantic search and other machine learning tasks","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":132,"name":"semantic search","description":"Semantic search is a type of search that uses machine learning techniques to understand the meaning of a query and retrieve relevant results","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":133,"name":"Indistractable","description":"A book written by Nir Eyal that offers strategies for controlling your attention and choosing your life","type":"books","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Indistractable","description":"A book written by Nir Eyal about controlling attention and choosing your life","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Indistractable: How to Control Your Attention and Choose Your Life","description":"A book written by Nir Eyal about taking control of your attention and focusing on what matters","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Nir Eyal","description":"Author of the article and bestselling author of Hooked and Indistractable","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}']
    
    group_three_clusters_names = ["Video Conferencing Platforms", "Detroit Pistons Players"]
    ent_str_group_three = ['{"document_id":136,"name":"Zoom","description":"A company that provides video conferencing services","type":"company","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"virtual meetings","description":"Meetings held through video conferencing technology","type":"topic","id":null,"source":null,"wikidata_id":null,"score":null}']

    
    ## Make sure there are not subtopics in the database
    subtopics = getter.get_subtopics(user_id)
    assert len(subtopics) == 0
    
    ##insert_entities_group(ent_str_group_one)  
   
    subtopics =  await subtopics_util.subtopics_factory(user_id, minimum_community_size=2)
    assert len(subtopics) > 0
     

    ## Test the names of the subtopics
    for subtopic in subtopics:
        assert subtopic.name is not None

        distances = []
        for group_name in groups_1_2_clousters_names:
            distance = ts_util.cos_sim(model.encode(subtopic.name), model.encode(group_name))
            distances.append(distance)
        ## Making sure that at least one subtopic is similar to one of the existing subtopics
        ## Because the sample is small, the freshold is low
        assert max(distances) > 0.1

    ## Assert that subtopics are stored in the database
    with Session(engine) as session:
        for subtopic in subtopics:
            session.add(subtopic)
            session.refresh(subtopic)
            assert len(subtopic.embeddings) > 0
            assert (len(subtopic.entities) > 0 or len(subtopic.documents) > 0)
            assert subtopic.key_words is not None
            assert len(subtopic.vector.tolist()) > 0
            

def test_get_subtopics():
    subtopics = getter.get_subtopics_display(user_id)
    max_index = len(subtopics) - 1
    assert subtopics[0].number_of_docs > subtopics[max_index].number_of_docs