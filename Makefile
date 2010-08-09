SRC = src
TEST = test
BUILDDIR = build
DISTDIR = dist

# stupid distutils, it's broken in so many ways
SUBBUILDDIR = $(shell python -c 'import distutils.util, sys; print "lib.%s-%s" % (distutils.util.get_platform(), sys.version[0:3])')
PYTHON25 := $(shell python -c 'import sys; v = sys.version_info; print (1 if v[0] <= 2 and v[1] <= 5 else 0)')

ifeq ($(PYTHON25),0)
BUILDDIR := $(BUILDDIR)/$(SUBBUILDDIR)
else
BUILDDIR := $(BUILDDIR)/lib
endif

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
	$(COVERAGE) -c
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
