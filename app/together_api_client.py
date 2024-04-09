from typing import Any
import os
import logging
import sys
import re
import json
import aiohttp
import asyncio
from time import sleep
from pydantic import ValidationError
from transformers import AutoTokenizer
from app.icog_util import truncate_text
from app.models import DocumentPrompt, DocumentPromptOne


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

config = os.environ


class ApiCallException(Exception):
    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


class PromptTemplates:
    def __init__(self) -> None:
        self.template = ""
        pass

    def getTemplate(self) -> str:
        return self.template

    def __name__(self) -> str:
        return self.__class__.__name__

    def __call__(self, text):
        pass




class TogetherMixtralClient:
    """
    APIModel class is used to generate summaries by calling the Together Mistral 7x8 Service.

    It handles constructing the API request, sending it, and processing the response.

    Key responsibilities:
    - Initialize the API client with auth token and endpoint
    - Build the API request payload from the input text
    - Send request to API and get response
    - Extract and clean up the summary text from the API response
    """

    def __init__(self) -> None:
        self._api_token = config["TOGETHER_TOKEN"]
        self._options = {"use_cache": True}
        self._api_url = "https://api.together.xyz/inference"
        self._model_name = "mistralai/Mixtral-8x7B-Instruct-v0.1"
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_name, use_fast=True, use_cache=False
        )
        self._max_length = 32000
        self._retry_sleep = 30
        self._retry_attempts = 0
        self._retry_max_attempts = 2
        self._client_session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "content-type": "application/json",
                "accept": "application/json",
                "User-Agent": "Icognition App",
            }
        )
 

    def build_query(self, templete: str, body_text: str) -> str:
        results = templete.format(BODY=body_text)
        tokens = self._tokenizer.encode(results, return_tensor="np")
        if len(tokens[0]) > self._max_length:
            logging.warn(f"Query is too big, let shorten the body text")

        return results

    async def api_call(self, payload) -> dict:
        API_URL = self._api_url
        async with self._client_session.post(API_URL, json=payload) as res:
            status = res.status
            if status == 200:
                return await res.json()
            else:
                logging.info(f"API Call Error: {res.reason}. Status code: {status}")
                raise ApiCallException(
                    "Error during API call",
                    {
                        "status_code": status,
                        "content": str(res.content._exception),
                        "reason": res.reason,
                    },
                )
                return None

    async def generate(
        self,
        body_text: str,
        model: DocumentPrompt = DocumentPromptOne,
        temperature=0.2,
        top_p=0.8,
        top_k=70,
    ) -> DocumentPrompt:
        ## Use template to generate prompt
        ## Build payload
        payload = {
            "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "messages": model.get_messages(body_text),
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": 1,
            "response_format": {
                "type": "json_object",
                "schema": model.model_json_schema(),
            },
        }

        continue_loop = True
        self._retry_attempts = 0

        while continue_loop:
            try:
                self._retry_attempts += 1
                logging.debug(f"Attempt {self._retry_attempts} to generate summary")
                res = await self.api_call(payload)
                logging.debug(f"Response status: {res['status']}")

            except ApiCallException as e:
                logging.error(f"Error calling API and/or handleResponse: {e}")
                raise e

            try:
                answer = model.model_validate_json(
                    res["output"]["choices"][0]["text"]
                )
                answer.usage = res["usage"]

            except ValidationError as e:
                logging.error(f"Error validating JSON: {e}")
                raise e

            if answer is not None:
                logging.debug(
                    f"Answer is not None. Stop retrying. Number of attempts {self._retry_attempts}"
                )
                continue_loop = False
            elif self._retry_attempts <= self._retry_max_attempts:
                logging.debug(
                    f"Answer is None. Retry. Number of attempts {self._retry_attempts}"
                )
                continue_loop = True
                sleep(self._retry_sleep)
            else:
                continue_loop = False
                logging.error(
                    f"Exitting retry loop. Number of attempts {self._retry_attempts}"
                )

        return answer