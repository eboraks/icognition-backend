from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
from app.models import (
    Bookmark,
    Document,
    PagePayload,
    DocumentDisplay,
    HTTPError,
    SearchPayload,
    SearchResults,
    SubTopicDisplay,
    TreeNode,
)
import logging
import sys
import app.app_logic as app_logic
import app.subtopics_util as subtopics_util
import app.html_parser as html_parser
import app.getters as getter
from app.search_handler import SearchHandler
from app.prompt_models import RAGPrompt

search = SearchHandler()


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(funcName)s:%(lineno)d - %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI()
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


@app.get("/")
async def root():
    return {"message": "Welcome to Icognition API"}


@app.get("/ping", status_code=200)
async def ping():
    try:
        bm = app_logic.test_db_connection()
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Database connection failed")

    return {"Message": "Service is up and running"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(request)
    logging.error(exc)
    return PlainTextResponse(str(request), status_code=400)


@app.post(
    "/bookmark",
    responses={
        400: {
            "model": HTTPError,
            "description": "Reporting back errors",
        },
        404: {"model": HTTPError, "description": "Page is not supported"},
        201: {"model": Bookmark, "description": "Bookmark created successfully"},
    },
)
async def create_bookmark(
    payload: PagePayload, background_tasks: BackgroundTasks, response: Response
):

    logging.info(f"Icognition bookmark endpoint called on {payload.url}")

    if payload.user_id == None:
        logging.warn(f"User ID not provided for {payload.url}")
        raise HTTPException(
            status_code=400,
            detail="User ID not provided for the bookmark",
        )

    # Check if payload.url is not the root URL of a website
    if html_parser.unsupported_page_url(payload.url):
        logging.warn(f"Invalid URL provided: {payload.url}")
        raise HTTPException(
            status_code=400,
            detail="I am sorry, I can't analyze home or search pages",
        )

    page = app_logic.create_page(payload)

    if page is None:
        logging.warn(f"Page object not created for {payload.url}")
        raise HTTPException(
            status_code=404,
            detail="Hmm, I wasn't able to find information on this page. I sent a message to our engineers",
        )

    ## Check in bookmark already exists
    _bookmark = getter.get_bookmark_by_url(payload.user_id, page.clean_url)
    if _bookmark is not None:
        _doc = getter.get_document_by_bookmark_id(_bookmark.id)
        
        if _doc.status == "Done":
            logging.info(f"Bookmark already exists for {page.clean_url}")
            response.status_code = status.HTTP_201_CREATED
            return _bookmark
        elif _doc.status == "Processing":
            logging.info(f"Document is still processing for {page.clean_url}")
            response.status_code = status.HTTP_206_PARTIAL_CONTENT
            return _bookmark
        elif _doc.status in ["Failure", "Pending"]:
            logging.info(f"Document status is {_doc.status} attempting to regenerated document for {page.clean_url}")
            background_tasks.add_task(generate_document, bookmark = _bookmark)
            response.status_code = status.HTTP_201_CREATED
            return _bookmark
    else:
        logging.info(f"Page object created for {page.clean_url}")
        _bookmark = app_logic.create_bookmark(page, payload.user_id)
        logging.info(f"Bookmark created for {_bookmark.url}")
        background_tasks.add_task(generate_document, bookmark = _bookmark)
        response.status_code = status.HTTP_201_CREATED
        return _bookmark


@app.post(
    "/document/regenerate",
    response_model=Bookmark,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_regenerate_document(
    old_doc: Document, background_tasks: BackgroundTasks
):
    """
    This method create document using a bookmark id and a URL.
    Because create_bookmark also generate document, this method is use to re-generate
    the a document. Because it can take time to generate a document, this method
    kickoff the generate and return 202
    """
    logging.info(f"Regenrate Document ID {old_doc.id}")
    # Generate LLM content in a background process

    # Reason for returning bookmark is because the document will changed after the regeneration,
    # and the bookmark will be used to get the new document
    new_doc = app_logic.clone_document(old_doc)
    background_tasks.add_task(regenerate_document, new_doc)
    bookmark = app_logic.reassociate_bookmark_with_document(old_doc.id, new_doc.id)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


## Background task to generate summaries from LLM
async def generate_document(bookmark: Bookmark):
    document = getter.get_document_by_id(bookmark.document_id)

    if document.status in ["Pending", "Done", "Failure"]:
        logging.info(f"Background task for document ID: {bookmark.document_id}")
        await app_logic.extract_info_from_doc(document)
        await app_logic.generate_embeddings(bookmark.user_id)
        ## aawait subtopics_util.subtopics_factory(_user_id = bookmark.user_id)
        logging.info(f"Background task for document ID: {bookmark.document_id} completed")


## Background task to regenerate summaries from LLM if not already exists
async def regenerate_document(doc: Document):

    if doc.status in ["Pending", "Done", "Failure"]:

        new_doc = await app_logic.extract_info_from_doc(doc)
        if new_doc:
            logging.info(f"Background task for document ID: {new_doc.id} completed")
        else:
            logging.error(
                f"Background document regenaring for document ID: {doc.id} failed"
            )


@app.get("/bookmarks/user/{user_id}", response_model=List[Bookmark], status_code=200)
async def get_bookmarks_by_user_id(user_id: str):
    bookmarks = getter.get_bookmarks_by_user_id(user_id)

    if bookmarks is None:
        raise HTTPException(status_code=404, detail="Bookmarks not found")

    logging.info(f"Icognition return {len(bookmarks)} bookmarks")
    return bookmarks

@app.post("/bookmark/user", response_model=Bookmark, status_code=200)
async def get_bookmarks_by_user_id(payload: PagePayload):
    bookmark = getter.get_bookmark_by_url(payload.user_id, payload.url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


@app.get(
    "/documents_plus/user/{user_id}",
    response_model=List[DocumentDisplay],
    status_code=200,
)
async def get_documents_plus_by_user_id(user_id: str):
    
    documents = getter.get_documents_display_by_user_id(user_id)
    
    if documents is None:
        raise HTTPException(status_code=404, detail="Documents not found")

    logging.info(f"Icognition return {len(documents)} documents_plus")
    return documents


@app.get("/bookmark", response_model=Bookmark, status_code=200)
async def get_bookmark_by_url(url: str):
    bookmark = getter.get_bookmark_by_url(url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    logging.info(f"Icognition return bookmark {bookmark.id}")
    return bookmark


@app.get("/bookmark/{id}/document")
async def get_bookmark_document(id: int, response: Response):
    logging.info(f"Icognition bookmark document endpoint called on {id}")
    document = getter.get_document_by_bookmark_id(id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status == "Processing":
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        return document
    else:
        response.status_code = status.HTTP_200_OK
        return document


@app.get("/document_plus/{bookmark_id}", responses={
        404: {
            "model": HTTPError,
            "description": "Returning document error",
        },
        206: {"model": None, "description": "Document is being processed"},
        200: {"model": DocumentDisplay, "description": "Document is ready"},
    })
async def get_document_plus(bookmark_id: int, response: Response, background_tasks: BackgroundTasks):
    """get document with entities and concepts"""

    logging.info(f"Document plus -> endpoint called on bookmark {bookmark_id}")
    document = getter.get_document_by_bookmark_id(bookmark_id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status in ["Processing", "Pending"]:
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        logging.info(
            f"Document plus -> endpoint called on document status {document.status}"
        )
        return None
    elif document.status == "Done":
        
        response.status_code = status.HTTP_200_OK
        logging.info(
            f"Document plus -> endpoint called on document status {document.status}"
        )

        return document.to_display()
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return document.to_display()


@app.get("/document/{id}")
async def get_document(id: int, response: Response):
    logging.info(f"Icognition document endpoint called on {id}")
    document = getter.get_document_by_id(id)

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # If document is still in processing, let the client know
    if document.status == "Processing":
        response.status_code = status.HTTP_206_PARTIAL_CONTENT
        return document
    else:
        response.status_code = status.HTTP_200_OK
        return document
    
@app.get("/bookmark/{id}/keysentences")
async def get_bookmark_keysentences(id: int, response: Response):

    try:
        sentences = app_logic.document_key_sentences(id)
        response.status_code = status.HTTP_200_OK
        return sentences

    except ValueError as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail=e)



@app.delete("/bookmark/{id}", status_code=204)
async def delete_bookmark(id: int) -> None:
    logging.info(f"Delete bookmark and associated records for id: {id}")
    app_logic.delete_bookmark_and_associate_records(id)


@app.delete("/document/{id}", status_code=204)
async def delete_document(id: int) -> None:
    logging.info(f"Delete document and associated records for id: {id}")
    app_logic.delete_document_and_associate_records(id)


@app.get("/subtopics/{user_id}", response_model=List[SubTopicDisplay], status_code=200)
async def get_user_subtopics(user_id: str):
    try:
        subtopics = getter.get_subtopics_display(user_id = user_id)
        return subtopics
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Subtopics not found")


@app.get("/subtopics_node/{user_id}", response_model=List[TreeNode], status_code=200)
async def get_user_subtopics_node(user_id: str):
    try:
        subtopics_nodes = getter.get_subtopics_nodes_by_user(user_id)
        return subtopics_nodes
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Subtopics not found")
    
@app.get("/filter_nodes/{user_id}", response_model=List[TreeNode], status_code=200)
async def get_user_filter_nodes(user_id: str):
    try:
        return getter.get_filter_nodes_by_user_id(user_id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Error getting filter nodes")

@app.get("/subtopics_name_regenerate/{user_id}", status_code=200)
async def regenerate_user_subtopics(user_id: str, background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(subtopics_util.rename_subtopics, user_id)
        return {"Message": "Subtopics regeneration submitted"}
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Subtopics regeneration failed")


@app.post("/search", status_code=200, response_model=SearchResults)
async def search_documents(search_payload: SearchPayload, response: Response):
    logging.info(f"Search documents")
    
    try:
        results = await search(search_payload.user_id, search_payload.query)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Search failed")
    
    if results.failure:
        return results

    if len(results.documents_display) == 0:
        raise HTTPException(status_code=404, detail="No results found")

    if results.rag_answer:
        response.headers["icognitoin-answer-type"] = "RAGAnswer"
        return results
    else:
        response.headers["icognitoin-answer-type"] = "DocumentDisplay"
        return results
        



@app.get("/generate_embedding", status_code=200)
async def generate_embedding():
    try:
        await app_logic.generate_documents_embeddings()
        return {"Message": "Embedding generation completed"}
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Embedding generation failed")

@app.delete("/subtopics/{user_id}", status_code=204)
def delete_user_id_subtopics(user_id: str):
    logging.info(f"Delete subtopics for user_id: {user_id}")
    subtopics_util.delete_user_id_subtopics(user_id) 

@app.get("/regenerate/subtopics/{user_id}", status_code=200)
async def regenerate_subtopics(user_id: str, background_tasks: BackgroundTasks):
    try:
        subtopics_util.delete_user_id_subtopics(user_id)
        background_tasks.add_task(subtopics_util.subtopics_factory, _user_id = user_id, _force_run = True)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Subtopics generation failed")
    
@app.get("/generate/subtopics/{user_id}", status_code=200)
async def generate_subtopics(user_id: str, background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(subtopics_util.subtopics_factory, 
                                  _user_id = user_id, _force_run = True)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Subtopics generation failed")
    

@app.get("/entities_names/{user_id}", status_code=200)
async def get_user_entities_names(user_id: str):
    try:
        names = getter.get_entities_names_by_user_id(user_id)
        return names
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Entities not found")

@app.get("/placeholder_image", 
         responses = {200: {"content": {"image/png": {}}}},
        response_class=FileResponse)
async def get_placeholder_image():
    return FileResponse("./app/assets/images/library_placeholder.jpg")