
from pypdf import PdfReader

TEST_FILE = "files/inputs/Level-1-Unit-1-printable-Morpheme-tiles.pdf"

def main():
    
    reader = PdfReader(TEST_FILE)

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        print(f"--- Page {i + 1}")
        print(text)



if __name__ == "__main__":
    main()
