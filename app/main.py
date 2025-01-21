import asyncio
from enum import Enum
import time
from fastapi import (
    FastAPI,
    HTTPException,
    BackgroundTasks,
    status,
    Response,
    UploadFile,
    File,
    Form,
    WebSocket,
    WebSocketDisconnect,
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List, Annotated
from app.models import (
    User,
    Source,
    Document,
    PagePayload,
    DocumentPublic,
    HTTPError,
    RagAnswerPublic,
    QuestionPlayload,
    SearchPayload,
    SearchResults,
    Study_Collection_Document_Link,
    SubTopicDisplay,
    TreeNode,
    StudyCollectionPublic,
    StudyTaskPublic,
    CollectionDocumentlinkPayload,
)
import app.study_collection_handler as collection_handler
from app.source_doc_handler import SourceDocHandler
import app.question_answer_handler as question_answer_handler
import json, aiofiles
import app.app_logic as app_logic
import app.html_parser as html_parser
import app.getters as getter
import app.deleters as deleters
import app.entity_handler as entity_handler
import logging
from app.search_handler import SearchHandler
from app.prompt_models import RAGPrompt
from app.user_handler import UserHandler

search = SearchHandler()


class Groups(Enum):
    LIBRARY = "Library Search & Filter"
    BOOKMARK = "Bookmark / Source"
    DOCUMENT = "Document and Related Data (Entities, Questions...)"
    USER_DATA = "User Data (Documents, Entities, Topics)"
    ACTION = "Initiate Action"
    STUDY_COLLECTION = "Study Collection"
    ICONS = "Icons"
    FOR_TESTING = "For Testing"
    ASK_QUESTION = "Ask Question"


app = FastAPI()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s [%(filename)s:%(lineno)d]",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("icognition")


origins = [
    "chrome-extension://oeilkphkfimekfadiflbljknbhfmppej",
    "http://localhost:8080",
    "https://icognition.ai",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["icognitoin-answer-type"],
)


# websocket setup
active_connections: dict[str] = {}


class ConnectionManager:
    async def connect(self, websocket: WebSocket, session_id: str):

        await websocket.accept()
        active_connections[session_id] = websocket
        logger.info(f"Websocket connected for {session_id}")

    async def disconnect(self, session_id: str, message: str):
        try:
            websocket = active_connections[session_id]
            await websocket.close(code=1000, reason=message)
            del active_connections[session_id]
            logger.info(f"Websocket disconnected for {session_id}")
        except Exception as e:
            logger.error(
                f"Error in disconnecting websocket {session_id}. Error: {str(e)}"
            )
            logger.error(
                f"Error in disconnecting websocket {session_id}. Error: {str(e)}"
            )
            pass

    async def broadcast(self, message, user_id):

        ## Find session_id that include the string user_id
        session_ids = [key for key in active_connections.keys() if user_id in key]

        if len(session_ids) == 0:
            logger.info(f"Could not find websocket for {user_id} in broadcast")

        for session_id in session_ids:
            target_websocket = active_connections[session_id]
            await target_websocket.send_text(message)
            await target_websocket.send_text(message)


manager = ConnectionManager()


async def broadcastProgress(doc_id: str, user_id: str, increment: int):
    try:

        await manager.broadcast(
            json.dumps(
                {
                    "user_id": user_id,
                    "document_id": doc_id,
                    "type": "progress_percentage",
                    "data": increment,
                }
            ),
            user_id,
        )

    except Exception as e:
        logger.error(f"Error in broadcastProgress: {str(e)}")
        pass


@app.websocket("/ws/{user_id}/{source}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, source: str):
    session_id = f"{source}:{user_id}"
    await manager.connect(websocket, session_id)
    logger.info(f"Websocket endpoint message for {session_id}")
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Websocket received message {data}")
            await manager.broadcast(message=data, user_id=user_id)
    except WebSocketDisconnect as e:
        logger.error(f"Websocket Exception for {session_id}. Error: {str(e)}")
        await manager.disconnect(session_id, "Error in websocket connection")
        # await manager.broadcast("Client disconnected.", user_id)


@app.get("/")
async def root():
    return {"message": "Welcome to Icognition API"}


@app.get("/ping", status_code=200)
async def ping():

    db_status = False
    try:
        bm = app_logic.test_db_connection()
        if bm:
            db_status = True

    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail=f"Database connection failed. Error: {str(e)}"
        )

    return {"Message": f"Service is up and running. DB status: {db_status}"}


@app.get("/status", status_code=200)
async def ping():

    db_status = False
    db_docs_count = 0
    fuse_status = False

    sourceHandler = SourceDocHandler()
    try:
        bm = app_logic.test_db_connection()
        if bm:
            db_status = True

    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail=f"Database connection failed. Error: {str(e)}"
        )

    try:
        db_docs_count = getter.get_documents_count()
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail=f"Database connection failed. Error: {str(e)}"
        )

    try:
        file_content = "test"
        filename = "test.txt"
        sourceHandler.write_file(filename=filename, content=file_content)
        if file_content == sourceHandler.read_file(filename=filename):
            fuse_status = True

    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail=f"File system connection failed. Error: {str(e)}"
        )

    return {
        "Message": f"Service is up and running. DB status: {db_status}, DB docs count: {db_docs_count}, Fuse status: {fuse_status}"
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(request)
    logger.error(exc)
    return PlainTextResponse(str(request), status_code=400)


@app.post("/add_user", status_code=204, tags=[Groups.USER_DATA.value])
async def add_user(user: User):
    user_handler = UserHandler()

    try:
        user_handler.add_users_from_source()
        user_handler.add_user(user)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="User creation failed")


