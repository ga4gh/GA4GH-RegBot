from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_document(text):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=100
    )

    chunks = splitter.split_text(text)

    return chunks