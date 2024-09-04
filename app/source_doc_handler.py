import pymupdf4llm as pdffile, pathlib, os, datetime, logging
import pathlib

from app.models import Source, Document

class SourceDocHandler:
    def __init__(self):
        self.local_bucket = os.getenv("LOCAL_BUCKET")
        self.source = None
        self.document = None

    def add_source(self, source_id: int) -> None:
        """
        This function adds a source to the handler
        """
        self.source = Source.get(Source.id == source_id)

    def add_document(self, document_id: int) -> None:
        """
        This function adds a document to the handler
        """
        self.document = Document.get(Document.id == document_id)

    