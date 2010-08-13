# vim: ts=4:sw=4:et:ai:sts=4

import csv, StringIO, subprocess

class Graph:
    [LINE, DOT, POINT, LINEPOINT] = range(0, 4)
    def __init__(self):
        self._plots = []
        self._title = None
    def set_title(self, title):
        self._title = title
    def add(self, plot):
        self._plots.append(plot)
    def generate(self, output_file):
        lines = self.gen_output()
        lines.insert(0, "set terminal postscript")
        lines.insert(0, "set output '%s'" % filename)
        gnuplot = subprocess.Popen(['gnuplot', '-'], 
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.STDOUT)
        gnuplot.communicate(input = "\n".join(lines))
    def Xplot(self, plotnr):
        lines = self.gen_output(plotnr)
        lines.insert(0, "set terminal wxt")
        lines.append('pause mouse')
        gnuplot = subprocess.Popen(['gnuplot', '-'], stdin = subprocess.PIPE)
        gnuplot.communicate(input = "\n".join(lines))
    def _style_to_str(self, style):
        d = {Graph.LINE: 'lines', Graph.DOT: 'dots', Graph.POINT: 'points', 
                Graph.LINEPOINT: 'linespoints'}
        return d[style]
    def gen_output(self, plots = None):
        if plots:
            plots = map(self._plots.__getitem__, plots)
        else:
            plots = self._plots
        lines = []
        if self._title:
            lines.append("set title '%s'" % self._title)
        line = []
        for plot in plots:
            line.append("'-' title '%s' with %s" % (plot.title(),
                self._style_to_str(plot.style())))
        lines.append('plot ' + ', '.join(line))
        for plot in plots:
            for r in plot.data():
                r = [str(d) for d in r]
                lines.append(' '.join(r))
            lines.extend(['e'])
        return lines

class Plot:
    def __init__(self, title, data, style = Graph.LINE):
        self._title = title
        self._data = data
        self._style = style
    def style(self):
        return self._style
    def title(self):
        return self._title
    def data(self):
        return self._data

class Row:
    def __init__(self, data, names = None):
        assert not names or len(names) == len(data)
        assert not names or all(map(lambda x: isinstance(x, str), names))
        self._data1 = list(data)
        if names:
            self._data2 = dict(zip(names, data))
        else:
            self._data2 = dict()
    def append(self, value, name = None):
        self._data1.append(value)
        if self._data2:
            assert name not in self._data2
            self._data2[name] = value
    def __getitem__(self, item):
        if isinstance(item, int):
            return self._data1[item]
        else:
            return self._data2[item]
    def __len__(self):
        return len(self._data1)
#    def __repr__(self):
#        return 

class Data:
    def __init__(self, rows = [], colnames = []):
        assert not (colnames and rows) or len(colnames) == len(rows[0])
        self._colnames = colnames
        self._data = []
        for r in rows:
            self.add_row(r)
    def add_row(self, row):
        if isinstance(row, Row):
            self._data.append(row)
        else:
            self._data.append(Row(row, self._colnames))
    def nrows(self):
        return len(self._data)
    def ncols(self):
        return len(self._data[0])
    def read_csv(self, stream, has_header = False):
        self._data = []
        self._colnames = []
        self._datadict = []
        n = 0
        reader = csv.reader(stream)
        for line in reader:
            if n and len(line) != n:
                raise 'Not matching number of columns in different rows'
            if not n:
                n = len(line)
                if has_header:
                    self._colnames = line
                    continue
            row = []
            for i in line:
                try:
                    row.append(float(i))
                except:
                    row.append(i)
            self._data.append(row)
        if has_header:
            self._gen_data_dict()
    def write_csv(self, stream):
        writer = csv.writer(stream)
        writer.writerows(self._data)
    def column(self, col):
        if isinstance(col, int):
            return [row[col] for row in self._data]
        else:
            return [row[col] for row in self._datadict]
    def row(self, row):
        return self._data[row]
    def cell(self, row, col):
        if isinstance(col, int):
            return self._data[row][col]
        else:
            return self._datadict[row][col]
    def select(self, cols = None, selectfn = lambda x: True,
            groupfn = lambda x: None):
        if cols:
            cols = list(cols)
        else:
            cols = range(self.ncols())
        groups = {}
        res = []
        for row in self._data if isinstance(cols[0], int) else self._datadict:
            if not selectfn(row):
                continue

    def add_column(self, fn, colname = None):
        if self._colnames:
            assert colname
        for row in self._data:
            row.append(fn(row))
        if colname:
            self._colname.append(colname)
            for row in self._datadict:
                row[colname] = fn(row)
        return self.ncols() - 1

def uniq(l):
    data = []
    for i in l:
        if i not in data:
            data.append(i)
    return data
