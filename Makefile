
environment:
	conda env create --name website -f environment.yml

go:
	cd morpheme-cards && npm run dev

update: final_json

final_json: lessons
	@echo "Adding final lesson details to JSON..."
	python3 update_card_json.py

lessons: parse_pdfs
	@echo "Getting lesson details..."
	python3 parse_pdf_lessons.py

parse_pdfs: 
	@echo "Getting morpheme card details..."
	python3 parse_pdfs.py


