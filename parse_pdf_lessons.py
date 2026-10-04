from collections import defaultdict
import json
import sys

import pdfplumber

# The RGB fill color (0-1 scale, as pdfplumber reports it) used for the
# red/maroon highlight box borders in this guide.
HIGHLIGHT_COLOR = (0.5607843, 0.2392157, 0.3333333)

# Tolerance (in points) for deciding two rectangles "touch" and belong
# to the same highlight box.
TOUCH_TOLERANCE = 1.0

# Incidental words that can land inside a highlight box's bounding
# rectangle but aren't actual morphemes (legend/caption text).
EXCLUDE_WORDS = {"Indicates", "target", "morphemes"}


INPUT_FILE_PATH = "files/inputs/U1_Optional-Morpheme-Tile-Guide.pdf"
OUTPUT_FILE_PATH = "files/outputs/lessons_output.json"



def inspect_fill_colors(pdf_path):
    """
    Utility: print every distinct rectangle fill color found in the PDF,
    with a count of how many rectangles use it. Run this on a new guide
    to find its highlight color if HIGHLIGHT_COLOR doesn't match.
    """
    with pdfplumber.open(pdf_path) as pdf:
        for pnum, page in enumerate(pdf.pages, 1):
            counts = defaultdict(int)
            for r in page.rects:
                if r["fill"]:
                    counts[r["non_stroking_color"]] += 1
            print(f"Page {pnum}:")
            for color, n in sorted(counts.items(), key=lambda kv: -kv[1]):
                print(f"  {color} -> {n} rects")


def _rects_touch(a, b, tol=TOUCH_TOLERANCE):
    """True if rectangle a (expanded by tol) overlaps rectangle b."""
    ax0, ax1 = a["x0"] - tol, a["x1"] + tol
    atop, abot = a["top"] - tol, a["bottom"] + tol
    bx0, bx1, btop, bbot = b["x0"], b["x1"], b["top"], b["bottom"]
    return not (ax1 < bx0 or bx1 < ax0 or abot < btop or bbot < atop)


def _cluster_rects(rects):
    """
    Union-find clustering: groups rectangles that touch/overlap into
    connected components. Used to merge a highlight box's separate
    edge-segments (top/bottom/left/right) back into one box.
    """
    parent = list(range(len(rects)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _rects_touch(rects[i], rects[j]):
                union(i, j)

    groups = defaultdict(list)
    for i in range(len(rects)):
        groups[find(i)].append(rects[i])
    return list(groups.values())


def _bounding_box(rects):
    x0 = min(r["x0"] for r in rects)
    x1 = max(r["x1"] for r in rects)
    top = min(r["top"] for r in rects)
    bottom = max(r["bottom"] for r in rects)
    return x0, x1, top, bottom


def _extract_header_labels(words, header_top_min=115, header_top_max=128):
    """
    Finds the "Week X - Lesson Y" header row and returns a list of
    (x0_of_label, label_text) tuples, one per column, in reading order.
    Assumes each header is exactly 5 tokens: Week, N, -, Lesson, M.
    """
    header_words = [w for w in words if header_top_min < w["top"] < header_top_max]
    header_words.sort(key=lambda w: w["x0"])

    labels = []
    for i in range(0, len(header_words), 5):
        chunk = header_words[i : i + 5]
        if len(chunk) < 5:
            continue
        label = " ".join(w["text"] for w in chunk)
        labels.append((chunk[0]["x0"], label))
    return labels


def extract_morpheme_tiles(pdf_path, highlight_color=HIGHLIGHT_COLOR):
    """
    Parses the PDF at pdf_path and returns a dict mapping each
    "Week X - Lesson Y" label to a list of its highlighted morphemes,
    e.g.:

        {
            "Week 1 - Lesson 3": ["hope", "ful", "less", "s", "ed", "ing", ...],
            "Week 2 - Lesson 3": ["tract", "or", "dis", "re"],
            ...
        }

    If a lesson has more than one separate highlight box, all of their
    morphemes are combined into that lesson's single list, in the
    order they appear on the page.
    """
    result = defaultdict(list)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            labels = _extract_header_labels(words)
            if not labels:
                continue  # no header row found on this page; skip

            highlight_rects = [
                r
                for r in page.rects
                if r["fill"] and r["non_stroking_color"] == highlight_color
            ]
            if not highlight_rects:
                continue

            boxes = [_bounding_box(g) for g in _cluster_rects(highlight_rects)]

            for (bx0, bx1, btop, bbottom) in boxes:
                # Match this box to the nearest column header by x-position.
                label = min(labels, key=lambda l: abs(l[0] - bx0))[1]

                morphemes = []
                for w in words:
                    if (
                        w["text"].isalpha()
                        and w["text"] not in EXCLUDE_WORDS
                        and (btop - 1) <= w["top"] <= (bbottom + 1)
                        and (bx0 - 5) <= w["x0"] <= (bx1 + 5)
                    ):
                        morphemes.append((w["top"], w["text"]))

                morphemes.sort(key=lambda m: m[0])  # top-to-bottom reading order
                result[label].extend(text for _, text in morphemes)

    return dict(result)


def main():
    data = extract_morpheme_tiles(INPUT_FILE_PATH)
    #print(json.dumps(data, indent=2))
    with open(OUTPUT_FILE_PATH, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    main()
