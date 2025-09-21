from typing import Any
import requests
import os
import logging
import sys
import re
import json
from time import sleep
from transformers import AutoTokenizer
from app.icog_util import truncate_text


logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

config = os.environ


class LlamaTemplates:
    def __init__(self) -> None:
        self.template = ""
        pass

    def getTemplate(self) -> str:
        return self.template

    def __name__(self) -> str:
        return self.__class__.__name__

    def __call__(self, text):
        pass

    # Replace long space bigger then 2 with single space
    def clean_text(self, text: str) -> str:
        return re.sub(r"\s{2,}", " ", text)


class BulletPointTemplate(LlamaTemplates):
    def __init__(self):
        super(BulletPointTemplate, self).__init__()
        self.template = """
                <s>[INST] <<SYS>>
                You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe.  
                Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. 
                Please ensure that your responses are socially unbiased and positive in nature.
                If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
                If you don't know the answer to a question, please don't share false information.
                <</SYS>>
                Write up to six points that summarize the text between double quotes: ""{BODY}"" [/INST]"""

    def __call__(self, text) -> str:
        return self.clean_text(self.template.format(BODY=text))


class PeopleCompaniesPlacesTemplate(LlamaTemplates):
    def __init__(self):
        super(PeopleCompaniesPlacesTemplate, self).__init__()
        self.template = """<s>[INST] <<SYS>>
                You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe.  
                Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. 
                Please ensure that your responses are socially unbiased and positive in nature.
                If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. 
                If you don't know the answer to a question, please don't share false information.
                <</SYS>>
                Find people, companies, and places in the text between the double quotes. 
                Format each item wrap with XML element tags, for example <people>[PERSON]</poeple> for people, don't create tag in data is not correct. ""{BODY}"" [/INST]"""

    def __call__(self, text) -> str:
        return self.clean_text(self.template.format(BODY=text))


class ConceptsTemplate(LlamaTemplates):
    def __init__(self):
        super(ConceptsTemplate, self).__init__()
        self.template = """<s>[INST] <<SYS>>
                You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe.  
                Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. 
                Please ensure that your responses are socially unbiased and positive in nature.
                If a question does not make any sense, or is not factually coherent, 
                explain why instead of answering something not correct. 
                If you don't know the answer to a question, please don't share false information.
                <</SYS>>
                In the text between the double quotes. Identify the top 5 to 8 general concepts, subjects and ideas 
                and add an explanation that describe them. Avoid referring to the text. ""{BODY}"" [/INST]
                """

    def __call__(self, text) -> str:
        return self.clean_text(self.template.format(BODY=text))


class HfApiClient:
    """
    APIModel class is used to generate summaries by calling the HuggingFace API.

    It handles constructing the API request, sending it, and processing the response.

    Key responsibilities:
    - Initialize the API client with auth token and endpoint
    - Build the API request payload from the input text
    - Send request to API and get response
    - Extract and clean up the summary text from the API response
    """

    def __init__(self) -> None:
        self._api_token = config["HF_API_TOKEN"]
        self._options = {"use_cache": True}
        self._base_url = "https://api-inference.huggingface.co/models/"
        self._model_name = "meta-llama/Llama-2-70b-chat-hf"
        self._api_url = self._base_url + self._model_name
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_name, use_auth_token=config["HF_API_TOKEN"]
        )
        self._max_length = 4096
        self._retry_sleep = 30
        self._retry_attempts = 0
        self._retry_max_attempts = 2
        self._templates = LlamaTemplates()
        self._parameters = {
            "max_length": 4096,
            "max_new_tokens": 1000,
            "top_k": 10,
            "return_full_text": False,
            "do_sample": True,
            "num_return_sequences": 1,
            "temperature": 0.5,
            "repetition_penalty": 1.0,
            "length_penalty": 1.0,
        }

    def build_query(self, templete: str, body_text: str) -> str:
        results = templete.format(BODY=body_text)
        tokens = self._tokenizer.encode(results, return_tensor="np")
        if len(tokens[0]) > self._max_length:
            logging.warn(f"Query is too big, let shorten the body text")

        return results

    def api_call(
        self, body_text: str, template: LlamaTemplates, parameters, options
    ) -> dict:
        API_URL = self._api_url
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "content-type": "application/json",
        }

        query = template(body_text)
        payload = {"inputs": query, "parameters": parameters, "options": options}

        response = requests.post(API_URL, headers=headers, json=payload)

        # If error true, sleep for 30 seconds and
        # try again.
        # If error still true, return error message.
        status = response.status_code
        # In case the service isn't ready or overloaded
        if (status == 503 or status == 429) and (
            self._retry_attempts < self._retry_max_attempts
        ):
            logging.info(
                f"API Call Error: {response.content}. Retrying in {self._retry_sleep} seconds"
            )
            self._retry_attempts += 1
            sleep(self._retry_sleep)
            logging.info(f"Retrying now")
            return self.api_call(body_text, template, parameters, options)

        # In case there are too many failures
        elif status == 503 and self._retry_attempts >= self._retry_max_attempts:
            self._retry_attempts = 0
            logging.warn(f"Retry limit reached. Returning error")
            raise ResourceWarning("Retry limit reached. Returning an error")

        # In case text is too long
        elif status == 422:
            logging.warn(
                f"Error calling HF with {response.status_code} and message {response.content}. For: {body_text[:20]}"
            )
            # count tokens of body text
            text_tokens_ids = self._tokenizer(body_text, return_tensors="pt").input_ids
            text_num_tokens = len(text_tokens_ids[0])

            # count tokens of prompt
            template_tokens_ids = self._tokenizer(
                template.getTemplate(), return_tensors="pt"
            ).input_ids
            template_num_tokens = len(template_tokens_ids[0])

            ## New max length take into account the token in the template
            new_max_length = self._max_length - template_num_tokens
            logging.info(f"New max length is: {new_max_length}")
            new_body_text = truncate_text(body_text, new_max_length, text_num_tokens)
            logging.info(f"New body text length is {len(new_body_text)}")
            return self.api_call(new_body_text, template, parameters, options)

        elif response.status_code == 200:
            try:
                results = response.json()
                answer = results[0]["generated_text"]
                logging.info(
                    f"API Call successful. Status code {response.status_code}. Generated text length: {len(answer)}"
                )
                self._retry_attempts = 0
                return answer
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON response: {response}")
                return None
        else:
            logging.error(
                f"Response from HF API isn't right. Status code: {response.status_code} Contenct {response.content}"
            )
            return None

    def generate(self, body_text: str, template: LlamaTemplates) -> str:
        parameters = {
            "max_length": 4000,
            "max_new_tokens": 1000,
            "top_k": 10,
            "return_full_text": False,
            "do_sample": True,
            "num_return_sequences": 1,
            "temperature": 0.2,
            "repetition_penalty": 1.0,
            "length_penalty": 1.0,
        }
        options = {"use_cache": False}

        logging.info(f"Sending query to API with template: {template.__name__}...")

        try:
            results = self.api_call(body_text, template, parameters, options)

            if results == None:
                logging.error(f"API Call Error for template: {template.__name__}")
                return None
            else:
                logging.info(
                    f"API Call successful. Returning results. len(results): {len(results)}"
                )
            return results
        except ResourceWarning as e:
            logging.error(e)
            raise ResourceWarning(e)
        except Exception as e:
            logging.error(e)
            raise Exception(e)
