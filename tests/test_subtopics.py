import json
from app.transformers_util import get_util, get_model
from app.models import Document, SubTopic, SubTopic_Entity_Link, Entity
from app.db_connector import get_engine
import app.subtopics_util as subtopics_util
import app.app_logic as app_logic
from sqlalchemy.orm import Session
from sqlalchemy import delete, select
import pytest 

user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'
engine = get_engine()


def test_entity_existing():
    new_entity = Entity(name="Larry David", description="Comedian, writer, actor, and television producer", type="person")
    exist = app_logic.entity_exists(new_entity)
    assert exist.id is not None


def test_delete_doc_entities():
    
    with Session(engine) as session:
        # get all entities with document_id 243
        entities = session.scalars(select(Entity).filter(Entity.document_id == 243)).all()
        # Delete all subtopic with entities
        subtopics = session.scalars(select(SubTopic).join(SubTopic_Entity_Link)\
                                    .filter(SubTopic_Entity_Link.entity_id.in_(
                                        [entity.id for entity in entities]))).all()
        entity_links = session.scalars(select(SubTopic_Entity_Link)\
                                      .filter(SubTopic_Entity_Link.entity_id.in_(
                                          [entity.id for entity in entities]))).all()
        for link in entity_links:
            session.delete(link)
        
        for subtopic in subtopics:
            session.delete(subtopic)

        for entity in entities:    
            session.delete(entity)
        session.commit()


@pytest.mark.asyncio
async def test_generate_entitiies_for_test_doc():

    ## Get document 243
    with Session(engine) as session:
        doc = session.scalars(select(Document).filter(Document.id == 243)).one()
        assert doc is not None
    
    await app_logic.extract_info_from_doc(doc)


def insert_entities_group(entities_group):
    engine = get_engine()
    with Session(engine) as session:
        entities = [Entity(**json.loads(ent_str)) for ent_str in entities_group]
        
        for entity in entities:
            ## Hacking the score to be 0.99 to make easy to find those entities
            entity.score = 0.99
            session.add(entity)
        
        session.commit()

        assert entities[0].id is not None

def clear_database():
    engine = get_engine()
    with Session(engine) as session:

        delete_links = session.scalars(select(SubTopic_Entity_Link).join(Entity).filter(Entity.score == 0.99)).all()
        for link in delete_links:
            session.delete(link)
        
        delete_subtopics = session.scalars(select(SubTopic).outerjoin(SubTopic_Entity_Link).where(SubTopic_Entity_Link.subtopic_id == None)).all()
        for subtopic in delete_subtopics:
            session.delete(subtopic)
        
        delete_entities = session.scalars(select(Entity).filter(Entity.score == 0.99)).all()
        for entity in delete_entities:
            session.delete(entity)
        
        session.commit()


