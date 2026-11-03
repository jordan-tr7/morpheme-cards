from collections import defaultdict
import json
import re

import pdfplumber

# The RGB fill color (0-1 scale, as pdfplumber reports it) used for the
# gray lesson background boxes.
GRAY_COLOR = (0.9490196, 0.9490196, 0.9490196)

# The RGB fill color used for the red/maroon target morpheme boxes.
HIGHLIGHT_COLOR = (0.5607843, 0.2392157, 0.3333333)

# Tolerance (in points) for deciding two rectangles "touch" and belong
# to the same box.
TOUCH_TOLERANCE = 1.0

# Words that can appear in the graphic but are not morphemes.
EXCLUDE_WORDS = {"Indicates", "target", "morphemes"}

# ============================================================================
# USER PARAMETERS
# ============================================================================

LEVEL_NUMBER = 1

INPUT_FILES = [
    "files/inputs/U1_Optional-Morpheme-Tile-Guide.pdf",
    "files/inputs/Unit-2-Optional-Morpheme-Tile-Guide.pdf"
]

OUTPUT_FILE_PATH = "files/outputs/lessons_output.json"


def inspect_fill_colors(pdf_path):
    """
    Utility: print every distinct rectangle fill color found in the PDF.
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


def extract_unit_number(pdf):
    """
    Attempts to locate a Unit number anywhere in the PDF text.

    Examples:
        Unit 1
        Unit 2 - Optional Morpheme Tile Guide
        U1
        U2
    """
    for page in pdf.pages:
        text = page.extract_text() or ""

        match = re.search(r"\bUnit\s+(\d+)\b", text, re.IGNORECASE)
        if match:
            return int(match.group(1))

        match = re.search(r"\bU(\d+)\b", text)
        if match:
            return int(match.group(1))

    return None


def _rects_touch(a, b, tol=TOUCH_TOLERANCE):
    """True if rectangle a (expanded by tol) overlaps rectangle b."""
    ax0, ax1 = a["x0"] - tol, a["x1"] + tol
    atop, abot = a["top"] - tol, a["bottom"] + tol

    bx0, bx1 = b["x0"], b["x1"]
    btop, bbot = b["top"], b["bottom"]

    return not (
        ax1 < bx0
        or bx1 < ax0
        or abot < btop
        or bbot < atop
    )


def _cluster_rects(rects):
    """
    Union-find clustering: groups touching rectangles into components.
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


def _extract_header_labels(words):
    """
    Finds lesson labels like:

        Week 1 - Lesson 1
        Week 1 - Lesson 2

    Returns:
        [(x0, label), ...]
    """
    week_indices = [
        i for i, w in enumerate(words)
        if w["text"] == "Week"
    ]

    labels = []

    for idx in week_indices:
        chunk = words[idx:idx + 5]

        if len(chunk) == 5:
            label = " ".join(w["text"] for w in chunk)
            labels.append((chunk[0]["x0"], label))

    return labels


def _find_preceding_id(words, current_word, vertical_tolerance=3):
    """
    Attempts to locate the numeric morpheme ID associated with a morpheme.

    In the guide, IDs are typically immediately to the left of the
    morpheme text on the same row.

    Example:

        57 bio
        ^^ ID
    """

    candidates = []

    for w in words:

        if not w["text"].isdigit():
            continue

        if abs(w["top"] - current_word["top"]) > vertical_tolerance:
            continue

        if w["x0"] >= current_word["x0"]:
            continue

        candidates.append(w)

    if not candidates:
        return None

    nearest = max(candidates, key=lambda x: x["x0"])

    try:
        return int(nearest["text"])
    except Exception:
        return None


def _morphemes_in_box(words, box, tol=1):
    """
    Returns a list of:

    [
        {
            "id": 57,
            "morpheme": "bio"
        }
    ]
    """
    bx0, bx1, btop, bbottom = box

    hits = []

    for w in words:

        inside_box = (
            (btop - tol) <= w["top"] <= (bbottom + tol)
            and (bx0 - 5) <= w["x0"] <= (bx1 + 5)
        )

        if not inside_box:
            continue

        text = w["text"].strip()

        if not text.isalpha():
            continue

        if text in EXCLUDE_WORDS:
            continue

        morpheme_id = _find_preceding_id(words, w)

        hits.append(
            (
                w["top"],
                w["x0"],
                {
                    "id": morpheme_id,
                    "morpheme": text
                }
            )
        )

    hits.sort(key=lambda x: (x[0], x[1]))

    return [item for _, _, item in hits]


