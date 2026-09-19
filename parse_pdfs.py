
"""
Script to Parse PDFs into Flashcards
"""


import json
import re
import sys
from collections import defaultdict
import pdfplumber


INPUT_FILE_PATH = "files/inputs/Level-1-Unit-1-printable-Morpheme-tiles.pdf"
OUTPUT_FILE_PATH = "files/outputs/output.json"


def cmyk_to_hex(color):
    """
    This method converts a pdfplumber non_stroking_color tuple
    to a #rrggbb hex string. 
    
    pdfplumber can give back CMYK (4), RGB (3) or grayscale depending
    on how pdf handles color content
    """
    if color is None:
        return None 
    
    if len(color) == 4:
        c, m, y, k = color 
        r = 255 * (1 - c) * (1 - k)
        g = 255 * (1 - m) * (1 - k)
        b = 255 * (1 - y) * (1 - k)
    elif len(color) == 3:
        r, g, b, = (v * 255 for v in color)
    elif len(color) == 1:
        r = g = b = color[0] * 255
    else:
        return None

    # return final hex string
    return "#{:02x}{:02x}{:02x}".format(round(r), round(g), round(b))


def color_for_word(page, word):
    """
    Function to look up the fill color of a word's first char. 
    """
    for c in page.chars:
        if (
            c["x0"] >= word["x0"] - 0.5
            and c["x1"] <= word["x1"] + 0.5
            and c["top"] >= word["top"] - 0.5
            and c["bottom"] <= word["bottom"] + 0.5
        ):
            return cmyk_to_hex(c.get("non_stroking_color"))
    return None


def detect_grid(page, min_col_gap=100, min_row_gap=50):
    """
    This function infers card-grid row/col boundaries from page's 
    ruled lines. 
    
    Returns (rows, cols) where each is a list of (start, end) tuples
    in the PDF "top-down" coords. pdfplumber's top/bot : x0/x1
    """
    xs = sorted({round(l["x0"], 1) for l in page.lines if abs(l["x0"] - l["x1"]) < 0.5})
    ys = sorted({round(l["top"], 1) for l in page.lines if abs(l["top"] - l["bottom"]) < 0.5})
 
    cols = [(xs[i], xs[i + 1]) for i in range(len(xs) - 1) if xs[i + 1] - xs[i] > min_col_gap]
    rows = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1) if ys[i + 1] - ys[i] > min_row_gap]
    return rows, cols


def words_in_bbox(all_words, x0, x1, top, bottom, pad=1.0):
    return [
        w for w in all_words
        if w["x0"] >= x0 - pad and w["x1"] <= x1 + pad 
        and w["top"] >= top - pad and w["bottom"] <= bottom + pad 
    ]




