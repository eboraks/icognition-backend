import pytest
import json
import uuid
import logging
from unittest.mock import Mock, patch, mock_open
from pydantic import BaseModel
from app.models import Chat_Message, Document, EventName, Source
from app.chat_handler import ChatHandler
from app.response_models import Status, Answer
from app.gemini_chat_client import ChatClient
from sqlalchemy.orm import Session
from app.db_connector import get_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text



engine = get_engine()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestResponseModel(BaseModel):
    answer_for_chat: str
    short_answer_for_computer: str
    citations: list
    status: str

@pytest.fixture
def mock_chat_handler():
    # Create mock document
    document_id = str(uuid.uuid4())
    mock_doc = Document(
        id=document_id,
        title="Test Document",
        original_text="Test content"
    )
    
    # Create mock source
    mock_source = Source(
        id=str(uuid.uuid4()),
        user_id="test_user_id",
        html_root_element="<html>Test content</html>"
    )
    
    # Create mock client
    mock_client = Mock(spec=ChatClient)
    
    # Mock the database and client functions
    with patch('app.getters.get_document_by_id') as mock_get_doc, \
         patch('app.getters.get_source_by_document_id') as mock_get_source, \
         patch('app.chat_handler.insert_or_update_chat_history') as mock_insert, \
         patch('app.chat_handler.ChatClient') as mock_chat_client_class:
        
        # Setup mock returns
        mock_get_doc.return_value = mock_doc
        mock_get_source.return_value = mock_source
        mock_insert.side_effect = lambda x: x
        mock_chat_client_class.return_value = mock_client
        
        # Mock the system instruction file read
        with patch('builtins.open', mock_open(read_data="You are a helpful assistant.")):
            # Create chat handler instance with correct parameters
            handler = ChatHandler(
                document_id=document_id,
                user_id="test_user_id",
                temperature=0.5
            )
            
            return handler

def test_successful_response(mock_chat_handler):
    """Test processing a successful response from the client"""
    # Arrange
    expected_response = TestResponseModel(
        answer_for_chat="Test answer",
        short_answer_for_computer="Short answer",
        citations=[],
        status=Status.SUCCESS.value
    )
    mock_chat_handler._client.send_message.return_value = expected_response
    
    # Act
    result = mock_chat_handler._process_chat_step(
        _user_prompt="test question",
        _ai_prompt="test prompt",
        _response_model=TestResponseModel
    )
    
    # Assert
    assert isinstance(result, Chat_Message)
    assert result.user_prompt == "test question"
    assert result.ai_prompt == "test prompt"
    assert result.chat_type == "document"
    assert result.asked_by == "system"
    assert result.event_name == EventName.INIT_DOC_CHAT.value
    
    # Verify response content
    response_data = json.loads(result.response)
    assert response_data["answer_for_chat"] == "Test answer"
    assert response_data["status"] == Status.SUCCESS.value

def test_string_response_handling(mock_chat_handler):
    """Test handling when client returns a string response"""
    # Arrange
    string_response = json.dumps({
        "answer_for_chat": "String response",
        "short_answer_for_computer": "Short",
        "citations": [],
        "status": Status.SUCCESS.value
    })
    mock_chat_handler._client.send_message.return_value = string_response
    
    # Act
    result = mock_chat_handler._process_chat_step(
        _user_prompt="test question",
        _ai_prompt="test prompt",
        _response_model=TestResponseModel
    )
    
    # Assert
    assert isinstance(result, Chat_Message)
    response_data = json.loads(result.response)
    assert response_data["answer_for_chat"] == "String response"
    assert response_data["status"] == Status.SUCCESS.value

def test_failed_response(mock_chat_handler):
    """Test handling a failed response from the client"""
    # Arrange
    failed_response = TestResponseModel(
        answer_for_chat="Error occurred",
        short_answer_for_computer="Error",
        citations=[],
        status="FAILED"
    )
    mock_chat_handler._client.send_message.return_value = failed_response
    
    # Act
    result = mock_chat_handler._process_chat_step(
        _user_prompt="test question",
        _ai_prompt="test prompt",
        _response_model=TestResponseModel
    )
    
    # Assert
    assert isinstance(result, Chat_Message)
    assert result.event_name == EventName.ERROR.value
    response_data = json.loads(result.response)
    assert response_data["status"] == "error"
    assert "Error" in response_data["answer_for_chat"]

