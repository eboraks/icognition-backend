import app.getters as getter
import pytest
from app.gemini_prompts_models import SummarizePrompt, EntitiesPrompt, IdentifyQuestionsAnswerPrompt, AskQuestionPrompt, TopicPrompt
from app.models import Document, Entity
from app.gemini_client import GeminiClient

genimi_client = GeminiClient()


user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'


@pytest.mark.asyncio
async def test_summarization():
    document = getter.get_document_by_id(109)

    prompt = SummarizePrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, SummarizePrompt)

    assert generated_response is not None
    assert generated_response.what_this_article_is_about is not None
    assert generated_response.key_learning_from_article is not None
    assert len(generated_response.key_points) > 0
    assert len(generated_response.citations_sentances) > 0
    assert generated_response.citations_sentances is not None
    assert generated_response.meta_answer is not None
    assert generated_response.meta_answer == "SUCCESS"


    document = generated_response.populate_document(document)
    assert document.is_about is not None
    assert document.learning_from_document is not None
    assert len(document.summary_bullet_points) > 0 
    

@pytest.mark.asyncio
async def test_entities():
    document = getter.get_document_by_id(109)

    prompt = EntitiesPrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, EntitiesPrompt)

    assert generated_response is not None
    assert len(generated_response.entities) > 0



@pytest.mark.asyncio
async def test_topics():
    document = getter.get_document_by_id(109)

    prompt = TopicPrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, TopicPrompt)

    assert generated_response is not None
    assert len(generated_response.topics) > 0


@pytest.mark.asyncio
async def test_questions_answers():
    document = getter.get_document_by_id(109)

    prompt = IdentifyQuestionsAnswerPrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, IdentifyQuestionsAnswerPrompt)

    assert generated_response is not None
    assert len(generated_response.questions_answers) > 0
    assert generated_response.meta_answer is not None
    assert generated_response.meta_answer == "SUCCESS"

    for qa in generated_response.questions_answers:
        assert qa.question is not None
        assert qa.answer is not None
        assert qa.citiation is not None
        assert len(qa.citiation) > 0
    

@pytest.mark.asyncio
async def test_ask_question():
    document = getter.get_document_by_id(109)

    prompt = AskQuestionPrompt.build_prompt([document], "Who is Trump and what does it do?")
    generated_response = await genimi_client.generate_response(prompt, AskQuestionPrompt)

    assert generated_response is not None
    assert generated_response.answer is not None
    assert generated_response.meta_answer is not None
    assert generated_response.meta_answer == "SUCCESS"
    assert generated_response.documents_citations is not None
    assert len(generated_response.documents_citations) > 0

    for dc in generated_response.documents_citations:
        assert dc.document_id is not None
        assert dc.citations is not None
        assert len(dc.citations) > 0
    


@pytest.mark.asyncio
async def test_run_all():
    ## The purpose of this test it to make sure that the gemini_client.py and gemini_prompts_models.py are working as expected
    document = getter.get_document_by_id(109)

    ## Test Summarization
    prompt = SummarizePrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, SummarizePrompt)

    assert generated_response is not None

    ## Test Entities
    prompt = EntitiesPrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, EntitiesPrompt)

    assert generated_response is not None

    ## Test Questions and Answers
    prompt = IdentifyQuestionsAnswerPrompt.build_prompt(document.original_text)
    generated_response = await genimi_client.generate_response(prompt, IdentifyQuestionsAnswerPrompt)

    assert generated_response is not None

    ## Test Ask Question
    prompt = AskQuestionPrompt.build_prompt([document], "Who is Trump and what does it do?")
    generated_response = await genimi_client.generate_response(prompt, AskQuestionPrompt)

    assert generated_response is not None
    