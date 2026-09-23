
"""
Script to add icon flag to JSON and keep only active card types
"""

import json 

INPUT_FILE = "files/outputs/output.json"


def add_label_flags(data):
    for item in data:
        item["icon_types"] = []
        if item["front_has_icon"] or item["back_has_icon"]:
            if "alternate" in item.get("note", "").lower():
                item["icon_types"].append("alternate")
            if "chameleon" in item.get("note", "").lower():
                item["icon_types"].append("chameleon")


def add_lesson_unit_data(data):
    for item in data:
        unit_items = item["unit_label"]
        unit_parts = unit_items.split()
        item["level"] = next((x for x in unit_parts if x.startswith("L")), None)
        item["unit"] = next((x for x in unit_parts if x.startswith("U")), None)


def add_word_type(data):
    for item in data:
        origin = item.get("origin", "").lower()
        if "prefix" in origin:
            item["word_type"] = "prefix"
        elif "suffix" in origin:
            item["word_type"] = "suffix"
        elif "base" in origin:
            item["word_type"] = "base"
        elif "root" in origin:
            item["word_type"] = "root"
        else:
            item["word_type"] = "ERROR"

def add_word_origin(data):
    for item in data:
        origin = item.get("origin", "").lower()
        if "anglo" in origin:
            item["word_origin"] = "Anglo-Saxon"
        elif "latin" in origin:
            item["word_origin"] = "Latin"
        elif "greek" in origin:
            item["word_origin"] = "Greek"
        else:
            item["word_origin"] = "ERROR"

def main():
    print(f"\nReading File: {INPUT_FILE}\n")

    with open(INPUT_FILE, 'r') as file:
        data = json.load(file)
    
    print(f"Data is type: {type(data)}")
    print(f"JSON contains {len(data)} items.")

    data = [item for item in data if item["is_card"]]

    print(f"After filtering data contains {len(data)} true cards.")

    add_label_flags(data)
    add_lesson_unit_data(data)
    add_word_type(data)
    add_word_origin(data)
    
    types = []
    for item in data:
        types.append(item["word_type"])
        #print(item)

    print(set(types))

    with open ("files/outputs/updated_cards.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent = 4)

if __name__ == "__main__":
    main()