def extract_morpheme_tiles(
    pdf_path,
    level_number,
    gray_color=GRAY_COLOR,
    highlight_color=HIGHLIGHT_COLOR
):
    """
    Returns:

    {
        "Level": 1,
        "Unit": 2,
        "Lessons": {
            "Week 1 - Lesson 1": {
                "all": [...],
                "target": [...]
            }
        }
    }
    """

    with pdfplumber.open(pdf_path) as pdf:

        unit_number = extract_unit_number(pdf)

        result = {
            "Level": level_number,
            "Unit": unit_number,
            "Lessons": {}
        }

        for page in pdf.pages:

            words = page.extract_words()
            labels = _extract_header_labels(words)

            print(f"Page {page.page_number}")
            print("Labels found:", labels)

            if not labels:
                continue

            # ==========================================================
            # ALL MORPHEMES
            # ==========================================================

            gray_rects = [
                r
                for r in page.rects
                if r["fill"]
                and r["non_stroking_color"] == gray_color
            ]

            gray_boxes = [
                _bounding_box(g)
                for g in _cluster_rects(gray_rects)
            ]

            best_gray_per_label = {}

            for box in gray_boxes:

                bx0 = box[0]

                label = min(
                    labels,
                    key=lambda l: abs(l[0] - bx0)
                )[1]

                area = (
                    (box[1] - box[0])
                    * (box[3] - box[2])
                )

                if (
                    label not in best_gray_per_label
                    or area > best_gray_per_label[label][0]
                ):
                    best_gray_per_label[label] = (area, box)

            for label, (_, box) in best_gray_per_label.items():

                result["Lessons"].setdefault(
                    label,
                    {
                        "all": [],
                        "target": []
                    }
                )

                result["Lessons"][label]["all"] = (
                    _morphemes_in_box(words, box)
                )

            # ==========================================================
            # TARGET MORPHEMES
            # ==========================================================

            highlight_rects = [
                r
                for r in page.rects
                if r["fill"]
                and r["non_stroking_color"] == highlight_color
            ]

            highlight_boxes = [
                _bounding_box(g)
                for g in _cluster_rects(highlight_rects)
            ]

            for box in highlight_boxes:

                bx0 = box[0]

                label = min(
                    labels,
                    key=lambda l: abs(l[0] - bx0)
                )[1]

                result["Lessons"].setdefault(
                    label,
                    {
                        "all": [],
                        "target": []
                    }
                )

                result["Lessons"][label]["target"].extend(
                    _morphemes_in_box(words, box)
                )

    return result


