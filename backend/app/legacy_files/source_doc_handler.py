import pymupdf4llm
import os, sys, logging, json
import markdown
import app.html_parser as html_parser
from pathlib import Path
from app.models import Page, Document, PagePayload
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
                select(Source ).where(and_(Source.filename == filename, Source.user_id == user_id))
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
    
    async def generate_doc_from_pdf(self, source: Source, callback) -> None:
        
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

        payload = PagePayload(url=html_file, user_id=source.user_id, html=content, source='pdf')
        page = html_parser.create_page(payload)

        ## URL and Filename are not the same, but in this case we use them for the same thing - unique identifying the source
        page.clean_url = source.filename
        doc = self.create_document_from_page(page, source_type='pdf')
        doc.image_url = "https://placeholder.ai/icon/icons8-pdf-80"

        with Session(engine) as session:
            session.add(source)
            source.document_id = doc.id
            session.commit()
            session.refresh(source)

        await callback({"message": "generate_doc_from_pdf_done", "source": source})

    def create_document_from_page(self, page: Page, source_type = 'web') -> Document:
        session = Session(engine)
        doc = session.scalar(select(Document).where(Document.url == page.clean_url))

        ## If Document isn't already exist, create it
        if doc:
            session.close()
            return doc

        doc = Document()
        doc.title = page.title
        doc.url = page.clean_url
        doc.source_type = source_type
        doc.authors = ", ".join(page.authors) if page.authors else None
        doc.metadata_keywords = ", ".join(page.keywords) if page.keywords else None
        doc.locale = page.locale
        doc.publication_date = page.publish_date
        doc.image_url = page.image_url
        doc.site_name = page.site_name
        doc.metadata_description = page.metadata_description
        
        session.add(doc)
        session.commit()
        session.refresh(doc)
        session.close()

        return doc
    
    def write_file(self, filename: str, content: str) -> None:
        """
        This function writes the content to the file
        This is used to test FUSE functionality in the local bucket
        """
        filepath = os.path.join(self.local_bucket, filename)

        with open(filepath, "w") as file:
            file.write(content)
    
    def read_file(self, filename: str) -> str:
        """
        This function reads the content of the file
        This is used to test FUSE functionality in the local bucket
        """
        filepath = os.path.join(self.local_bucket, filename)

        with open(filepath, "r") as file:
            content = file.read()
        
        return content

        

    