from fastapi import FastAPI, HTTPException, BackgroundTasks, status, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import List
from app.models import (
    Answer,
    Source,
    Document,
    PagePayload,
    DocumentPublic,
    HTTPError,
    Question_Answer,
    RagAnswerPublic,
    QuestionPlayload,
    SearchPayload,
    SearchResults,
    Study_Project_Document_Link,
    SubTopicDisplay,
    TreeNode,
    StudyProjectPublic,
    StudyTaskPublic,
    ProjectDocumentlinkPayload
)
import app.study_project_handler as project_handler
import logging
import sys, json
import app.app_logic as app_logic
import app.subtopics_util as subtopics_util
import app.html_parser as html_parser
import app.getters as getter
from app.search_handler import SearchHandler
from app.prompt_models import RAGPrompt

search = SearchHandler()


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    level=logging.INFO,
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


@app.post("/document/question", response_model=RagAnswerPublic, status_code=200)
async def post_document_question(payload: QuestionPlayload):
    try:
        logging.info(f"Question endpoint called on {payload.document_id} with question {payload.question}")
        answer = await app_logic.custom_question(question=payload.question, document_id=payload.document_id)
        logging.info(f"Question endpoint called on {payload.document_id} with answer {answer.answer}")
        return answer
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Answer generation failed")



