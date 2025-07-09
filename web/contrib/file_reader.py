import logging
from PyPDF2 import PdfReader


logger = logging.getLogger("django")

PDF_MAX_PAGE_LIMIT = 10


def open_pdf(filepath: str):
    logger.debug(f"Opening PDF file: {filepath}")
    reader = PdfReader(filepath)
    number_of_pages = len(reader.pages)
    if number_of_pages > PDF_MAX_PAGE_LIMIT:
        raise ValueError(f"PDF has more than {PDF_MAX_PAGE_LIMIT} pages")
    pages = ""
    for page in reader.pages:
        text = page.extract_text()
        pages += text + "\n\n"
    return pages, number_of_pages
