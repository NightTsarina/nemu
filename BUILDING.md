# How to build nemu

## Dependencies

  * python-unshare (http://pypi.python.org/pypi/python-unshare)
  * python-passfd (http://pypi.python.org/pypi/python-passfd)
  * linux-kernel >= 2.6.35
  * bridge-utils
  * iproute
  * procps
  * xauth (Needed only for X11 forwarding support)

## Details

Once the dependencies are installed, run:

    $ make
    $ sudo make test # optional
    $ sudo make install
