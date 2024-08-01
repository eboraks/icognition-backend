import app.getters as getter
import pytest
from app.gemini_prompts_models import SummarizePrompt, EntitiesPrompt, IdentifyQuestionsAnswerPrompt, AskQuestionPrompt
from app.models import Document, Entity
from app.genimi_client import generate_response 


user_id = 'yU13Hk9BwEQiREgh91YM6EFKR7M2'


@pytest.mark.asyncio
async def test_summarization():
    document = getter.get_document_by_id(109)

    prompt = SummarizePrompt.build_prompt(document.original_text)
    generated_response = await generate_response(prompt, SummarizePrompt)

    assert generated_response is not None  

@pytest.mark.asyncio
async def test_entities():
    document = getter.get_document_by_id(109)

    prompt = EntitiesPrompt.build_prompt(document.original_text)
    generated_response = await generate_response(prompt, EntitiesPrompt)

    assert generated_response is not None


@pytest.mark.asyncio
async def test_questions_answers():
    document = getter.get_document_by_id(109)

    prompt = IdentifyQuestionsAnswerPrompt.build_prompt(document.original_text)
    generated_response = await generate_response(prompt, IdentifyQuestionsAnswerPrompt)

    assert generated_response is not None
    

@pytest.mark.asyncio
async def test_ask_question():
    document = getter.get_document_by_id(109)

    prompt = AskQuestionPrompt.build_prompt([document], "Who is Trump and what does it do?")
    generated_response = await generate_response(prompt, AskQuestionPrompt)

    assert generated_response is not None