def test_exception_handling(mock_chat_handler):
    """Test handling when client raises an exception"""
    # Arrange
    mock_chat_handler._client.send_message.side_effect = Exception("Test error")
    
    # Act
    result = mock_chat_handler._process_chat_step(
        _user_prompt="test question",
        _ai_prompt="test prompt",
        _response_model=TestResponseModel
    )
    
    # Assert
    assert isinstance(result, Chat_Message)
    assert result.event_name == EventName.ERROR.value
    response_data = json.loads(result.response)
    assert response_data["status"] == "error"
    assert "Test error" in response_data["answer_for_chat"]

@pytest.mark.integration
def test_process_chat_step_real():
    """Integration test for _process_chat_step using real API calls"""
    # Test database connection first
    try:
        with Session(engine) as session:
            session.execute(text("SELECT 1"))
            logger.info("Database connection successful")
    except SQLAlchemyError as e:
        logger.error(f"Database connection failed: {str(e)}")
        pytest.fail("Could not connect to database")

    # Create a real document
    document_id = str(uuid.uuid4())
    test_doc = Document(
        id=document_id,
        title="Test Document",
        original_text="This is a test document about artificial intelligence and machine learning."
    )
    
    # Create a real source
    source_id = str(uuid.uuid4())
    test_source = Source(
        id=source_id,
        user_id="test_user",
        document_id=document_id,  # Link source to document
        html_root_element="""
        <html>
            <body>
                <h1>Artificial Intelligence Overview</h1>
                <p>Artificial Intelligence (AI) is transforming how we live and work. 
                Machine learning, a subset of AI, enables computers to learn from data 
                without being explicitly programmed.</p>
                <p>Key applications include:</p>
                <ul>
                    <li>Natural Language Processing</li>
                    <li>Computer Vision</li>
                    <li>Robotics</li>
                </ul>
            </body>
        </html>
        """
    )
    
    logger.info(f"Created test document with ID: {document_id}")
    logger.info(f"Created test source with ID: {source_id}")
    
    # Insert test data into database
    with Session(engine) as session:
        try:
            # Insert document and source
            session.add(test_doc)
            session.flush()  # Flush to catch any immediate database errors
            logger.info("Added document to session")
            
            session.add(test_source)
            session.flush()  # Flush to catch any immediate database errors
            logger.info("Added source to session")
            
            session.commit()
            logger.info("Successfully committed test data to database")
            
            # Initialize real ChatHandler
            handler = ChatHandler(
                document_id=document_id,
                user_id="test_user",
                temperature=0.5
            )
            
            logger.info("Created ChatHandler instance")
            
            # Test with a real prompt
            result = handler._process_chat_step(
                _user_prompt="What is the main topic of this document?",
                _ai_prompt="Please provide a concise answer.",
                _response_model=Answer
            )
            
            # Verify the response
            assert isinstance(result, Chat_Message)
            assert result.user_prompt == "What is the main topic of this document?"
            assert result.chat_type == "document"
            assert result.asked_by == "system"
            
            # Check response content
            response_data = json.loads(result.response)
            assert "answer_for_chat" in response_data
            assert "citations" in response_data
            assert "status" in response_data
            logger.info(f"API Response: {response_data['answer_for_chat']}")
            
            # Test with a more complex query
            result = handler._process_chat_step(
                _user_prompt="What are the key applications mentioned in the document?",
                _ai_prompt="List them in bullet points.",
                _response_model=Answer
            )
            
            # Verify the response
            assert isinstance(result, Chat_Message)
            response_data = json.loads(result.response)
            assert "answer_for_chat" in response_data
            logger.info(f"API Response for applications: {response_data['answer_for_chat']}")
            
            # Test error handling with invalid input
            result = handler._process_chat_step(
                _user_prompt="",  # Empty prompt to test error handling
                _ai_prompt="",
                _response_model=Answer
            )
            
            # Verify error handling
            assert isinstance(result, Chat_Message)
            response_data = json.loads(result.response)
            assert response_data["status"] == "error" or "error" in response_data["answer_for_chat"].lower()
            
        except Exception as e:
            logger.error(f"Test failed with error: {str(e)}")
            raise
        finally:
            try:
                # Cleanup: Delete test data
                logger.info("Starting cleanup...")
                session.query(Chat_Message).filter(Chat_Message.chat_id == document_id).delete()
                logger.info("Deleted chat messages")
                session.query(Source).filter(Source.id == source_id).delete()
                logger.info("Deleted test source")
                session.query(Document).filter(Document.id == document_id).delete()
                logger.info("Deleted test document")
                session.commit()
                logger.info("Cleanup completed successfully")
            except Exception as e:
                logger.error(f"Cleanup failed: {str(e)}")
                session.rollback()
                raise

if __name__ == "__main__":
    # This allows running this test file directly for quick testing
    pytest.main([__file__, "-v"])