In the years since I wrote this, docker and friends exploited namespaces to create much more complex frameworks than this. A good side effect is that iproute2 learnt to manage namespaces with some very useful commands. Also, a functioning python library to talk to NETLINK was published.

Nemu would get a big performance and reliability improvement from adopting those:

* [Python Netlink library](https://pypi.python.org/pypi/pyroute2)
* [IProute2 namespace management](http://baturin.org/docs/iproute2/#Network%20namespace%20management)

Another requested feature is to isolate the bridge interface from the default namespace, which was not possible a few years ago. I will have to research this again.
