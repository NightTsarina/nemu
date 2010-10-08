#define _GNU_SOURCE 1
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <stdbool.h>
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>

static int get_xfd (void)
{
  char *env = getenv("NETNS_X11_FD");
  if (env == 0)
    {
      return -1;
    }
  return atoi (env);
}

typedef int (*ConnectFunction) (int, const struct sockaddr *,
				socklen_t);

int connect(int sockfd, const struct sockaddr *serv_addr,
	    socklen_t addrlen)
{
  if (serv_addr->sa_family == AF_UNIX)
    {
      const struct sockaddr_un *sun = (const struct sockaddr_un *)serv_addr;
      if (strcmp (sun->sun_path, "/tmp/.X11-unix/X0") == 0)
	{
	  // this is an attempt to connect to the X server.
	  // intercept !
	  int xfd = get_xfd ();
	  fcntl (xfd, F_SETFD, 0);
	  int status = dup2 (xfd, sockfd);
	  status = close (xfd);
	  return 0;
	}
    }
  // lookup the symbol named connect in the next library
  // in the name lookup scope of the dynamic loader
  void *symbol = dlsym (RTLD_NEXT, "connect");
  if (symbol == 0)
    {
      return -1;
    }
  ConnectFunction connect_function = (ConnectFunction) symbol;
  int status = connect_function (sockfd, serv_addr, addrlen);
  
  return status;
}
