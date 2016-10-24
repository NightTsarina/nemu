# Support for X11 forwarding in Nemu

## Introduction

Nemu has special support for forwarding X11 sessions, so interactive programs can be run from inside virtual nodes.

When running in a different network namespace (a virtual node), UNIX domain sockets cannot be used to communicate to the main namespace, or with other namespaces. Because of this, the usual way to start X11 applications does not work.

Furthermore, as the network topology is constructed by the user, and can be completely arbitrary, in general there is no guarantee that normal X11-over-TCP would work either!

To solve this problem, Nemu starts a separate process per virtual node that will forward TCP connections inside the node to the local X11 UNIX domain or TCP socket, in a very similar way to what SSH does to forward X11 connections. A nice UNIX trick is used to pass the listening socket to the virtual node while keeping the other end in the "normal" main namespace (see http://pypi.python.org/pypi/python-passfd).

## Troubleshooting

To enable this feature, create your `nemu.Node` object with the optional argument `forward_X11` set to `True`.

Note that when switching to root to run your Nemu scripts, it could happen that the X11 libraries are not able to obtain the proper credentials to connect to your display:

    $ sudo xeyes
    Error: Can't open display: localhost:11.0

This is usually seen when using forwarded X11 connections through SSH, as it does not set the `XAUTHORITY` variable, and the libraries take the default value, which is different for you and for the root user.

As a simple workaround, you can set the `XAUTHORITY` variable to the full path of your xauth file (sudo keeps `XAUTHORITY` unchanged):

    $ XAUTHORITY=${HOME}/.Xauthority sudo xeyes

This will not work in most NFS-mounted home directories, you will need to copy the xauth file out of NFS first:

    $ cp ${HOME}/.Xauthority /tmp/${USER}-Xauthority
    $ export XAUTHORITY=/tmp/${USER}-Xauthority
    $ sudo xeyes