def group_into_lines(words, tol=2.0):
    """Cluster words sharing roughly the same baseline into text lines."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for ln in lines:
            if abs(ln["top"] - w["top"]) <= tol:
                ln["words"].append(w)
                break
        else:
            lines.append({"top": w["top"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
        ln["size"] = round(ln["words"][0]["size"], 1)
    lines.sort(key=lambda l: l["top"])
    return lines
 
 
def cell_has_icon(page, x0, x1, top, bottom):
    """True if any vector shape (icon art) is drawn inside this cell."""
    for s in page.curves + page.rects:
        if s["x0"] >= x0 - 1 and s["x1"] <= x1 + 1 and s["top"] >= top - 1 and s["bottom"] <= bottom + 1:
            return True
    return False
 
 
def parse_front_cell(page, all_words, x0, x1, top, bottom):
    lines = group_into_lines(words_in_bbox(all_words, x0, x1, top, bottom))
    cell = {}
    for ln in lines:
        if ln["size"] >= 30:
            cell["morpheme"] = ln["text"]
            cell["color"] = color_for_word(page, ln["words"][0])
        elif re.match(r"^L\d+\s*U\d+$", ln["text"]):
            cell["unit_label"] = ln["text"]
        else:
            cell.setdefault("other_text", []).append(ln["text"])
    cell["has_icon"] = cell_has_icon(page, x0, x1, top, bottom)
    return cell
 
 
def parse_back_cell(page, all_words, x0, x1, top, bottom):
    lines = group_into_lines(words_in_bbox(all_words, x0, x1, top, bottom))
    cell = {}
    cell_h = bottom - top
    definition_parts = []
    for ln in lines:
        rel = (ln["top"] - top) / cell_h if cell_h else 0
        size = ln["size"]
        if 11 <= size <= 13 and rel < 0.3 and "morpheme" not in cell:
            cell["morpheme"] = ln["text"]
            cell["color"] = color_for_word(page, ln["words"][0])
        elif 16 <= size <= 18:
            definition_parts.append(ln["text"])
        elif 11 <= size <= 13:
            cell["origin"] = (cell.get("origin", "") + " " + ln["text"]).strip()
        elif 9.5 <= size <= 10.5:
            cell["note"] = (cell.get("note", "") + " " + ln["text"]).strip()
        elif size < 9.5 and re.match(r"^\d+$", ln["text"]):
            cell["index"] = int(ln["text"])
        else:
            cell.setdefault("other_text", []).append(ln["text"])
    if definition_parts:
        cell["definition"] = " ".join(definition_parts)
    cell["has_icon"] = cell_has_icon(page, x0, x1, top, bottom)
    return cell
 

def extract_cards(pdf_path):
    cards = []
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        for i in range(0, len(pages) - 1, 2):
            front_page, back_page = pages[i], pages[i + 1]
 
            f_rows, f_cols = detect_grid(front_page)
            b_rows, b_cols = detect_grid(back_page)
            if len(f_rows) != len(b_rows) or len(f_cols) != len(b_cols):
                print(f"Warning: grid mismatch between pages {i+1} and {i+2}, skipping pair")
                continue
 
            f_words = front_page.extract_words(extra_attrs=["size", "fontname"])
            b_words = back_page.extract_words(extra_attrs=["size", "fontname"])
            n_cols = len(f_cols)
 
            for r, (ftop, fbot) in enumerate(f_rows):
                for c, (fx0, fx1) in enumerate(f_cols):
                    front = parse_front_cell(front_page, f_words, fx0, fx1, ftop, fbot)
 
                    mirrored_c = n_cols - 1 - c
                    bx0, bx1 = b_cols[mirrored_c]
                    btop, bbot = b_rows[r]
                    back = parse_back_cell(back_page, b_words, bx0, bx1, btop, bbot)
 
                    if not front.get("morpheme") and not back.get("morpheme"):
                        # Title/legend cell rather than an actual card -- keep
                        # it, but flag it so downstream code can filter it out.
                        cards.append({
                            "page_front": i + 1, "page_back": i + 2,
                            "row": r, "front_col": c,
                            "is_card": False,
                            "front": front, "back": back,
                        })
                        continue
 
                    cards.append({
                        "page_front": i + 1,
                        "page_back": i + 2,
                        "row": r,
                        "front_col": c,
                        "is_card": True,
                        "morpheme": front.get("morpheme") or back.get("morpheme"),
                        "unit_label": front.get("unit_label"),
                        "color": front.get("color") or back.get("color"),
                        "definition": back.get("definition"),
                        "origin": back.get("origin"),
                        "note": back.get("note"),
                        "index": back.get("index"),
                        "front_has_icon": front.get("has_icon", False),
                        "back_has_icon": back.get("has_icon", False),
                    })
    return cards
 
 
def render_cell_image(pdf_path, page_number, x0, x1, top, bottom, out_path, dpi=300):
    """Rasterize a single cell to a PNG, for when you need the icon as a real
    image rather than just a yes/no flag (requires pdf2image + poppler)."""
    from pdf2image import convert_from_path
 
    page_img = convert_from_path(
        pdf_path, dpi=dpi, first_page=page_number, last_page=page_number
    )[0]
    scale = dpi / 72.0
    box = (x0 * scale, top * scale, x1 * scale, bottom * scale)
    page_img.crop(box).save(out_path)
 
 
 
def main():
    #if len(sys.argv) != 3:
       # print("Usage: python parse_morpheme_cards.py input.pdf output.json")
       # sys.exit(1)
 
    cards = extract_cards(INPUT_FILE_PATH) #sys.argv[1]
    with open(OUTPUT_FILE_PATH, "w") as f:
        json.dump(cards, f, indent=2)
 
    real_cards = [c for c in cards if c.get("is_card")]
    print(f"Extracted {len(real_cards)} cards ({len(cards) - len(real_cards)} non-card cells) "
          f"-> {OUTPUT_FILE_PATH}")


if __name__ == "__main__":
    main()
    
