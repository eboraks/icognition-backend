import json
import asyncio
from typing import Callable, List, Optional, Dict
from pydantic import BaseModel
import logging

from app.gemini_chat_client import ChatClient
import app.getters as getters


from app.app_logic import insert_or_update_chat_history
from app.models import Chat_Message, Document, EventName, BroadcastMessage, WebSocketMessageType
from app.response_models import Answer, ContentType, PageContent, Summary,  Status, SuggestedQuestions, get_model_class, ExtractedEntity, Entities
import app.app_logic as  app_logic
from app.entity_handler import insert_entities

# Set up logger
logger = logging.getLogger(__name__)


class ChatHandler:
    def __init__(self, document_id: str = None, collection_id: str = None, user_id: str = None, temperature: float = 0.5, event_listener: Callable = None):
        self._user_id = user_id
        self._temperature = temperature
        self._event_listener = event_listener
        self._context_type = "document" if document_id else "collection"
        self._context_id = document_id if document_id else collection_id
        
        # Load context data
        if self._context_type == "document" and document_id:
            self._doc = getters.get_document_by_id(document_id)
            source = getters.get_source_by_document_id(document_id)
            if source is None:
                raise ValueError("Document or source not found")
            self._source = source
        elif self._context_type == "collection" and collection_id:
            self._doc = getters.get_study_collection_by_id(collection_id)
        
        # Initialize chat client
        system_instruction = None
        try:
            with open("app/chat_workflows/chat_system_instructions.txt", "r") as f:
                system_instruction = f.read()
        except Exception as e:
            logger.error(f"Error loading system instruction: {str(e)}")
            system_instruction = "You are a helpful assistant."
        
        self._client = ChatClient(
            response_model=Answer, 
            system_instruction=system_instruction
        )
        
        # Set chat history if available
        if self._context_id:
            chat_history = getters.get_chat_history(self._context_id)
            if chat_history:
                self._client.set_chat_history(chat_history)
    
    
    def _get_model_from_name(self, model_name: str) -> Optional[BaseModel]:
        """Get a model instance from its name"""
        model_class = get_model_class(model_name)
        if model_class:
            return model_class()
        return None

    def _process_chat_step(self, _user_prompt: str, 
                           _ai_prompt: str, 
                           _response_model: BaseModel, 
                           _asked_by: str = "system", 
                           _chat_type: str = "document", 
                           _event_name: str = EventName.INIT_DOC_CHAT.value, 
                           _save_to_db: bool = True) -> Chat_Message:
        try:
            response = self._client.send_message(prompt = _user_prompt + " " + _ai_prompt, response_model = _response_model)
            
            if type(response) == str:
                ## Try to parse the answer as a json
                try:
                    response = json.loads(response)
                    message = Chat_Message(
                        chat_id = self._doc.id,
                        chat_type = _chat_type,
                        user_id = self._user_id, 
                        user_prompt = _user_prompt,
                        ai_prompt = _ai_prompt,
                        asked_by = _asked_by,
                        response = json.dumps(response),
                        response_model = _response_model.__class__.__name__,
                        event_name = _event_name
                    )
                    if _save_to_db:
                        message = insert_or_update_chat_history(message)
                    
                    return message
                except Exception as e:  
                    logger.error(f"Error parsing answer: {str(e)}")
                    return None
            
            if response.status == Status.SUCCESS.value or response.status == Status.SUCCESS:
                message = Chat_Message(
                    chat_id = self._doc.id,
                    chat_type = _chat_type,
                    user_id = self._user_id, 
                    user_prompt = _user_prompt,
                    ai_prompt = _ai_prompt,
                    asked_by = _asked_by,
                    response = response.model_dump_json(),
                    response_model = _response_model.__class__.__name__,
                    event_name = _event_name
                )
                message = insert_or_update_chat_history(message)
                
                return message
            else:
                logger.error(f"Error in _process_chat_step: {response.status}")
                # Create an error message
                error_response = {
                    "answer_for_chat": f"Error: {response.status}",
                    "short_answer_for_computer": f"Error: {response.status}",
                    "citations": [],
                    "status": "error"
                }
                
                message = Chat_Message(
                    chat_id = self._doc.id,
                    chat_type = _chat_type,
                    user_id = self._user_id, 
                    user_prompt = _user_prompt,
                    ai_prompt = _ai_prompt,
                    asked_by = _asked_by,
                    response = json.dumps(error_response),
                    response_model = _response_model.__class__.__name__,
                    event_name = EventName.ERROR.value
                )
                message = insert_or_update_chat_history(message)
                return message
            
        except Exception as e:
            logger.error(f"Error in _process_chat_step: {str(e)}. User prompt: {_user_prompt}.")
            # Create an error message
            error_response = {
                "answer_for_chat": f"Error: {str(e)}",
                "short_answer_for_computer": f"Error: {str(e)}",
                "citations": [],
                "status": "error"
            }
            
            message = Chat_Message(
                chat_id = self._doc.id,
                chat_type = _chat_type,
                user_id = self._user_id, 
                user_prompt = _user_prompt,
                ai_prompt = _ai_prompt,
                asked_by = _asked_by,
                response = json.dumps(error_response),
                response_model = _response_model.__class__.__name__,
                event_name = EventName.ERROR.value
            )
            message = insert_or_update_chat_history(message)
            return message
    
    
    def start_analyze(self, doc: Document):
        
        ## If the chat is already initiated, retrieve summary and suggested questions braodcast them to client
        if self.chat_status(self._doc.id):
            
            summary_messages = getters.get_chat_messages(user_id = self._user_id, 
                                                       document_id = doc.id)

            asyncio.run(self._event_listener(BroadcastMessage(
                user_id=self._user_id,
                message_type= WebSocketMessageType.CHAT_READY.value,
                document_id= str(self._doc.id),
                data=[chat.to_dict() for chat in summary_messages]
            )))
            return True
        
        ## TODO, I need to improve the logic inf case we have summary and suggested questoin, but missing other type like entities

        ## Get the chat history and if it exists, send event that the chat is already initiated
        chat_history = getters.get_chat_history(self._doc.id)
        event_names = [message.event_name for message in chat_history]
        
        ## Get the content types and entity types
        content_types = getters.get_content_types()
        entity_types = getters.get_entity_types()
        
        ## Identify the level of bias in the content
        try: 
            with open("app/data/bias_categorization.json", "r") as f:
                bias_categorization = json.load(f)
        except Exception as e:
            logger.error(f"Error loading bias categorization: {str(e)}")
            bias_categorization = []
        
        

        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=10,
            document_id=self._doc.id
        )))
        
        
        ## Send the initial chat message
        if EventName.INIT_DOC_CHAT.value not in event_names:
            content_message = self._process_chat_step(
                _user_prompt = """Here is a page from the web. Please extract the title, 
                publication date, authoers and other information. 
                Here is the page:
                """,
                _ai_prompt = self._source.html_root_element[:400000],
                _response_model = PageContent,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.INIT_DOC_CHAT.value
            )
        
            if content_message is None:
                logger.error("Error in content response")
                asyncio.run(self._event_listener(BroadcastMessage(
                    user_id=self._user_id,
                    message_type=WebSocketMessageType.ERROR.value,
                    data=f"Error in content response",
                    document_id=self._doc.id
                )))
            else:
                try:
                    # Parse the response JSON to get the content data
                    content_response = json.loads(content_message.response)
                    if doc.title is None:
                        doc.title = content_response.get("title", "Untitled")
                    if doc.publication_date is None:
                        doc.publication_date = content_response.get("published_date", None)
                    if doc.authors is None:
                        doc.authors = content_response.get("authors", None)
                except Exception as e:
                    logger.error(f"Error in content response: {str(e)}")
                    asyncio.run(self._event_listener(BroadcastMessage(
                        user_id=self._user_id,
                        message_type=WebSocketMessageType.ERROR.value,
                        data=f"Error in content response: {str(e)}",
                        document_id=self._doc.id
                    )))
                
                
        ## Send progress percentage
        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=30,
            document_id=self._doc.id
        )))

       

        if EventName.CONTENT_TYPE.value not in event_names:
            content_type_message = self._process_chat_step(
                _user_prompt = "Categorize the type of the content. ",
                _ai_prompt = """Is it news article, blog post, product description, etc. 
                Use the following content types as a reference: """ + str(content_types),
                _response_model = ContentType,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.CONTENT_TYPE.value
            )
            
            # Parse the response JSON to get the content type
            content_type_data = json.loads(content_type_message.response)
            doc.content_type = content_type_data.get("content_type", "content")
        else:
            # Find the content type message in chat history
            content_type_message = next((msg for msg in chat_history if msg.event_name == EventName.CONTENT_TYPE.value), None)
            if content_type_message:
                content_type_data = json.loads(content_type_message.response)
                doc.content_type = content_type_data.get("content_type", "content")
            else:
                doc.content_type = "content"
        
    
        
        

        asyncio.run(self._event_listener(BroadcastMessage(
            user_id=self._user_id,
            message_type=WebSocketMessageType.PROGRESS_PERCENTAGE.value,
            data=20,
            document_id=self._doc.id
        )))

        content_name = doc.title if doc.title else doc.content_type
        
        if len(bias_categorization) > 0:
            if EventName.BIAS_CATEGORIZATION.value not in event_names:
                bias_message = self._process_chat_step(
                    _user_prompt = f"Identify the level of bias in the {content_name}. ",
                    _ai_prompt = """Use the following bias categorization to identify the level of bias: """ + json.dumps(bias_categorization),
                    _response_model = Answer,
                    _asked_by = "system",
                    _chat_type = "document",
                    _event_name = EventName.BIAS_CATEGORIZATION.value
                )
                
                # Parse the response JSON to get the bias data
                bias_data = json.loads(bias_message.response)
                bias_answer = bias_data.get("answer_for_chat", "No bias information available")
        else:
            bias_answer = "No bias information available"
        
        if EventName.SUMMARY.value not in event_names:
            summary_message = self.generate_initial_summary(bias_answer)
             
            if summary_message is None:
                logger.error("Error in summary response")
                asyncio.run(self._event_listener(BroadcastMessage(
                    user_id=self._user_id,
                    message_type=WebSocketMessageType.ERROR.value,
                    data=f"Error in summary response",
                    document_id=self._doc.id
                )))
            else:
                data = json.loads(summary_message.response)
                summary_answer = data.get("answer_for_chat", "No summary available")
                doc.ai_is_about = summary_answer
                logger.info(f"Summary: {summary_answer[:100]}")
                asyncio.run(self._event_listener(BroadcastMessage(
                    user_id=self._user_id,
                    message_type=WebSocketMessageType.CHAT_READY.value,
                    data=[summary_message.to_dict()],
                    document_id=self._doc.id
                )))
        
        
        if EventName.SUGGESTED_QUESTIONS.value not in event_names:
            suggested_questions = self.generate_suggested_chat_questions()
            
            # Broadcast the suggested questions to the client
            if suggested_questions:
                asyncio.run(self._event_listener(BroadcastMessage(
                    user_id=self._user_id,
                    message_type=WebSocketMessageType.SUGGESTED_QUESTIONS.value,
                    data=suggested_questions,
                    document_id=self._doc.id
                )))
        
        
        
        if EventName.BULLETS_POINTS.value not in event_names:
            bullets_message = self._process_chat_step(
                _user_prompt = f"Summaries the main idea in the \"{content_name}\" and create a short overview in bullet points that is easy to understand",
                _ai_prompt = "",
                _response_model = Summary,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.BULLETS_POINTS.value
            )
            
            # Parse the response JSON to get the bullet points data
            bullets_data = json.loads(bullets_message.response)
            bullets_summary = bullets_data.get("important_bullet_points", ["No bullet points available"])
            doc.ai_bullet_points = bullets_summary
            logger.info(f"Summary: {bullets_summary}")
    
    
        
        if EventName.ENTITIES.value not in event_names:
            entities_message = self._process_chat_step(
                _user_prompt = f"Identify the entities in the {content_name}",
                _ai_prompt = """Use the following schema.org entities as a reference: """ + str(entity_types),
                _response_model = Entities,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.ENTITIES.value
            )
            
            # Parse the response JSON to get the entities data
            if entities_message is not None:
                entities_data = json.loads(entities_message.response)
                entities_answer = entities_data.get("entities", ["No entities available"])
                logger.info(f"Entities: {entities_answer}")
                # Store the entities list directly as a list of dicts, no need for json.dumps()
                # since types_and_concepts is already a JSONB column that accepts lists/dicts
                doc.types_and_concepts = entities_answer
                
                ## Insert the entities into the database
                asyncio.run(insert_entities(self._user_id, entities_answer, self._doc.id))
        
        
        if len(doc.source_text_in_html) == 0:
            source_text = self._process_chat_step(
                _user_prompt = """Extract the text from the page and format it in simple HTML with headers, paragraphs, lists, etc.
                No div, span, or other html tags. The text should be in the same order as it is in the page. 
                The reason for this is that we want to keep the original structure of the page, and display it to the user 
                in the same way as it is in the page.
                Here is the page: """,
                _ai_prompt = self._source.html_root_element[:400000],
                _response_model = Answer,
                _asked_by = "system",
                _chat_type = "document",
                _event_name = EventName.SOURCE_TEXT.value
            )
            if source_text is not None:
                answer_data = json.loads(source_text.response)
                doc.source_text_in_html = answer_data.get("answer_for_chat", "")
        
                
        ## Save the document in the database
        app_logic.update_document(doc)
    
    def generate_initial_summary(self, bias_answer: str) -> Chat_Message:
        """
        Generate an initial summary of the document content
        
        Args:
            bias_answer: Information about the document's bias
            
        Returns:
            A Chat_Message object containing the summary
        """
        ai_prompt = f"""You are a helpful assistant that explains the content of a document to the user.
            I want you to take the following chat history and write a message to the user that explains the content.
            Your response should include a short explanation of the content, 
            that include what the content is about (max four sentences), and what is the bias / motivation of the author
            and key concepts or ideas in the content.
            
            The bias is: {bias_answer}
            """
        
        summary_message = self._process_chat_step(
            _user_prompt = "Explain the content of the document",
            _ai_prompt = ai_prompt,
            _response_model = Answer,
            _asked_by = "system",
            _chat_type = "document",
            _event_name = EventName.SUMMARY.value
        )
        
        return summary_message

    

    async def ask_question(self, question: str) -> Chat_Message:
        """
        Ask a question using the chat session manager
        
        Args:
            question: The question to ask
            
        Returns:
            A Chat_Message object containing the response
        """
        
        # Ask the question
        try:
            # Send the question to the chat client
            _prompt = f"{question}\n\nFormat the answer_for_chat in the response using HTML tags: <b> for bold, <br> for new line and <ul> and </ul> for the bullet points."
            response = self._client.send_message(prompt=_prompt, response_model=Answer)
            
            # Convert the response to JSON string if it's not already
            response_json = response.model_dump_json() if hasattr(response, "model_dump_json") else json.dumps(response)
            
            # Store the conversation in the database
            message = Chat_Message(
                chat_id=str(self._context_id),
                chat_type=self._context_type,
                user_id=self._user_id,
                user_prompt=question,
                ai_prompt=_prompt,
                asked_by="user",
                response=response_json,
                event_name=EventName.MANUAL_MESSAGE.value
            )
            message = insert_or_update_chat_history(message)
            
            return message
            
        except Exception as e:
            logger.error(f"Error in ask_question: {str(e)}")
            # Create an error message
            error_response = {
                "answer_for_chat": f"I'm sorry, I encountered an error: {str(e)}",
                "short_answer_for_computer": f"Error: {str(e)}",
                "citations": [],
                "status": "error"
            }
            
            message = Chat_Message(
                chat_id=str(self._context_id),
                chat_type=self._context_type,
                user_id=self._user_id,
                user_prompt=question,
                ai_prompt=_prompt,
                asked_by="user",
                response=json.dumps(error_response),
                event_name=EventName.ERROR.value
            )
            message = insert_or_update_chat_history(message)
            
            return message

    
    


    @classmethod    
    def chat_status(cls, document_id: str) -> bool:
        """
        Check if all required chat steps are completed for a document
        
        Args:
            document_id: The document ID to check
            
        Returns:
            True if all required steps are completed, False otherwise
        """
        event_names = [message.event_name for message in getters.get_chat_history(document_id)]

        if len(event_names) == 0:
            return False

        enum_values = [EventName.SUMMARY.value, EventName.SUGGESTED_QUESTIONS.value]

        for enum_value in enum_values:
            if enum_value not in event_names:
                return False

        return True
    
    @classmethod
    def get_initial_chat_history(cls, document_id: str) -> list[Chat_Message]:
        """
        Get the initial chat history for a document, including summary and user messages
        
        Args:
            document_id: The document ID
            
        Returns:
            A list of Chat_Message objects
        """
        chat = getters.get_chat_history(document_id)

        ## Filter out message with event_name = SUMMARY, 
        initial_chat_history = [message for message in chat if message.event_name in [EventName.SUMMARY.value]]
        user_messages = [message for message in chat if message.asked_by == "user"]

        ## Add the user messages to the chat history
        initial_chat_history.extend(user_messages)
        initial_chat_history.sort(key=lambda x: x.created_at)

        return initial_chat_history
    
    def get_document_from_chat_history(self) -> Dict:
        """
        Create a document dictionary from chat history
        
        This method extracts information from chat messages with different event types:
        - SUMMARY event type is used for document["is_about"]
        - ENTITIES event type is used for document["entities_and_concepts"]
        - CONTENT_TITLE event type is used for document["title"]
        - CONTENT_TYPE event type is used for document["source_type"]
        
        Returns:
            A dictionary with document data extracted from the chat history
        """
        try:
            # Get chat history for document
            chat_history = getters.get_chat_history(self._context_id)
            
            if not chat_history:
                logger.warning(f"No chat history found for document {self._context_id}")
                return None
            
            # Create an initial document dictionary
            document = {
                "id": str(self._context_id),
                "title": "Document from Chat",
                "status": "Done"
            }
            
            # Process chat messages to build document dictionary
            return  (chat_history, document)
            
        except Exception as e:
            logger.error(f"Error in get_document_from_chat_history: {str(e)}")
            return None

    def generate_suggested_chat_questions(self) -> List[str]:
        """
        Generate suggested questions for the user based on the document content and chat history.
        Uses the existing chat context and _process_chat_step to generate questions.
        
        Returns:
            List[str]: A list of suggested questions
        """
        try:
            user_prompt = "Generate interesting questions about this document"
            ai_prompt = """
            Based on the document content and our previous conversation, 
            generate 5 interesting questions that would help the user better understand the content. 
            Make sure the content have answer to the questions.
            Make sure the questions are not in the chat history.
            1. The main arguments or points
            2. The implications or impact
            3. The context or background
            4. Specific details that might be interesting
            5. Relationships to broader topics or themes
            
            Keep the questions short and concise, and not more than 15 words each.
            
            Return your response in this format:
            {
                "questions": ["Question 1?", "Question 2?", "Question 3?", "Question 4?", "Question 5?"],
                "status": "Success"
            }
            """
            
            # Use _process_chat_step to generate questions
            message = self._process_chat_step(
                _user_prompt=user_prompt,
                _ai_prompt=ai_prompt,
                _response_model=SuggestedQuestions,
                _asked_by="system",
                _chat_type="document",
                _event_name=EventName.SUGGESTED_QUESTIONS.value,
                _save_to_db=False
            )
            
            if not message:
                logger.error("Failed to generate questions")
                return []
            
            # Extract questions from the response
            try:
                # Parse the response JSON
                response_data = message.response
                if isinstance(response_data, str):
                    response_data = json.loads(response_data)
                
                # Get questions directly from the questions field
                questions = response_data.get('questions', [])
                
                # Ensure we have a list of strings
                if not isinstance(questions, list):
                    questions = []
                questions = [str(q) for q in questions if isinstance(q, (str, int, float))]
                
                return questions
                
            except json.JSONDecodeError:
                logger.error("Failed to parse questions response")
                return []
            
        except Exception as e:
            logger.error(f"Error generating suggested questions: {str(e)}")
            return []
            






