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
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		echo $$i; \
		PYTHONPATH="$(BUILDDIR):$$PYTHONPATH" $$i || exit 1; \
		done

coverage: all
	rm -f .coverage
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		set -e; \
		PYTHONPATH="$(BUILDDIR):$$PYTHONPATH" $(COVERAGE) -x $$i; \
		done
	$(COVERAGE) -r -m `find "$(SRC)" -name \\*.py -type f`
	rm -f .coverage

clean:
	./setup.py clean
	rm -f `find -name \*.pyc` .coverage *.pcap

distclean: clean
	rm -rf "$(DISTDIR)"

dist:
	./setup.py sdist

.PHONY: clean distclean dist test coverage install
