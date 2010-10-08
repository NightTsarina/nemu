CFLAGS+=-fpic
LDFLAGS+=-ldl
all: libconnectwrapper.so
libconnectwrapper.so: connect.o
	$(CC) $(LDFLAGS) -shared -o $@ $^
connect.o: connect.c

clean:
	rm -f *.o 2>/dev/null