def deep_merge_extend(dict1, dict2):
    """
    Recursively merge dictionaries while extending lists.
    """

    result = dict1.copy()

    for key, value in dict2.items():

        if key in result:

            if (
                isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = deep_merge_extend(
                    result[key],
                    value
                )

            elif (
                isinstance(result[key], list)
                and isinstance(value, list)
            ):
                result[key] = result[key] + value

            else:
                result[key] = value

        else:
            result[key] = value

    return result


def main():

    combined_output = {
        "Level": LEVEL_NUMBER,
        "Units": []
    }

    for pdf_file in INPUT_FILES:

        print("Processing:", pdf_file)

        try:

            result = extract_morpheme_tiles(
                pdf_file,
                LEVEL_NUMBER
            )

            combined_output["Units"].append(result)

            print("Success")

        except Exception as e:

            print("Failed")
            print(type(e))
            print(e)
            raise

    with open(OUTPUT_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            combined_output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"Output written to: {OUTPUT_FILE_PATH}")


    


if __name__ == "__main__":
    main()




# from collections import defaultdict
# import json
# import sys

# import pdfplumber

# # The RGB fill color (0-1 scale, as pdfplumber reports it) used for the
# # red/maroon highlight box borders in this guide.
# GRAY_COLOR = (0.9490196, 0.9490196, 0.9490196)
# HIGHLIGHT_COLOR = (0.5607843, 0.2392157, 0.3333333)

# # Tolerance (in points) for deciding two rectangles "touch" and belong
# # to the same highlight box.
# TOUCH_TOLERANCE = 1.0

# # Incidental words that can land inside a highlight box's bounding
# # rectangle but aren't actual morphemes (legend/caption text).
# EXCLUDE_WORDS = {"Indicates", "target", "morphemes"}

# #INPUT_FILE_PATH = 
# INPUT_FILES = [
#     "files/inputs/U1_Optional-Morpheme-Tile-Guide.pdf",
#     "files/inputs/Unit-2-Optional-Morpheme-Tile-Guide.pdf"
# ]

# OUTPUT_FILE_PATH = "files/outputs/lessons_output.json"

# def inspect_fill_colors(pdf_path):
#     """
#     Utility: print every distinct rectangle fill color found in the PDF,
#     with a count of how many rectangles use it. Run this on a new guide
#     to find its gray/highlight colors if the constants above don't match.
#     """
#     with pdfplumber.open(pdf_path) as pdf:
#         for pnum, page in enumerate(pdf.pages, 1):
#             counts = defaultdict(int)
#             for r in page.rects:
#                 if r["fill"]:
#                     counts[r["non_stroking_color"]] += 1
#             print(f"Page {pnum}:")
#             for color, n in sorted(counts.items(), key=lambda kv: -kv[1]):
#                 print(f"  {color} -> {n} rects")
 
# def _rects_touch(a, b, tol=TOUCH_TOLERANCE):
#     """True if rectangle a (expanded by tol) overlaps rectangle b."""
#     ax0, ax1 = a["x0"] - tol, a["x1"] + tol
#     atop, abot = a["top"] - tol, a["bottom"] + tol
#     bx0, bx1, btop, bbot = b["x0"], b["x1"], b["top"], b["bottom"]
#     return not (ax1 < bx0 or bx1 < ax0 or abot < btop or bbot < atop)
 
# def _cluster_rects(rects):
#     """
#     Union-find clustering: groups rectangles that touch/overlap into
#     connected components.
#     """
#     parent = list(range(len(rects)))
 
#     def find(x):
#         while parent[x] != x:
#             parent[x] = parent[parent[x]]
#             x = parent[x]
#         return x
 
#     def union(x, y):
#         px, py = find(x), find(y)
#         if px != py:
#             parent[px] = py
 
#     for i in range(len(rects)):
#         for j in range(i + 1, len(rects)):
#             if _rects_touch(rects[i], rects[j]):
#                 union(i, j)
 
#     groups = defaultdict(list)
#     for i in range(len(rects)):
#         groups[find(i)].append(rects[i])
#     return list(groups.values())
 
# def _bounding_box(rects):
#     x0 = min(r["x0"] for r in rects)
#     x1 = max(r["x1"] for r in rects)
#     top = min(r["top"] for r in rects)
#     bottom = max(r["bottom"] for r in rects)
#     return x0, x1, top, bottom
 
# def _extract_header_labels(words, header_top_min=115, header_top_max=128):
#     """
#     Finds the "Week X - Lesson Y" header row and returns a list of
#     (x0_of_label, label_text) tuples, one per column, in reading order.
#     Assumes each header is exactly 5 tokens: Week, N, -, Lesson, M.
#     """

#     # for w in words:
#     #     if "Week" in w["text"] or "Lesson" in w["text"]:
#     #         print(
#     #             w["text"],
#     #             "top=", w["top"],
#     #             "x0=", w["x0"]
#     #         )

#     # for w in sorted(words, key=lambda w: w["top"]):
#     #     if "Week" in w["text"]:
#     #         print(w)

#     week_indices = [i for i, w in enumerate(words) if w["text"] == "Week"]

#     labels = []

#     for idx in week_indices:
#         chunk = words[idx:idx + 5]

#         if len(chunk) == 5:
#             label = " ".join(w["text"] for w in chunk)
#             labels.append((chunk[0]["x0"], label))

#     return labels

#     # header_words = [w for w in words if header_top_min < w["top"] < header_top_max]
#     # header_words.sort(key=lambda w: w["x0"])
 
#     # labels = []
#     # for i in range(0, len(header_words), 5):
#     #     chunk = header_words[i : i + 5]
#     #     if len(chunk) < 5:
#     #         continue
#     #     label = " ".join(w["text"] for w in chunk)
#     #     labels.append((chunk[0]["x0"], label))
#     # return labels
 
# def _words_in_box(words, box, tol=1):
#     bx0, bx1, btop, bbottom = box
#     hits = []
#     for w in words:
#         if (
#             w["text"].isalpha()
#             and w["text"] not in EXCLUDE_WORDS
#             and (btop - tol) <= w["top"] <= (bbottom + tol)
#             and (bx0 - 5) <= w["x0"] <= (bx1 + 5)
#         ):
#             hits.append((w["top"], w["text"]))
#     hits.sort(key=lambda m: m[0])  # top-to-bottom reading order
#     return [text for _, text in hits]
 
 
# def extract_morpheme_tiles(pdf_path, gray_color=GRAY_COLOR, highlight_color=HIGHLIGHT_COLOR):
#     """
#     Parses the PDF at pdf_path and returns a dict mapping each
#     "Week X - Lesson Y" label to:
 
#         {
#             "all":    [every morpheme in that lesson's gray background box],
#             "target": [the subset of those morphemes marked in red boxes],
#         }
 
#     If a lesson has more than one separate red box, their morphemes are
#     combined into a single "target" list, in page order.
#     """
#     result = {}
 
#     with pdfplumber.open(pdf_path) as pdf:
#         for page in pdf.pages:
#             words = page.extract_words()
#             labels = _extract_header_labels(words)
#             print("Page", page.page_number)
#             print("Labels found:", labels)
#             if not labels:
#                 print("No labels found")
#                 continue  # no header row found on this page; skip
 
#             # --- Full list: largest gray cluster per column ---
#             gray_rects = [
#                 r for r in page.rects if r["fill"] and r["non_stroking_color"] == gray_color
#             ]
#             gray_boxes = [_bounding_box(g) for g in _cluster_rects(gray_rects)]
 
#             print("\nPAGE", page.page_number)
#             print("labels:", labels)
#             print("gray rects:", len(gray_rects))
#             print("gray boxes:", len(gray_boxes))

#             best_gray_per_label = {}
#             for box in gray_boxes:
#                 bx0 = box[0]
#                 label = min(labels, key=lambda l: abs(l[0] - bx0))[1]
#                 area = (box[1] - box[0]) * (box[3] - box[2])
#                 if label not in best_gray_per_label or area > best_gray_per_label[label][0]:
#                     best_gray_per_label[label] = (area, box)
 
#             for label, (_, box) in best_gray_per_label.items():
#                 result.setdefault(label, {"all": [], "target": []})
#                 result[label]["all"] = _words_in_box(words, box)
 
#             # --- Target subset: red/maroon boxes per column (can be several) ---
#             highlight_rects = [
#                 r
#                 for r in page.rects
#                 if r["fill"] and r["non_stroking_color"] == highlight_color
#             ]
#             highlight_boxes = [_bounding_box(g) for g in _cluster_rects(highlight_rects)]
 
#             for box in highlight_boxes:
#                 bx0 = box[0]
#                 label = min(labels, key=lambda l: abs(l[0] - bx0))[1]
#                 result.setdefault(label, {"all": [], "target": []})
#                 result[label]["target"].extend(_words_in_box(words, box))
 
#     return result


# def deep_merge_extend(dict1, dict2):
#     result = dict1.copy()

#     for key, value in dict2.items():
#         if key in result:
#             # If both values are dictionaries, merge them recursively
#             if isinstance(result[key], dict) and isinstance(value, dict):
#                 result[key] = deep_merge_extend(result[key], value)
#             # If both values are lists, extend them together
#             elif isinstance(result[key], list) and isinstance(value, list):
#                 result[key] = result[key] + value
#             else:
#                 # Fallback / overwrite if data types don't match or aren't lists/dicts
#                 result[key] = value
#         else:
#             # If the key doesn't exist yet, simply add it
#             result[key] = value
            
#     return result


# def main():

    

#     data = {}

#     for f in INPUT_FILES:

    
#         print("Processing:", f)

#         try:

#             res = extract_morpheme_tiles(f)
#             print("Success")
#             print(res)
#             #print(inspect_fill_colors(f))
#             data = deep_merge_extend(data, res) 
#         except Exception as e:
#             print("Failed")
#             print(type(e))
#             print(e)
#             raise
        
#     #print(json.dumps(data, indent=2))
#     with open(OUTPUT_FILE_PATH, "w") as f:
#         json.dump(data, f, indent=2)


# if __name__ == "__main__":
#     main()
