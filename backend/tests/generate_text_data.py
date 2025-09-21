from app import html_parser

urls = [
    "https://www.yahoo.com/finance/news/collecting-degrees-thermometer-atlanta-woman-110000419.html",
    "https://www.yahoo.com/lifestyle/archaeologists-found-extraordinary-pyramid-apparently-150000080.html",
    "https://www.yahoo.com/entertainment/richard-romanus-actor-mean-streets-150542330.html",
]


def save_text_to_file(text, filename):
    with open(filename, "w") as file:
        file.write(text)


for url in urls:
    page = html_parser.create_page(url)
    if len(page.full_text) > 1:
        file_name = f"tests/data/{url.split('/')[-1]}.txt"
        save_text_to_file(page.full_text, file_name)
