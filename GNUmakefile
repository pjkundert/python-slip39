#
# GNU 'make' file
# 

# PY[3] is the target Python interpreter.  It must have pytest installed.
PY3=python3

VERSION=$(shell $(PY3) -c 'exec(open("slip39/version.py").read()); print( __version__ )')

# To see all pytest output, uncomment --capture=no
PYTESTOPTS=-vv # --capture=no --log-cli-level=INFO

PY3TEST=TZ=$(TZ) $(PY3) -m pytest $(PYTESTOPTS)

.PHONY: all test clean upload
all:			help

help:
	@echo "GNUmakefile for cpppo.  Targets:"
	@echo "  help			This help"
	@echo "  test			Run unit tests under Python3"
	@echo "  build			Build dist packages under Python3"
	@echo "  install		Install in /usr/local for Python3"
	@echo "  clean			Remove build artifacts"
	@echo "  upload			Upload new version to pypi (package maintainer only)"

test:
	$(PY3TEST)


doctest:
	$(PY3TEST) --doctest-modules


analyze:
	flake8 -j 1 --max-line-length=200 \
	  --ignore=W503,E201,E202,E221,E223,E226,E231,E242,E251,E265,E272,E274 \
	  slip39

pylint:
	cd .. && pylint slip39 --disable=W,C,R


build-check:
	@$(PY3) -m build --version \
	    || ( echo "\n*** Missing Python modules; run:\n\n        $(PY3) -m pip install --upgrade pip setuptools build\n" \
	        && false )

build:	build-check clean
	$(PY3) -m build
	@ls -last dist

dist/slip39-$(VERSION)-py3-none-any.whl: build

install:	dist/slip39-$(VERSION)-py3-none-any.whl
	$(PY3) -m pip install --force-reinstall $^


# Support uploading a new version of slip32 to pypi.  Must:
#   o advance __version__ number in slip32/version.py
#   o log in to your pypi account (ie. for package maintainer only)

upload: build
	python3 -m twine upload --repository pypi dist/*

clean:
	@rm -rf MANIFEST *.png build dist auto *.egg-info $(shell find . -name '*.pyc' -o -name '__pycache__' )


# Run only tests with a prefix containing the target string, eg test-blah
test-%:
	$(PY3TEST) *$*_test.py

unit-%:
	$(PY3TEST) -k $*


#
# Target to allow the printing of 'make' variables, eg:
#
#     make print-CXXFLAGS
#
print-%:
	@echo $* = $($*)
	@echo $*\'s origin is $(origin $*)
