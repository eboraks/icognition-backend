from pathlib import Path
import pymupdf4llm
import os, sys, logging
import markdown

from app.models import Source, Document

from app.db_connector import get_engine
from sqlalchemy import (
    select,
    delete,
    and_,
    or_,
    text,
    exc,
)
from sqlalchemy.orm import Session

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

engine = get_engine()


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

    def generate_filepath(self, source_id: str, user_id: str, filename: str) -> Path:
        """
        This function generates the filepaths for the pdf files
        """
        filepath = Path(f"{self.local_bucket}/{user_id}/{source_id}/{filename.replace(' ', '_')}")
        
        os.makedirs(filepath.parent, exist_ok=True) 

        return filepath

    def source_with_file_exists(self, filename: str, user_id: str) -> bool:
        """
        This function checks if a source with the given filename exists
        """
        with Session(engine) as session:
            source = session.execute(
                select(Source).where(and_(Source.filename == filename, Source.user_id == user_id))
            ).scalar_one_or_none()

        return source is not None
    
    def create_source(self, user_id: str, filename: str = None)-> Source:
        """
        This function creates a source
        """
        source_exits = self.source_with_file_exists(filename=filename, user_id=user_id)
        if source_exits:
            raise Exception("A source with the given filename and user_id already exists")

        with Session(engine) as session:
            source = Source(user_id=user_id)
            session.add(source)
            session.commit()
            session.refresh(source)
            if filename:
                source.filename = filename
                source.filepath = self.generate_filepath(source_id=source.id, user_id=user_id, filename=filename)
                session.commit()
                session.refresh(source)            
        
        return source
    
    async def convert_pdf_to_markup(self, source: Source, callback) -> None:
        
        md_file = f"{source.filepath}.md"
        html_file = f"{source.filepath}.html"
        Path(md_file).write_bytes(pymupdf4llm.to_markdown(source.filepath).encode())
        markdown.markdownFromFile(input=md_file, output=html_file)

        ## Remove the horizontal line from the html file. This line represents page breaks in the pdf
        with open(html_file, "r") as file:
            content = file.read()

        content = content.replace("<hr />", "")

        with open(html_file, "w") as file:
            file.write(content)

        callback({"filename": md_file})    

        

    