@app.post(
    "/bookmark",
    responses={
        400: {
            "model": HTTPError,
            "description": "Reporting back errors",
        },
        404: {"model": HTTPError, "description": "Page is not supported"},
        201: {"model": Source, "description": "Bookmark created successfully"},
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
    _bookmark = getter.get_source_by_url(payload.user_id, page.clean_url)
    if _bookmark is not None:
        _doc = getter.get_document_by_source_id(_bookmark.id)
        
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
        _bookmark = app_logic.create_source_bookmark(page, payload.user_id)
        logging.info(f"Bookmark created for {_bookmark.url}")
        background_tasks.add_task(generate_document, bookmark = _bookmark)
        response.status_code = status.HTTP_201_CREATED
        return _bookmark


@app.post(
    "/document/regenerate",
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
async def generate_document(bookmark: Source):
    document = getter.get_document_by_id(bookmark.document_id)

    if document.status in ["Pending", "Done", "Failure"]:
        logging.info(f"Background task for document ID: {bookmark.document_id}")
        document = await app_logic.generate_summary(doc= document)
        await app_logic.generate_embeddings_for_docs(docs = [document], user_id = bookmark.user_id)
        logging.info(f"Background task for document ID: {bookmark.document_id} completed")

    
    if len(getter.get_entities_ids_by_document_id(document.id)) == 0:
        ent_success = await app_logic.generate_entities(user_id= bookmark.user_id, doc = document)
        topic_success = await app_logic.generate_topics(user_id= bookmark.user_id, doc = document)
        logging.info(f"Background task for generating entities and topics for: {document.id} completed. Result, entities: {ent_success} topic: {topic_success}")
        await app_logic.generate_embeddings_for_entities(user_id =  bookmark.user_id)


    if len(getter.get_question_answer_by_document_id(document.id)) == 0:
        success = await app_logic.generate_doc_quesions_answers(user_id= bookmark.user_id, doc = document)
        logging.info(f"Background task for generating questions and answers for: {document.id} completed. Result, {success}")
        ## For now, we are not generating embeddings for questions and answers




## Background task to regenerate summaries from LLM if not already exists
async def regenerate_document(doc: Document):

    if doc.status in ["Pending", "Done", "Failure"]:

        new_doc = await app_logic.generate_summary(doc)
        if new_doc:
            logging.info(f"Background task for document ID: {new_doc.id} completed")
        else:
            logging.error(
                f"Background document regenaring for document ID: {doc.id} failed"
            )


@app.get("/bookmarks/user/{user_id}", response_model=List[Source], status_code=200)
async def get_bookmarks_by_user_id(user_id: str):
    bookmarks = getter.get_sources_by_user_id(user_id)

    if bookmarks is None:
        raise HTTPException(status_code=404, detail="Bookmarks not found")

    logging.info(f"Icognition return {len(bookmarks)} bookmarks")
    return bookmarks

@app.post("/bookmark/user", response_model=Source, status_code=200)
async def get_bookmarks_by_user_id(payload: PagePayload):
    bookmark = getter.get_source_by_url(payload.user_id, payload.url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    return bookmark


@app.get(
    "/documents_plus/user/{user_id}",
    response_model=List[DocumentPublic],
    status_code=200,
)
async def get_documents_plus_by_user_id(user_id: str):
    
    documents = getter.get_documents_display_by_user_id(user_id)
    
    if documents is None:
        raise HTTPException(status_code=404, detail="Documents not found")

    logging.info(f"Icognition return {len(documents)} documents_plus")
    return documents

@app.get('/document/{id}/html_elements', status_code=200)
async def get_document_html_elements(id: str):
    try:
        doc = getter.get_document_public_by_id(id)
        return json.loads(doc.html_elements)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Document not found")



@app.get("/bookmark", response_model=Source, status_code=200)
async def get_bookmark_by_url(url: str):
    bookmark = getter.get_source_by_url(url)

    if bookmark is None:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    logging.info(f"Icognition return bookmark {bookmark.id}")
    return bookmark


@app.get("/bookmark/{id}/document")
async def get_bookmark_document(id: str, response: Response):
    logging.info(f"Icognition bookmark document endpoint called on {id}")
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


@app.get("/document_plus/{source_id}", responses={
        404: {
            "model": HTTPError,
            "description": "Returning document error",
        },
        206: {"model": None, "description": "Document is being processed"},
        200: {"model": DocumentPublic, "description": "Document is ready"},
    })
async def get_document_plus(source_id: str, response: Response, background_tasks: BackgroundTasks):
    """get document with entities and concepts"""

    logging.info(f"Document plus -> endpoint called on bookmark {source_id}")
    document = getter.get_document_by_source_id(source_id)

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

        return document.to_public()
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return document.to_public()


@app.get("/document/{id}")
async def get_document(id: str, response: Response):
    logging.info(f"Icognition document endpoint called on {id}")
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
    
@app.get("/document/{id}/xray")
async def get_document_summary(id: str, response: Response, force: str | None = None):
    
        try:
            res = getter.get_document_public_by_id(id)
            response.status_code = status.HTTP_200_OK
            return res
    
        except ValueError as e:
            logging.error(e)
            raise HTTPException(status_code=404, detail=e)


@app.get("/document/{id}/questions_answers")
async def get_document_questions_answers(id: str, response: Response):

    try:
        qas = getter.get_question_answer_by_document_id(id)
        qas = [qa.to_display() for qa in qas]
        response.status_code = status.HTTP_200_OK
        return qas

    except ValueError as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail=e)


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
async def delete_bookmark(id: str) -> None:
    logging.info(f"Delete bookmark and associated records for id: {id}")
    app_logic.delete_bookmark_and_associate_records(id)


@app.delete("/document/{id}", status_code=204)
async def delete_document(id: str) -> None:
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
    logging.info(f"Search documents with query: {search_payload.query}")
    
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
        



@app.get("/generate_embedding/{user_id}", status_code=200)
async def generate_embedding(user_id: str):
    try:
        await app_logic.generate_embeddings(user_id=user_id)
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


## Study project endpoints
@app.get("/study_projects/{user_id}", response_model=List[StudyProjectPublic], status_code=200)
async def get_study_projects(user_id: str):
    try:
        projects = project_handler.get_study_projects(user_id)
        return projects
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Study projects not found")
    

@app.post("/study_project", response_model=StudyProjectPublic, status_code=200)
async def create_study_project(project: StudyProjectPublic, background_tasks: BackgroundTasks):
    try:
        project = await project_handler.create_study_project(name=project.name, 
                objective=project.objective, 
                user_id = project.user_id, 
                tasks_descriptions=project.tasks)
        
        background_tasks.add_task(project_handler.generate_project_response, project_id = project.id, listener = event_listener)
        return project
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study project creation failed")
    
def event_listener(event):
    logging.info(f"Event listner called with event: {event}")


@app.get("/study_project/{id}", response_model=StudyProjectPublic, status_code=200)
async def get_study_project(id: str):
    try:
        project = project_handler.get_study_project_by_id(id)
        return project
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Study project not found")
    

@app.delete("/study_project/{id}", status_code=204)
async def delete_study_project(id: str):
    try:
        project_handler.delete_study_project(id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study project deletion failed")
    

@app.post("/study_task", response_model=StudyTaskPublic, status_code=200)
async def create_study_task(task: StudyTaskPublic):
    try:
        task = project_handler.create_study_task(project_id=task.project_id, description=task.description)
        return task
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study task creation failed")
    
@app.post("/study_tasks", response_model=List[StudyTaskPublic], status_code=200)
async def create_study_tasks(tasks: List[StudyTaskPublic]):
    try:
        created_tasks = []
        for task in tasks:
            created_tasks.append(project_handler.create_study_task(project_id=task.project_id, description=task.description))
        return created_tasks
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Study task creation failed")
    
@app.get("/study_project_tasks/{project_id}", response_model=List[StudyTaskPublic], status_code=200)
async def get_study_tasks(project_id: str):
    try:
        tasks = project_handler.get_study_tasks(project_id)
        return tasks
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Study tasks not found")
    

@app.get("/study_project/{project_id}/related_entities", response_model=List[TreeNode], status_code=200)
async def get_project_entities(project_id: str):
    try:
        entities = project_handler.get_project_entities(project_id)
        return entities
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=404, detail="Entities not found")
    

@app.post("/project_document_link", status_code=200, response_model= Study_Project_Document_Link)
async def link_project_document(payload: ProjectDocumentlinkPayload):
    try:
        return project_handler.link_project_document(project_id = payload.project_id, document_id = payload.document_id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Project document link failed")
    
@app.post("/project_document_unlink", status_code=200)
async def unlink_project_document(payload: ProjectDocumentlinkPayload):
    try:
        return project_handler.unlink_project_document(project_id = payload.project_id, document_id = payload.document_id)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=500, detail="Project document unlink failed")