@app.get(
    "/populate_user_table",
    status_code=204,
    tags=[Groups.ACTION.value, Groups.FOR_TESTING.value],
)
async def add_user():
    user_handler = UserHandler()

    try:
        user_handler.add_users_from_source()
    except Exception as e:
        logger.error(e)
        raise HTTPException(
            status_code=500, detail="Failed to populate user table" + str(e)
        )


@app.post(
    "/bookmark",
    tags=[Groups.BOOKMARK.value],
    responses={
        400: {
            "model": HTTPError,
            "description": "Reporting back errors",
        },
        404: {"model": HTTPError, "description": "Page is not supported"},
        201: {"model": Source, "description": "Bookmark created successfully"},
        200: {"model": Source, "description": "Bookmark already exists"},
    },
)
async def create_bookmark(
    payload: PagePayload, background_tasks: BackgroundTasks, response: Response
):

    logger.info(f"Icognition bookmark endpoint called on {payload.url}")

    if payload.user_id == None:
        logger.warn(f"User ID not provided for {payload.url}")
        raise HTTPException(
            status_code=400,
            detail="User ID not provided for the bookmark",
        )

    # Check if payload.url is not the root URL of a website
    if html_parser.unsupported_page_url(payload.url):
        logger.warn(f"Invalid URL provided: {payload.url}")
        raise HTTPException(
            status_code=400,
            detail="I am sorry, I can't analyze home or search pages",
        )

    page = app_logic.create_page(payload)

    if page is None:
        logger.warn(f"Page object not created for {payload.url}")
        raise HTTPException(
            status_code=404,
            detail="Hmm, I wasn't able to find information on this page. I sent a message to our engineers",
        )

    ## Check in bookmark already exists
    try:
        _source = getter.get_source_by_url(payload.user_id, page.clean_url)
        if _source is not None:
            _doc = getter.get_document_by_source_id(_source.id)
            if _doc.status == "Done":
                logger.info(f"Bookmark already exists for {page.clean_url}")
                response.status_code = status.HTTP_200_OK

                ## Broadcast the document to the user
                doc = getter.get_document_public_by_id(_doc.id)
                message = {
                    "user_id": payload.user_id,
                    "document_id": doc.id,
                    "type": "document",
                    "data": doc.model_dump_json(),
                }
                await manager.broadcast(json.dumps(message), _source.user_id)

                return _source
            elif _doc.status == "Processing":
                logger.info(f"Document is still processing for {page.clean_url}")
                response.status_code = status.HTTP_206_PARTIAL_CONTENT

                message = {
                    "user_id": payload.user_id,
                    "document_id": _source.document_id,
                    "type": "document_in_progress",
                    "data": _source.model_dump_json(),
                }
                await manager.broadcast(json.dumps(message), payload.user_id)

                return _source
            elif _doc.status in ["Failure", "Pending"]:
                logger.info(
                    f"Document status is {_doc.status} attempting to regenerated document for {page.clean_url}"
                )

                background_tasks.add_task(
                    run_async_task_sync(generate_document_summary, _source)
                )
                background_tasks.add_task(
                    run_async_task_sync(generate_document_qanda, _source)
                )
                background_tasks.add_task(
                    run_async_task_sync(generate_document_entities, _source)
                )
                response.status_code = status.HTTP_201_CREATED
                return _source
        else:
            logger.info(f"Page object created for {page.clean_url}")
            _source = app_logic.create_source_bookmark(page, payload.user_id)
            logger.info(f"Source created for {_source.url}")

            background_tasks.add_task(
                run_async_task_sync(generate_document_summary, _source)
            )
            background_tasks.add_task(
                run_async_task_sync(generate_document_qanda, _source)
            )
            background_tasks.add_task(
                run_async_task_sync(generate_document_entities, _source)
            )

            response.status_code = status.HTTP_201_CREATED
            message = {
                "user_id": payload.user_id,
                "document_id": str(_source.document_id),
                "type": "document_in_progress",
                "data": None,
            }
            await manager.broadcast(json.dumps(message), payload.user_id)
            return _source
    except Exception as e:
        logger.error("Error in create_bookmark: ", e)
        raise HTTPException(status_code=500, detail="Bookmark creation failed")


