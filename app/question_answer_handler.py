from sqlalchemy import and_, select
import app.getters as getter
from app.models import (
    Question_Answer,
    QuestionAnswerStatus,
    Document,
    RagAnswerPublic,
)
from sqlalchemy.orm import Session
from app.db_connector import get_engine
from app.gemini_client import GeminiClient
from app.gemini_prompts_models import AskQuestionPrompt, IdentifyQuestionsAnswerPrompt


from app.log import get_logger
logging = get_logger(__name__)

engine = get_engine()
genimi_client = GeminiClient()


async def generate_doc_quesions_answers(user_id: str, doc: Document, testing: bool = False) -> list[Question_Answer]:

    try:
        logging.info(f"Generating questions and answers for document {doc.id}")
        
        ## If file exists, load it and return payload
        prompt = IdentifyQuestionsAnswerPrompt.build_prompt(doc.original_text)
        response = await genimi_client.generate_response(prompt, IdentifyQuestionsAnswerPrompt)
        ## Using the entities builder to get the entities from the response    
        qans = await response.questions_answers_builder(document_id = doc.id)
 

    except Exception as e:
        logging.error(f"generate_doc_quesions_answers: Error {e}")


    try:
        with Session(engine) as session:
            session.add_all(qans)
            session.commit()
        return qans
    except Exception as e:
        logging.error(f"Error saving questions and answers {e}")



async def insert_question_answer_for_doc(document_id: str, RagAnswerPublic: RagAnswerPublic) -> RagAnswerPublic:
    """
    This function inserts a question and answer for a document
    """
    
    qa = Question_Answer()
    qa.document_id = document_id
    qa.question = RagAnswerPublic.question
    qa.answer = RagAnswerPublic.answer
    qa.citations = [c.to_dict() for c in RagAnswerPublic.citations]
    qa.created_by = 'User'
    qa.question_vector = await genimi_client.generate_embedding(qa.question)
    

    with Session(engine) as session:
        session.add(qa)
        session.commit()
        session.refresh(qa)
        return qa.to_public()

async def custom_question(document_id: str, question: str, save: bool) -> RagAnswerPublic:
    """
    This function generates a summary with verbatim sentences
    """
    doc = getter.get_document_by_id(document_id) 
    
    prompt = AskQuestionPrompt.build_prompt([doc], question)
    generated_response = await genimi_client.generate_response(prompt, AskQuestionPrompt) 
    
    answer = generated_response.question_answer_builder(question=question)

    if (answer.status == QuestionAnswerStatus.COMPLETED_NO_SAVE.value and save):
        return await insert_question_answer_for_doc(document_id, answer)
    else:
        return answer
    
async def delete_question_answer(qa_id: str) -> bool:
    """
    This function marks a question and answer for deletion
    """
    with Session(engine) as session:
        qa = session.scalar(select(Question_Answer).where(Question_Answer.uuid == qa_id))
        qa.deleted = True
        session.commit()
        return True

def get_question_answer_by_document_id(document_id: int) -> list[Question_Answer]:
    session = Session(engine)
    qas = session.scalars(select(Question_Answer).where(and_(Question_Answer.document_id == document_id, Question_Answer.deleted == False))).all()
    session.close()
    return qas

def get_question_answer_public_by_document_id(document_id: int) -> list[RagAnswerPublic]:
    
    with Session(engine) as session:
        qas = session.scalars(select(Question_Answer).where(and_(Question_Answer.document_id == document_id, Question_Answer.deleted == False))).all()
        qas = [qa.to_public() for qa in qas]

    return qas