import logging
import os, sys
import string
import numpy as np
import math
import nltk

from stop_words import get_stop_words
from nltk.tokenize import word_tokenize
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
 
config = os.environ
 
model_name = config["TOGETHER_MODEL"] # "mistralai/Mixtral-8x7B-Instruct-v0.1"
# tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True, use_cache=False)

nltk.download('punkt')

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)

translator = str.maketrans("", "", string.punctuation)
stopwords = get_stop_words("en")


def remove_stop_words(string, return_format="String"):
    """This method removes stop words from a string.

    Args:
        string (str): string from which the stop words should be removed
        return_format (str, optional): format of the returned data type String or List. Defaults to 'String'.

    Returns:
        str: string without stop words
    """
    tokens = word_tokenize(string)
    filtered_tokens = [w for w in tokens if not w in stopwords]

    if return_format == "List":
        return filtered_tokens
    else:
        return " ".join(filtered_tokens)


def truncate_text(
    text: str, llm_max_tokens: int, number_of_tokens: int, LANGUAGE="english"
) -> str:
    """
    Truncate_text recursive function that tokenizes and splits the text into chunks of 512 tokens
    Then, use the LSA summarizer to summarize each chunk

    Args:
        text (str): The text that need to be truncate
        llm_max_tokens (int): Maximum number of tokens the LLM support.
        number_of_tokens (int): The number of LLM tokens that text have

    Retruns:
        Summary (str)
    """

    summarizer = LsaSummarizer()

    if number_of_tokens > llm_max_tokens:
        logging.info(
            f"Text is too long. Splitting into chunks of {llm_max_tokens} tokens"
        )
        parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
        num_sentences = len(parser.document.sentences)
        avg_tokens_per_sentence = int(number_of_tokens / num_sentences)
        excess_tokens = number_of_tokens - llm_max_tokens
        num_sentences_to_summarize = num_sentences - (
            math.ceil(excess_tokens / avg_tokens_per_sentence)
        )

        logging.info(f"Number of tokens: {number_of_tokens}.")
        logging.info(f"Number of sentences: {num_sentences}.")
        logging.info(f"Average tokens per sentence: {avg_tokens_per_sentence}.")
        logging.info(f"Excess tokens: {excess_tokens}.")
        logging.info(f"Number of sentences to summarize: {num_sentences_to_summarize}")

        summary = summarizer(parser.document, num_sentences_to_summarize)
        summary_text = " ".join([sentence._text for sentence in summary])
        return summary_text

    else:
        logging.info("Text is short enough. No need to summarizing.")
        return text

class DocSummarizer():
    
    def __init__(self):
        self._summarizer = LsaSummarizer()
        self._LANGUAGE = "english"
    
    def __call__(self, text: str, reduce_by: int = 0.6) -> str:
        """
        Summarize the text using LSA summarizer

        Args:
            text (str): The text that need to be summarize
            reduce_by (float, optional): The ratio of the summary to the original text. Defaults to 0.6.

        Returns:
            Summary (str)
        """
        parser = PlaintextParser.from_string(text, Tokenizer(self._LANGUAGE))
        num_sentences = len(parser.document.sentences)
        num_sentences_to_summarize = int(num_sentences * reduce_by)
        summary = self._summarizer(parser.document, num_sentences_to_summarize)
        summary_text = " ".join([sentence._text for sentence in summary])
        return summary_text


def deduplicate_objects_list(l: list) -> list:
    """
    Deduplicate a list objects using the id attribute

    Args:
        l (list): The list that need to be deduplicated

    Returns:
        list: The deduplicated list
    """
    ids = [i.id for i in l]
    duplicates = {x for x in ids if ids.count(x) > 1}
    if len(duplicates) > 0:
        logging.warning(f"Deduplicate objects found: {duplicates}. List length: {len(l)}")

        for d in duplicates:
            for r in l:
                if r.id == d:
                    l.remove(r)
                    break
        logging.info(f"Removed duplicate. New list length: {len(l)}")
        return deduplicate_objects_list(l)
    else:
        return l