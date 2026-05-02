.PHONY: api-run

api-run:
	python -m uvicorn mmfp.api.main:app --reload
