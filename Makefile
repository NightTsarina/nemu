SRC = src/
TEST = t/
BUILDDIR = build/lib/
DISTDIR = dist/

COVERAGE = $(or $(shell which coverage), $(shell which python-coverage), \
	   coverage)

all:
	./setup.py build

install: all
	./setup.py install

test: all
	retval=0; \
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		echo $$i; \
		PYTHONPATH="$(BUILDDIR):$$PYTHONPATH" $$i || retval=$$?; \
		done; exit $$retval

coverage: all
	rm -f .coverage
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		set -e; \
		PYTHONPATH="$(BUILDDIR):$$PYTHONPATH" $(COVERAGE) -x $$i; \
		done
	$(COVERAGE) -r -m `find "$(BUILDDIR)" -name \\*.py -type f`
	rm -f .coverage

clean:
	./setup.py clean
	rm -f `find -name \*.pyc` .coverage *.pcap

distclean: clean
	rm -rf "$(DISTDIR)"

MANIFEST:
	find . -path ./.hg -prune -o -path ./build -prune -o \
		-name \*.pyc -prune -o -name \*.swp -prune -o \
		-name MANIFEST -prune -o -type f -print | \
		sed 's#^\./##' | sort > MANIFEST

dist: MANIFEST
	./setup.py sdist

.PHONY: clean distclean dist test coverage install MANIFEST
