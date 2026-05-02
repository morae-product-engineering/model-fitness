.PHONY: api-run

api-run:
	# PYTHONPATH=. ensures the repo root is on sys.path so the `platform`
	# namespace package is found before the stdlib `platform` module.
	# This is required on Python 3.13+, which skips .pth files named
	# with a leading "__" (see: https://github.com/python/cpython/issues/122905).
	PYTHONPATH=. python -m uvicorn platform.api.main:app --reload
