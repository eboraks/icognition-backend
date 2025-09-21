from sqlmodel import Session
from app.models import Content_Type, Entity_Type
from app.db_connector import get_engine
from app.log import get_logger
import json
from sqlalchemy import select

logging = get_logger(__name__)

# Get the same engine used in app_logic
engine = get_engine()

def load_content_types():
    try:
        with open('data/content_types.json', 'r') as f:
            data = json.load(f)
        
        content_types = []
        for category in data['content_types']:
            for type_name in category['types']:
                content_type = Content_Type(
                    name=type_name,
                    description=f"Content type for {type_name}",
                    category=category['category'],
                    follow_up_questions=[]
                )
                content_types.append(content_type)
        
        return content_types
    except Exception as e:
        logging.error(f"Error loading content types: {str(e)}")
        raise e

def load_entity_types():
    try:
        with open('data/schema_types.json', 'r') as f:
            data = json.load(f)
        
        entity_types = []
        for entity_type in data['entity_types']:
            et = Entity_Type(
                name=entity_type['name'],
                description=entity_type['description'],
                follow_up_questions=[]
            )
            entity_types.append(et)
        
        return entity_types
    except Exception as e:
        logging.error(f"Error loading entity types: {str(e)}")
        raise e

def seed_database():
    try:
        with Session(engine) as session:
            # Check if data already exists
            existing_content_types = session.exec(select(Content_Type)).first()
            existing_entity_types = session.exec(select(Entity_Type)).first()
            
            if not existing_content_types:
                # Insert content types
                content_types = load_content_types()
                for ct in content_types:
                    session.add(ct)
                logging.info(f"Added {len(content_types)} content types")
            else:
                logging.info("Content types already exist in database, skipping insertion")
            
            if not existing_entity_types:
                # Insert entity types
                entity_types = load_entity_types()
                for et in entity_types:
                    session.add(et)
                logging.info(f"Added {len(entity_types)} entity types")
            else:
                logging.info("Entity types already exist in database, skipping insertion")
            
            session.commit()
            logging.info("Database seeding completed successfully!")
    except Exception as e:
        logging.error(f"Error seeding database: {str(e)}")
        raise e

if __name__ == "__main__":
    seed_database() 