
#from pypdf import PdfReader
import pymupdf 

TEST_FILE = "files/inputs/Level-1-Unit-1-printable-Morpheme-tiles.pdf"

def main():
    
    doc = pymupdf.open(TEST_FILE)
    print(f"Pages: {len(doc)}")

    for page_num, page in enumerate(doc):

        images = page.get_images(full=True)
        text = page.get_text()
        drawings = page.get_drawings()
        print(f"\n=== Page {page_num + 1} ===")
        print(f"{len(images)} image(s)")
        print(f"{len(drawings)} drawing(s)")
        #print(text)


    # reader = PdfReader(TEST_FILE)

    # for i, page in enumerate(reader.pages):
    #     text = page.extract_text()
    #     print(f"--- Page {i + 1}")
    #     print(text)



if __name__ == "__main__":
    main()
