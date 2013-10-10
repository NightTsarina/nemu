IMGS = openlogo.svg
PDF_IMGS := $(patsubst %.svg,%.pdf,$(patsubst %.dia,%.pdf,$(IMGS)))
DVI_IMGS := $(patsubst %.svg,%.eps,$(patsubst %.dia,%.eps,$(IMGS)))

ALL = nemu.pdf

all: $(ALL)

%.eps: %.dia
	inkscape -E $@ $<

%.pdf: %.dia
	inkscape -A $@ $<

%.eps: %.svg
	inkscape -E $@ $<

%.pdf: %.svg
	inkscape -A $@ $<

%.ps: %.dvi
	dvips $<

nemu.dvi: nemu.tex $(DVI_IMGS)
	latex $<
	latex $<

nemu.pdf: nemu.tex $(PDF_IMGS)
	pdflatex $<
	pdflatex $<

clean:
	rm -f $(PDF_IMGS) $(DVI_IMGS) *.aux *.out *.log *.dvi *.nav *.snm \
		*.toc *.vrb *.bak $(ALL)
