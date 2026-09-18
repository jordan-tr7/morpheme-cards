
environment:
	conda env create --name website -f environment.yml

go:
	cd morpheme-cards && npm run dev
