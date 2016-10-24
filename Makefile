SRC = src
TEST = test
BUILDDIR = build
DISTDIR = dist
COVERDIR = coverage
SRCFILES := $(shell find $(SRC) -type f)

# stupid distutils, it's broken in so many ways
SUBBUILDDIR := $(shell python -c 'import distutils.util, sys; \
	      print "lib.%s-%s" % (distutils.util.get_platform(), \
	      	sys.version[0:3])')
PYTHON25 := $(shell python -c 'import sys; v = sys.version_info; \
	print (1 if v[0] <= 2 and v[1] <= 5 else 0)')

ifeq ($(PYTHON25),0)
BUILDDIR := $(BUILDDIR)/$(SUBBUILDDIR)
else
BUILDDIR := $(BUILDDIR)/lib
endif

COVERAGE := $(or $(shell which coverage), $(shell which python-coverage), \
	    coverage)

all: build_stamp
build_stamp: $(SRCFILES)
	./setup.py build
	touch $@

install: all
	./setup.py install

test: all
	retval=0; \
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		echo $$i; \
		PYTHONPATH="$(BUILDDIR)" $$i || retval=$$?; \
		done; exit $$retval

coverage: coverage_stamp
	$(COVERAGE) -r -m `find "$(BUILDDIR)" -name \\*.py -type f`

coverage-report: coverage_stamp
	rm -rf $(COVERDIR)
	$(COVERAGE) -b -d $(COVERDIR) `find "$(BUILDDIR)" -name \\*.py -type f`
	@echo "Coverage report created in $(COVERDIR)/index.html"

coverage_stamp: build_stamp
	if [ `id -u` -ne 0 ]; then \
		echo "Coverage needs to be run as root."; false; fi
	for i in `find "$(TEST)" -perm -u+x -type f`; do \
		set -e; \
		PYTHONPATH="$(BUILDDIR)" $(COVERAGE) -x $$i; \
		done
	$(COVERAGE) -c
	touch $@

clean:
	./setup.py clean
	rm -f `find -name \*.pyc` .coverage *.pcap *_stamp
	rm -rf $(COVERDIR)
	#$(MAKE) -C $(CURDIR)/benchmarks/ clean

distclean: clean
	rm -rf "$(DISTDIR)"

MANIFEST: distclean
	find . -path ./.git\* -prune -o -path ./build -prune -o \
		-path ./docs/debconf-talk -prune -o \
		-path ./benchmarks -prune -o \
		-name \*.pyc -prune -o -name \*.swp -prune -o \
		-name MANIFEST -prune -o -name .hg\* -prune -o \
		-type f -print | sed 's#^\./##' | sort > MANIFEST

dist: MANIFEST
	./setup.py sdist

.PHONY: clean distclean dist test coverage install MANIFEST