@app.post(
    "/document/regenerate",
    tags=["Document"],
    response_model=Source,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_regenerate_document(
    old_doc: Document, background_tasks: BackgroundTasks
):
    """
    This method create document using a source id and a URL.
    Because create_source_bookmark also generate document, this method is use to re-generate
    the a document. Because it can take time to generate a document, this method
    kickoff the generate and return 202
    """
    logger.info(f"Regenrate Document ID {old_doc.id}")
    # Generate LLM content in a background process

    # Reason for returning bookmark is because the document will changed after the regeneration,
    # and the bookmark will be used to get the new document
    new_doc = app_logic.clone_document(old_doc)
    background_tasks.add_task(regenerate_document, new_doc)
    bookmark = app_logic.reassociate_bookmark_with_document(old_doc.id, new_doc.id)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")
        raise HTTPException(status_code=404, detail="Bookmark not found")
    return bookmark


@app.get("/regenerate/entities", tags=["Document"], status_code=200)
async def get_regenerate_entities(background_tasks: BackgroundTasks):
    background_tasks.add_task(regenerate_entities)
    return {"Message": "Regenerating entities"}


@app.get("/build_entity_vectors", tags=["Document"], status_code=200)
async def get_build_entity_vectors(background_tasks: BackgroundTasks):
    background_tasks.add_task(entity_handler.generate_entities_vectors)
    return {"Message": "Building entity vectors"}


@app.get("/boradcast/{user_id}", tags=["Document"], status_code=200)
async def broadcast_document_update(
    message: str, user_id: str, document_id: str = None
):

    if document_id is not None:
        doc = getter.get_document_public_by_id(document_id)
        message = {
            "user_id": user_id,
            "document_id": document_id,
            "type": "document",
            "data": doc.model_dump_json(),
        }
        await manager.broadcast(json.dumps(message), user_id)

    qas = question_answer_handler.get_question_answer_by_document_id(document_id)
    if len(qas) > 0:
        qas = [qa.to_public().model_dump_json() for qa in qas]
        message = {
            "user_id": user_id,
            "document_id": document_id,
            "type": "doc_qanda",
            "data": qas,
        }
        await manager.broadcast(json.dumps(message), user_id)


## Background task to generate summaries from LLM
async def generate_document_summary(source: Source):
    document = getter.get_document_by_id(source.document_id)
    doc_id = str(document.id)

    try:
        if document.status in ["Pending", "Done", "Failure"]:
            logger.info(f"Background task for document ID: {source.document_id}")

            await broadcastProgress(doc_id, source.user_id, 15)
            document = await app_logic.generate_summary(doc=document)
            await broadcastProgress(doc_id, source.user_id, 30)

            ## Broadcast the document to the user
            doc = getter.get_document_public_by_id(document.id)
            message = {
                "user_id": source.user_id,
                "document_id": doc.id,
                "type": "document",
                "data": doc.model_dump_json(),
            }
            await manager.broadcast(json.dumps(message), source.user_id)
            await broadcastProgress(doc_id, source.user_id, 10)

            await app_logic.generate_embeddings_for_docs(
                documents=[document], user_id=source.user_id
            )
            logger.info(
                f"Background task for document ID: {source.document_id} completed"
            )
    except Exception as e:
        logger.error("generate_document summary", e)


def run_async_task_sync(func, *args, **kwargs):

    logger.info(
        f"Running async task for {func.__name__} with args: {args} and kwargs: {kwargs}"
    )
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.create_task(func(*args, **kwargs))
    except Exception as e:
        logger.error(f"Error running async task {func.__name__}: {str(e)}")


async def generate_document_entities(source: Source):
    document = getter.get_document_by_id(source.document_id)

    try:
        if len(getter.get_entities_ids_by_document_id(document.id)) == 0:
            ent_success = await app_logic.generate_entities(
                user_id=source.user_id, doc=document
            )
            topic_success = await app_logic.generate_topics(
                user_id=source.user_id, doc=document
            )
            logger.info(
                f"Background task for generating entities and topics for: {document.id} completed. Result, number of entities: {len(ent_success)} number of topics: {len(topic_success)}"
            )
            await app_logic.generate_embeddings_for_entities(
                entities=ent_success, user_id=source.user_id
            )
            await app_logic.generate_embeddings_for_entities(
                entities=topic_success, user_id=source.user_id
            )
    except Exception as e:
        logger.error("Generate document entities ", e)


async def generate_document_qanda(source: Source):
    document = getter.get_document_by_id(source.document_id)
    doc_id = str(document.id)
    try:
        if (
            len(question_answer_handler.get_question_answer_by_document_id(document.id))
            == 0
        ):
            await broadcastProgress(doc_id, source.user_id, 5)

            await question_answer_handler.generate_doc_quesions_answers(
                user_id=source.user_id, doc=document
            )
            qas = question_answer_handler.get_question_answer_public_by_document_id(
                document.id
            )
            qas = [qa.model_dump() for qa in qas]
            await broadcastProgress(doc_id, source.user_id, 20)

            logger.info(
                f"Background task for generating questions and answers for: {document.id} completed. Number of questions and answers, {len(qas)}"
            )
            message = {
                "user_id": source.user_id,
                "document_id": str(document.id),
                "data": json.dumps(qas),
                "type": "doc_qanda",
            }
            await manager.broadcast(json.dumps(message), source.user_id)
            await broadcastProgress(doc_id, source.user_id, 20)

            ## For now, we are not generating embeddings for questions and answers
    except Exception as e:
        logger.error("Generate document question and answers ", e)


def generate_document_qanda_sync(source: Source):
    asyncio.run(generate_document_qanda(source))


## Background task to regenerate summaries from LLM if not already exists
async def regenerate_document(document: Document):

    if document.status in ["Pending", "Done", "Failure"]:
        logger.info(
            f"Background task for deleting document ID: {document.id} and associated records"
        )
        deleters.delete_document_associate_records(document_id=document.id)

    source = getter.get_source_by_document_id(document.id)
    try:
        if document.status in ["Pending", "Done", "Failure"]:
            logger.info(f"Background task for document ID: {document.id}")
            document = await app_logic.generate_summary(doc=document)
            await app_logic.generate_embeddings_for_docs(
                documents=[document], user_id=source.user_id
            )
            logger.info(
                f"Background task for document ID: {source.document_id} completed"
            )
    except Exception as e:
        logger.error(e)

    try:
        if len(getter.get_entities_ids_by_document_id(document.id)) == 0:
            ent_success = await app_logic.generate_entities(
                user_id=source.user_id, doc=document
            )
            topic_success = await app_logic.generate_topics(
                user_id=source.user_id, doc=document
            )
            logger.info(
                f"Background task for generating entities and topics for: {document.id} completed. Result, number of entities: {len(ent_success)} number of topics: {len(topic_success)}"
            )
            await app_logic.generate_embeddings_for_entities(
                entities=ent_success, user_id=source.user_id
            )
            await app_logic.generate_embeddings_for_entities(
                entities=topic_success, user_id=source.user_id
            )
    except Exception as e:
        logger.error(e)

    try:
        if (
            len(question_answer_handler.get_question_answer_by_document_id(document.id))
            == 0
        ):
            success = await question_answer_handler.generate_doc_quesions_answers(
                user_id=source.user_id, doc=document
            )
            logger.info(
                f"Background task for generating questions and answers for: {document.id} completed. Result, {success}"
            )
            ## For now, we are not generating embeddings for questions and answers
    except Exception as e:
        logger.error(e)


async def regenerate_entities():

    ## Get all documents
    documents = getter.get_all_documents()

    for doc in documents:
        try:
            deleters.delete_entities_associated_with_document(doc.id)
            deleters.delete_orphaned_entities()
        except Exception as e:
            logger.error(
                f"Error deleting entities for document {doc.id}. Error {str(e)}"
            )
            raise Exception(
                f"Error deleting entities for document {doc.id}. Error {str(e)}"
            )

    for document in documents:
        try:
            user_id = getter.get_source_by_document_id(doc.id).user_id
            ent_success = await app_logic.generate_entities(
                user_id=user_id, doc=document
            )
            topic_success = await app_logic.generate_topics(
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
            logger.error(
                f"Error generating entities for document {doc.id}. Error {str(e)}"
            )


@app.get(
    "/bookmarks/user/{user_id}",
    tags=["Bookmark"],
    response_model=List[Source],
    status_code=200,
)
async def get_bookmarks_by_user_id(user_id: str):
    bookmarks = getter.get_sources_by_user_id(user_id)

    if bookmarks is None:
        raise HTTPException(status_code=404, detail="Bookmarks not found")

    logger.info(f"Icognition return {len(bookmarks)} bookmarks")
    return bookmarks


@app.post("/bookmark/user", tags=["Bookmark"], response_model=Source, status_code=200)
async def get_bookmarks_by_user_id(payload: PagePayload):
    bookmark = getter.get_source_by_url(payload.user_id, payload.url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


@app.get(
    "/documents_plus/user/{user_id}",
    tags=["Document"],
    response_model=List[DocumentPublic],
    status_code=200,
)
async def get_documents_plus_by_user_id(user_id: str):

    documents = getter.get_documents_public_by_user_id(user_id)

    if documents is None:
        raise HTTPException(status_code=404, detail="Documents not found")

    logger.info(f"Icognition return {len(documents)} documents_plus")
    return documents


@app.get("/document/{id}/html_elements", tags=["Document"], status_code=200)
async def get_document_html_elements(id: str):
    try:
        doc = getter.get_document_public_by_id(id)
        return json.loads(doc.html_elements)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Document not found")


@app.get("/bookmark", tags=["Bookmark"], response_model=Source, status_code=200)
async def get_bookmark_by_url(url: str):
    bookmark = getter.get_source_by_url(url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    logger.info(f"Icognition return bookmark {bookmark.id}")
    return bookmark


@app.get("/bookmark/{id}/document", tags=["Bookmark"])
async def get_bookmark_document(id: str, response: Response):
    logger.info(f"Icognition bookmark document endpoint called on {id}")
    document = getter.get_document_by_source_id(id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status == "Processing":
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        return document
    else:
        response.status_code = status.HTTP_200_OK
        return document


@app.get(
    "/document_plus/{source_id}",
    tags=["Bookmark"],
    responses={
        404: {
            "model": HTTPError,
            "description": "Returning document error",
        },
        206: {"model": None, "description": "Document is being processed"},
        200: {"model": DocumentPublic, "description": "Document is ready"},
    },
)
async def get_document_plus(
    source_id: str, response: Response, background_tasks: BackgroundTasks
):
    """get document with entities and concepts"""

    logger.info(f"Document plus -> endpoint called on bookmark {source_id}")
    source = getter.get_source_by_id(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    document = getter.get_document_by_source_id(source_id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status in ["Processing", "Pending"]:
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        logger.info(
            f"Document plus -> endpoint called on document status {document.status}"
        )
        return None
    elif document.status == "Done":

        response.status_code = status.HTTP_200_OK
        logger.info(
            f"Document plus -> endpoint called on document status {document.status}"
        )

        return document.to_public()
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return document.to_public()


@app.get("/document/{id}", tags=["Document"])
async def get_document(id: str, response: Response):
    logger.info(f"Icognition document endpoint called on {id}")
    document = getter.get_document_public_by_id(id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status == "Processing":
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        return document
    else:
        response.status_code = status.HTTP_200_OK
        return document


@app.get("/document/{id}/xray", tags=["Document"])
async def get_document_summary(id: str, response: Response, force: str | None = None):

    try:
        res = getter.get_document_public_by_id(id)
        response.status_code = status.HTTP_200_OK
        return res

    except ValueError as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail=e)


@app.get("/document/{id}/questions_answers", tags=["Document"])
async def get_document_questions_answers(id: str, response: Response):

    try:
        qas = question_answer_handler.get_question_answer_public_by_document_id(id)
        response.status_code = status.HTTP_200_OK
        return qas

    except ValueError as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail=e)


@app.get("/bookmark/{id}/keysentences", tags=["Bookmark"])
async def get_bookmark_keysentences(id: int, response: Response):

    try:
        sentences = app_logic.document_key_sentences(id)
        response.status_code = status.HTTP_200_OK
        return sentences

    except ValueError as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail=e)


@app.delete("/bookmark/{id}", tags=["Bookmark"], status_code=204)
async def delete_bookmark(id: str) -> None:
    logger.info(f"Delete bookmark and associated records for id: {id}")
    deleters.delete_source_and_associate_records(id)


@app.delete("/document/{id}", tags=["Document"], status_code=204)
async def delete_document(id: str) -> None:
    logger.info(f"Delete document and associated records for id: {id}")

    deleters.delete_document_and_associate_records(id)


@app.get(
    "/subtopics/{user_id}",
    tags=["Subtopics"],
    response_model=List[SubTopicDisplay],
    status_code=200,
)
async def get_user_subtopics(user_id: str):
    try:
        subtopics = getter.get_subtopics_display(user_id=user_id)
        return subtopics
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Subtopics not found")


@app.get(
    "/subtopics_node/{user_id}",
    tags=["Subtopics"],
    response_model=List[TreeNode],
    status_code=200,
)
async def get_user_subtopics_node(user_id: str):
    try:
        subtopics_nodes = getter.get_subtopics_nodes_by_user(user_id)
        return subtopics_nodes
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Subtopics not found")


@app.get(
    "/filter_nodes/{user_id}",
    tags=["Library Search"],
    response_model=List[TreeNode],
    status_code=200,
)
async def get_user_filter_nodes(user_id: str):
    try:
        start_time = time.time()
        nodes = getter.get_filter_nodes_by_user_id(user_id)
        logger.info(f"Time to get filter nodes: {(time.time() - start_time):.2f}")
        return nodes
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Error getting filter nodes")


@app.post(
    "/search", tags=["Library Search"], status_code=200, response_model=SearchResults
)
async def search_documents(search_payload: SearchPayload, response: Response):
    logger.info(f"Search documents with query: {search_payload.query}")

    try:
        results = await search(search_payload.user_id, search_payload.query)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Search failed")

    if results.failure:
        return results

    if results.rag_answer:
        response.headers["icognitoin-answer-type"] = "RAGAnswer"
        return results
    else:
        if len(results.documents_display) == 0:
            raise HTTPException(status_code=404, detail="No results found")

        response.headers["icognitoin-answer-type"] = "DocumentDisplay"
        return results


@app.get(
    "/generate_embedding/{user_id}",
    tags=["User Data (Entities, Document)"],
    status_code=200,
)
async def generate_embedding(user_id: str):
    try:
        await app_logic.generate_embeddings(user_id=user_id)
        return {"Message": "Embedding generation completed"}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Embedding generation failed")


@app.get(
    "/entities_names/{user_id}",
    tags=["User Data (Entities, Document)"],
    status_code=200,
)
async def get_user_entities_names(user_id: str):
    try:
        start_time = time.time()
        names = getter.get_entities_names_by_user_id(user_id)
        logger.info(f"Time to get entities names: {(time.time() - start_time):.2f}")
        return names
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Entities not found")


@app.get(
    "/placeholder_image",
    tags=["Icons"],
    responses={200: {"content": {"image/png": {}}}},
    response_class=FileResponse,
)
async def get_placeholder_image():
    return FileResponse("./app/assets/images/library_placeholder.jpg")


@app.get(
    "/icon/{icon_name}",
    tags=["Icons"],
    responses={200: {"content": {"image/png": {}}}},
    response_class=FileResponse,
)
async def get_icon(icon_name: str):
    return FileResponse(f"./app/assets/images/{icon_name}.png")


## Study collection endpoints
@app.get(
    "/study_collections/{user_id}",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[StudyCollectionPublic],
    status_code=200,
)
async def get_study_collections(user_id: str):
    try:
        collections = collection_handler.get_study_collections_public(user_id)
        return collections
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Study collections not found")


@app.get(
    "/user_study_collections/{user_id}",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[StudyCollectionPublic],
    status_code=200,
)
async def get_user_study_collections(user_id: str):
    try:
        collections = collection_handler.get_study_collections_public(user_id)
        return collections
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Study collections not found")


@app.post(
    "/study_collection",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyCollectionPublic,
    status_code=200,
)
async def create_study_collection(
    collection: StudyCollectionPublic, background_tasks: BackgroundTasks
):
    try:
        collection = await collection_handler.create_study_collection(
            name=collection.name,
            objective=collection.description,
            user_id=collection.user_id,
            documents_ids=collection.documents_ids,
            tasks=collection.tasks,
        )

        background_tasks.add_task(
            collection_handler.generate_collection_response,
            collection_id=collection.id,
            listener=event_listener,
        )
        return collection
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection creation failed")


@app.put(
    "/study_collection",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyCollectionPublic,
    status_code=200,
)
async def update_study_collection(collection: StudyCollectionPublic):
    try:
        collection = await collection_handler.update_study_collection(collection)
        return collection
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection update failed")


@app.put(
    "/study_collection/{collection_id}/documents",
    tags=[Groups.STUDY_COLLECTION],
    status_code=200,
)
async def update_study_collection_documents(
    collection_id: str, document_ids: List[str]
):
    try:
        collection = collection_handler.get_study_collection_by_id(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Study collection not found")

        for document_id in document_ids:
            document = getter.get_document_by_id(document_id)
            if document is None:
                raise HTTPException(
                    status_code=404, detail=f"Document with id {document_id} not found"
                )
            collection_handler.link_collection_document(collection_id, document_id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection update failed")


@app.delete(
    "/study_collection/{id}/documents",
    tags=[Groups.STUDY_COLLECTION],
    status_code=204,
)
async def delete_study_collection_document(
    collection_id: str, documents_ids: List[str]
):
    try:
        collection = collection_handler.get_study_collection_by_id(collection_id)
        document = getter.get_document_by_id(document_id)
        if collection is None:
            raise HTTPException(status_code=404, detail="Study collection not found")

        for document_id in documents_ids:
            document = getter.get_document_by_id(document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            collection_handler.unlink_collection_document(collection_id, document_id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection update failed")


@app.get(
    "/generate_study_collection/{collection_id}",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyCollectionPublic,
    status_code=200,
)
async def generate_study_collection(
    collection_id: str, background_tasks: BackgroundTasks
):
    try:
        collection = collection_handler.get_study_collection_by_id(collection_id)

        if collection is None:
            raise HTTPException(status_code=404, detail="Study collection not found")

        background_tasks.add_task(
            collection_handler.generate_collection_response,
            collection_id=collection.id,
            listener=event_listener,
        )
        return collection
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection creation failed")


def event_listener(event):
    logger.info(f"Event listner called with event: {event}")


@app.get(
    "/study_collection/{id}/related_documents",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[DocumentPublic],
    status_code=200,
)
async def get_collection_related_documents(id: str):
    try:
        documents = collection_handler.find_related_docs_public(id)
        return documents
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Documents not found")


@app.get(
    "/study_collection/{id}",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyCollectionPublic,
    status_code=200,
)
async def get_study_collection(id: str):
    try:
        collection = collection_handler.get_study_collection_by_id(id)
        return collection
    except Exception as e:
        logging.error(e)
        raise HTTPException(
            status_code=404, detail=f"Study collection not found. Error {str(e)}"
        )


@app.get(
    "/study_collection/{id}/candidate_documents",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[DocumentPublic],
    status_code=200,
)
async def get_collection_candidate_documents(id: str):
    try:
        documents = collection_handler.get_list_of_candidates_docs(id)
        return documents
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Documents not found")


@app.delete("/study_collection/{id}", tags=[Groups.STUDY_COLLECTION], status_code=204)
async def delete_study_collection(id: str):
    try:
        collection_handler.delete_study_collection(id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study collection deletion failed")


@app.post(
    "/study_task",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyTaskPublic,
    status_code=200,
)
async def create_study_task(task: StudyTaskPublic):
    try:
        task = collection_handler.create_study_task(
            collection_id=task.collection_id, description=task.description
        )
        task = collection_handler.create_study_task(
            collection_id=task.collection_id, description=task.description
        )
        return task
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Study task creation failed")


@app.put(
    "/study_task",
    tags=[Groups.STUDY_COLLECTION],
    response_model=StudyTaskPublic,
    status_code=200,
)
async def update_study_task(task: StudyTaskPublic):
    try:
        task = await collection_handler.update_study_task(task)

        if task is None:
            raise HTTPException(status_code=404, detail="Error updating study task")
        else:
            return task
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Study task update failed")


@app.post(
    "/study_tasks",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[StudyTaskPublic],
    status_code=200,
)
async def create_study_tasks(tasks: List[StudyTaskPublic]):
    try:
        created_tasks = []
        for task in tasks:
            created_tasks.append(
                collection_handler.create_study_task(
                    collection_id=task.collection_id, description=task.description
                )
            )
            created_tasks.append(
                collection_handler.create_study_task(
                    collection_id=task.collection_id, description=task.description
                )
            )
        return created_tasks
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Study task creation failed")


@app.get(
    "/study_collection_tasks/{collection_id}",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[StudyTaskPublic],
    status_code=200,
)
async def get_study_tasks(collection_id: str):
    try:
        tasks = collection_handler.get_study_tasks(collection_id)
        return tasks
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Study tasks not found")


@app.get(
    "/study_collection/{collection_id}/related_entities",
    tags=[Groups.STUDY_COLLECTION],
    response_model=List[TreeNode],
    status_code=200,
)
async def get_collection_entities(collection_id: str):
    try:
        entities = collection_handler.get_collection_entities(collection_id)
        return entities
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=404, detail="Entities not found")


@app.post(
    "/collection_document_link",
    tags=[Groups.STUDY_COLLECTION],
    status_code=200,
    response_model=Study_Collection_Document_Link,
)
async def link_collection_document(payload: CollectionDocumentlinkPayload):
    try:
        return collection_handler.link_collection_document(
            collection_id=payload.collection_id, document_id=payload.document_id
        )

    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Collection document link failed")


@app.post(
    "/collection_document_unlink", tags=[Groups.STUDY_COLLECTION], status_code=200
)
async def unlink_collection_document(payload: CollectionDocumentlinkPayload):
    try:
        return collection_handler.unlink_collection_document(
            collection_id=payload.collection_id, document_id=payload.document_id
        )

    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Collection document unlink failed")


async def listen_doc_generation(event: dict):
    logger.info(f"Event listener called with event: {event['message']}")

    source = event["source"]
    if source.document_id is None:
        logger.warn(f"Document was not created for source {source.id}")
        return False
    else:
        await generate_document_summary(source)
        return True


@app.post("/create_source_upload_file/", tags=["Bookmark / Source"])
async def create_source_upload_file(
    file: Annotated[UploadFile, File()],
    user_id: Annotated[str, Form()],
    background_tasks: BackgroundTasks,
):

    user_handler = UserHandler()
    source_handler = SourceDocHandler()

    if user_handler.user_exits(user_id) != True:
        raise HTTPException(status_code=404, detail="User not found")

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    logger.info(
        f"File {file.filename} with contect type of {file.content_type} uploaded for user {user_id}"
    )

    try:
        source = source_handler.create_source(user_id=user_id, filename=file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    async with aiofiles.open(source.filepath, "wb") as out_file:
        content = await file.read()  # async read
        await out_file.write(content)  # async write
        await file.close()

    background_tasks.add_task(
        source_handler.generate_doc_from_pdf, source, listen_doc_generation
    )

    return {"filename": file.filename}


@app.post(
    "/ask_question",
    tags=[Groups.ASK_QUESTION],
    response_model=RagAnswerPublic,
    status_code=200,
)
async def ask_question(payload: QuestionPlayload):
    try:
        if payload.collection_id is None and payload.document_id is None:
            raise HTTPException(
                status_code=400, detail="Collection ID or Document ID are required"
            )
            raise HTTPException(
                status_code=400, detail="Collection ID or Document ID are required"
            )
        if payload.question is None:
            raise HTTPException(status_code=400, detail="Question is required")

        if payload.document_id is not None:
            answer = await question_answer_handler.custom_question(
                question=payload.question, document_id=payload.document_id, save=True
            )
            answer = await question_answer_handler.custom_question(
                question=payload.question, document_id=payload.document_id, save=True
            )
            return answer
        elif payload.collection_id is not None:
            answer = await collection_handler.ask_question(
                collection_id=payload.collection_id, question=payload.question
            )
            answer = await collection_handler.ask_question(
                collection_id=payload.collection_id, question=payload.question
            )
            return answer

    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Question answering failed")


@app.delete("/question_answer/{id}", tags=[Groups.ASK_QUESTION], status_code=204)
async def delete_question_answer(id: str):
    try:
        await question_answer_handler.delete_question_answer(id)
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Question answer deletion failed")


@app.post(
    "/document/question",
    tags=[Groups.DOCUMENT.value],
    response_model=RagAnswerPublic,
    status_code=200,
)
async def post_document_question(payload: QuestionPlayload):
    try:
        logger.info(
            f"Question endpoint called on {payload.document_id} with question {payload.question}"
        )
        answer = await question_answer_handler.custom_question(
            question=payload.question, document_id=payload.document_id
        )
        logger.info(
            f"Question endpoint called on {payload.document_id} with answer {answer.answer}"
        )
        return answer
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Answer generation failed")


@app.get("/reformat_citiation", tags=[Groups.FOR_TESTING.value], status_code=200)
async def reformat_citiation():
    try:
        await app_logic.update_question_answer_citation_format()
        return {"Message": "Citation reformatted"}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Citation reformatting failed")


@app.get(
    "/broadcast/{user_id}/{document_id}", tags=[Groups.ACTION.value], status_code=200
)
async def broadcast_document_update(user_id: str, document_id: str):
    doc = getter.get_document_public_by_id(document_id)
    message = {
        "user_id": user_id,
        "document_id": document_id,
        "type": "document",
        "data": doc.model_dump_json(),
    }
    await manager.broadcast(json.dumps(message), user_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")


@app.get(
    "/search_wikidata_for_entities", tags=[Groups.FOR_TESTING.value], status_code=200
)
async def search_wikidata_for_entities():
    try:
        await entity_handler.find_entities_without_wikidata_id()
        return {"Message": "Wikidata search completed"}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail="Wikidata search failed")
