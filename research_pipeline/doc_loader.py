def load_research_document(path: str):

    with open(path, "r") as f:
        text = f.read()

    return text