@pytest.mark.asyncio
async def test_workflow():

    ## Clear database before the test
    clear_database()

    import app.subtopics_util as subtopics_util ## Need to be imported within async becuase it's calling aiohttp via togeter client
    engine = get_engine()
    ts_util = get_util()
    model = get_model()


    groups_1_2_clousters_names = ['Retrieval-Augmented Generation (RAG)', 'Basketball Career of Marquese Chriss', 
                         'Vector Search and Databases', "Nir Eyal's Books and Teachings"]
    ent_str_group_one = ['{"document_id":127,"name":"retrieval-augmented generation (RAG)","description":"Retrieval-augmented generation (RAG) is a technique used to enhance response accuracy and reliability of generative AI models by fetching facts from external sources.","type":"technology","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Retrieval-Augmented Generation (RAG)","description":"Retrieval-Augmented Generation (RAG) is a method of natural language processing that combines retrieval of information from an external source with generation of new text.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"University of Washington","description":"A public research university in Seattle, Washington, where Marquese Chriss played basketball for two years","type":"educational institution","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"Sacramento","description":"The capital city of California, where Marquese Chriss grew up and played football and basketball","type":"location","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Vector search retrieval methods","description":"Vector search retrieval methods are a way of searching for information based on the similarity of vectors in a high-dimensional space.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Vector indexes","description":"Vector indexes are a way of organizing and searching for vectors in a high-dimensional space, based on their similarity to a given query vector.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":128,"name":"Hybrid retrieval approach","description":"Hybrid retrieval approach is a method of searching for information that combines multiple types of search methods, such as vector search and keyword search, to improve the accuracy and comprehensiveness of the results.","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":133,"name":"Nir Eyal","description":"A former lecturer at Stanford and the bestselling author of Hooked: How to Build Habit-Forming Products and Indistractable: How to Control Your Attention and Choose Your Life","type":"people","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Hooked","description":"A book written by Nir Eyal about habit-forming products","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Nir Eyal","description":"Author of the article and expert on habit-forming products","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Hooked: How to Build Habit-Forming Products","description":"A book written by Nir Eyal about building products that people can\'t put down","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":134,"name":"Nir Eyal","description":"Author of the book \'Indistractable: How to Control Your Attention and Choose Your Life\'","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}']
    ent_str_group_two = ['{"document_id":132,"name":"RAG","description":"Retrieval Augmented Generation (RAG) is a framework that augments prompt with additional context for more relevant and recent LLM (Language Model) output","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":131,"name":"Lorenzo Romar","description":"The former head coach of the University of Washington men\'s basketball team, who coached Marquese Chriss for two years","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":132,"name":"vector database","description":"A vector database is a type of database that stores and retrieves vector data, which can be used for semantic search and other machine learning tasks","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":132,"name":"semantic search","description":"Semantic search is a type of search that uses machine learning techniques to understand the meaning of a query and retrieve relevant results","type":"concepts","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":133,"name":"Indistractable","description":"A book written by Nir Eyal that offers strategies for controlling your attention and choosing your life","type":"books","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Indistractable","description":"A book written by Nir Eyal about controlling attention and choosing your life","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":135,"name":"Indistractable: How to Control Your Attention and Choose Your Life","description":"A book written by Nir Eyal about taking control of your attention and focusing on what matters","type":"book","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"Nir Eyal","description":"Author of the article and bestselling author of Hooked and Indistractable","type":"person","id":null,"source":null,"wikidata_id":null,"score":null}']
    
    group_three_clusters_names = ["Video Conferencing Platforms", "Detroit Pistons Players"]
    ent_str_group_three = ['{"document_id":136,"name":"Zoom","description":"A company that provides video conferencing services","type":"company","id":null,"source":null,"wikidata_id":null,"score":null}', '{"document_id":136,"name":"virtual meetings","description":"Meetings held through video conferencing technology","type":"topic","id":null,"source":null,"wikidata_id":null,"score":null}']

    ## Create first group of entities
    insert_entities_group(ent_str_group_one)

    ## Generate embedding for the entities
    await app_logic.generate_entities_embeddings()

    user_id = "yU13Hk9BwEQiREgh91YM6EFKR7M2"

    entities = subtopics_util.get_entities(user_id)
    
    ## Using score 0.99 to filter the entities that should be used in this testing
    entities = [entity for entity in entities if entity.score == 0.99]


    ## Test if entities match one of the existing subtopics. At this point of the test
    ## there are no subtopics created yet, so we expect the function to return all entities list
    subtopics = subtopics_util.get_subtopics(user_id)
    assert len(subtopics) == 0

    new_entities = subtopics_util.add_entities_to_subtopic(subtopics=subtopics, entities=entities)
    assert len(new_entities) == len(entities)

    if(len(entities) > 0):
        clusters = subtopics_util.generate_clusters(entities,  minimum_community_size=2)
        assert len(clusters) == 4


    subtopics = []
    for cluster in clusters:
        subtopic = await subtopics_util.create_subtopic(user_id, cluster, entities)
        assert subtopic.name is not None
        distances = []
        for group_name in groups_1_2_clousters_names:
            distance = ts_util.cos_sim(model.encode(subtopic.name), model.encode(group_name))
            distances.append(distance)
        ## Making sure that at least one subtopic is similar to one of the existing subtopics
        subtopics.append(subtopic)
        assert max(distances) > 0.1
       

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
    subtopics = subtopics_util.get_subtopics(user_id)
    assert len(subtopics) == 0
    
    insert_entities_group(ent_str_group_one)  
   
    ## Generate embedding for the entities
    await app_logic.generate_entities_embeddings()

    entities = subtopics_util.get_entities(user_id)
    
    ## Using score 0.99 to filter the entities that should be used in this testing
    entities = [entity for entity in entities if entity.score == 0.99]

    subtopics =  await subtopics_util.subtopics_factory(user_id, entities, minimum_community_size=2)
    assert len(subtopics) > 0
    assert len(subtopics) == 4

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

    ## Save the number of entities each subtopic has, this is to test the next step
    subtopics_num_of_entities = {}
    with Session(engine) as session:
        for subtopic in subtopics:
            session.add(subtopic)
            session.refresh(subtopic)
            assert len(subtopic.entities) > 0
            subtopics_num_of_entities[subtopic.name] = len(subtopic.entities)
            assert subtopics_num_of_entities[subtopic.name] > 0

    ## Test the next step of the factory
    insert_entities_group(ent_str_group_two)
    ## Generate embedding for the entities
    await app_logic.generate_entities_embeddings()

    entities_2 = subtopics_util.get_entities(user_id)
    
    ## Using score 0.99 to filter the entities that should be used in this testing
    entities_2 = [entity for entity in entities_2 if entity.score == 0.99]
    ## Making sure the same number of entities are returned
    assert len(entities_2) == len(ent_str_group_two)

    subtopics_2 =  await subtopics_util.subtopics_factory(user_id, entities_2, minimum_community_size=2)
    # In group two, the entities that are similar to the first group, so we expect fewer subtopics if any
    assert len(subtopics) > len(subtopics_2)

    ## Getting all subtopics from the database
    all_subtopics = subtopics_util.get_subtopics(user_id)

    ## There should the same number of more subtopics
    assert len(all_subtopics) == len(subtopics) + len(subtopics_2)

    with Session(engine) as session:    
        for subtopic in all_subtopics:
            session.add(subtopic)
            ## Making sure that the number of entities in the subtopic is the same as before
            if subtopic.name in subtopics_num_of_entities.keys():
                assert len(subtopic.entities) >= subtopics_num_of_entities[subtopic.name]