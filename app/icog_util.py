import logging
import sys
import string
import numpy as np
import math

from stop_words import get_stop_words
from nltk.tokenize import word_tokenize
from transformers import AutoTokenizer
from typing import Any, Dict, List, Union
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words


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

