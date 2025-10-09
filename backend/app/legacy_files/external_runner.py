## External running for long running tasks

import sys
import os
from pathlib import Path
import asyncio

# Add the parent directory to Python path so we can import app
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from app.log import get_logger
import app.entity_handler as entity_handler
import app.getters as getter
import app.app_logic as app_logic

logger = get_logger(__name__)

def test_function(*args):
    """Test function that prints its arguments"""
    logger.info(f"Test function called with args: {args}")
    return f"Test function completed with args: {args}"

async def generate_document_entities(document_id: str):
    document = getter.get_document_by_id(document_id)
    user_id = getter.get_source_by_document_id(document_id).user_id

    try:
        if len(getter.get_entities_ids_by_document_id(document.id)) == 0:
            ent_success = await entity_handler.generate_entities(
                user_id=user_id, doc=document
            )
            topic_success = await entity_handler.generate_topics(
                user_id=user_id, doc=document
            )
            logger.info(
                f"Background task for generating entities and topics for: {document.id} completed. Result, number of entities: {len(ent_success)} number of topics: {len(topic_success)}"
            )
            await app_logic.generate_embeddings_for_entities(
                entities=ent_success, user_id=user_id
            )
            await app_logic.generate_embeddings_for_entities(
                entities=topic_success, user_id=user_id
            )
    except Exception as e:
        logger.error(f"Generate document entities error: {str(e)}")
        raise e

def run_async_function(func, *args):
    """Helper function to run async functions"""
    asyncio.run(func(*args))

# Map of available functions
AVAILABLE_FUNCTIONS = {
    "test_function": test_function,
    "generate_document_entities": lambda *args: run_async_function(generate_document_entities, *args),
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("No function name provided")
        sys.exit(1)
        
    function_name = sys.argv[1]
    args = sys.argv[2:]
    
    if function_name not in AVAILABLE_FUNCTIONS:
        logger.error(f"Unknown function: {function_name}")
        sys.exit(1)
        
    try:
        # Call the function with provided arguments
        result = AVAILABLE_FUNCTIONS[function_name](*args)
        logger.info(f"Function {function_name} completed successfully")
        print(result)  # This will be captured in stdout
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error executing {function_name}: {str(e)}")
        sys.exit(1)