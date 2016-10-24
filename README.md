nemu
====

Nemu (Netwok EMUlator) is a small Python library to create emulated networks
and run and test programs in them.

Different programs, or copies of the same program, can run in different
emulated nodes, using only the emulated network to communicate, without ever
noticing they all run in the same computer.

Nemu provides a very simple interface to create nodes, connect them arbitrarily
with virtual interfaces, configure IPv4 and IPv6 addresses and routes, and
start programs in the nodes. The virtual interfaces also support emulation of
delays, loss, and reordering of packets, and bandwidth limitations.

You can even start interactive sessions by opening xterms on different nodes,
Nemu has special support for forwarding X sessions to the emulated nodes.

More advanced configurations, like setting up netfilter (iptables) rules,
starting VPN tunnels, routing daemons, etc, are simply supported by executing
the appropriate commands in the emulated nodes, exactly as if they were
executed in real machines in a real network.

All this is achieved with very small overhead, thanks to the Linux kernel's
[network name spaces][] capabilities, part of the bigger [Linux containers][]
project.

To get a feeling of what you can do with Nemu, take a peek at this [sample
script](examples/sample.py) that creates 3 interconnected nodes, runs some
tests and then starts xterms running tcpdump so you can see the packets flowing
from one node to the other.

Nemu was started as a research project at [INRIA][] (Institut de Recheche en
Informatique et Automatique, a French research institution) and now it is
developed jointly by INRIA staff and external developers.


Nemu is now part of [Debian][]! You can just `apt-get install python-nemu` and
start using it.

[network name spaces]: http://lxc.sourceforge.net/index.php/about/kernel-namespaces/network/
[Linux containers]: http://lxc.sourceforge.net/
[INRIA]: http://www.inria.fr/en/
[Debian]: http://packages.qa.debian.org/p/python-nemu.html
