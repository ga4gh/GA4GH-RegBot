from langchain_community.document_loaders import PyMuPDFLoader


def load_framework_pdf(path: str):

    loader = PyMuPDFLoader(path)

    docs = loader.load()

    return docs