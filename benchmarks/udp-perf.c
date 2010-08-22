/* vim: ts=4:sw=4:et:ai:sts=4
 */
#include <sys/timerfd.h>
#include <time.h>
#include <sys/time.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <sys/socket.h>
#include <stdint.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>

#define HDR_SIZE (14 + 20 + 8) /* eth + ip + udp headers */
static uint64_t current_time(void);

static void fatal(const char *func, const char *detailed) {
    char *error;
    if(detailed)
        fprintf(stderr, "%s\n", detailed);
    if(func) {
        error = strerror(errno);
        fprintf(stderr, "%s: %s (%d)\n", func, error, errno);
    }
    exit(1);
}
static void set_txbuf_size(int fd, int buffer_size) {
    int msg_size = buffer_size;
    int status = setsockopt(fd, SOL_SOCKET, SO_SNDBUF, (char*)&msg_size,
            sizeof(msg_size));
    if(status == -1)
        fatal("setsockopt", "Unable to set socket buffer size");
}

static void run_client(const char *to_ip, unsigned to_port, unsigned pkt_size) {
    int status, fd, cfd;
    uint64_t seq;
    struct sockaddr_in addr, to;
    void *buffer;

    if(pkt_size < HDR_SIZE)
        fatal(NULL, "Cannot send packets that small.");
    pkt_size -= HDR_SIZE;

    buffer = malloc(pkt_size);
    if(! buffer)
        fatal("malloc", NULL);
    memset(buffer, 0, pkt_size);

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(fd == -1)
        fatal("socket", "Unable to create udp socket");

    cfd = socket(AF_INET, SOCK_STREAM, 0);
    if(cfd == -1)
        fatal("socket", "Unable to create tcp socket");

#if 0
    status = fcntl(fd, F_GETFL, 0);
    if(status == -1)
        fatal("fcntl", NULL);

    status = fcntl(fd, F_SETFL, status | O_NONBLOCK);
    if(status == -1)
        fatal("fcntl", NULL);

    set_txbuf_size(fd, 1<<20);
#endif

    addr.sin_family = AF_INET;
    addr.sin_port = 0;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    to.sin_family = AF_INET;
    to.sin_port = htons(to_port);
    to.sin_addr.s_addr = inet_addr(to_ip);

    status = bind(fd, (struct sockaddr*)&addr, sizeof(addr));
    if(status == -1)
        fatal("bind", NULL);

    status = connect(cfd, (struct sockaddr*)&to, sizeof(to));
    if(status == -1)
        fatal("connect", "Can not connect to server");

    for(seq = 0; ; seq++) {
        ssize_t written;
        uint64_t now;
        fd_set rfds;
        struct timeval tv;

        /* Check if asked to stop */
        FD_ZERO(&rfds);
        FD_SET(cfd, &rfds);
        tv.tv_sec = 0;
        tv.tv_usec = 0;
        status = select(cfd + 1, &rfds, NULL, NULL, &tv);
        if(status == -1)
            fatal("select", NULL);

        if(status) {
            status = recv(cfd, buffer, 8, 0);
            if(status == -1)
                fatal("recv", NULL);
            if(((uint64_t *)buffer)[0] == 0xdeadbeef)
                break;
            fatal(NULL, "Received invalid control message");
        }

        now = current_time();
        if(pkt_size >= sizeof(uint64_t))
            ((uint64_t *)buffer)[0] = now;
        if(pkt_size >= 2 * sizeof(uint64_t))
            ((uint64_t *)buffer)[1] = seq;

        written = sendto(fd, buffer, pkt_size, 0, (struct sockaddr *)&to,
                sizeof(to));
        if(written == -1 && (errno == EWOULDBLOCK || errno == EAGAIN))
            continue;
        if(written == -1)
            fatal("sendto", NULL);
    }
    free(buffer);
    status = close(cfd);
    if(status == -1)
        fatal("close", "Unable to close socket");
    status = close(fd);
    if(status == -1)
        fatal("close", "Unable to close socket");
}

static uint64_t current_time(void) {
    struct timeval tv;
    uint64_t current_time;
    int status;
    
    status = gettimeofday(&tv, 0);
    if(status == -1)
        fatal("gettimeofday", "Unable to get current time\n");
    current_time = tv.tv_sec * 1000000 + tv.tv_usec;
    return current_time;
}

static void run_server(int port, uint64_t max_time, uint64_t max_pkts,
        uint64_t max_bytes, bool verbose) {
    struct sockaddr_in addr;
    int fd, cfd, serverfd, status;
    uint64_t now, last_ts, last_seq, preceived, breceived, errors;
    uint64_t start, tot_delay, max_delay, min_delay, last_delay;
    double jitter = 0.0L;
    ssize_t pkt_size = -1, buffer_sz = 1 << 17; /* should be enough */
    void *buffer;
    uint64_t magic = 0xdeadbeef;

    buffer = malloc(buffer_sz);
    if(! buffer)
        fatal("malloc", NULL);

    fd = socket(AF_INET, SOCK_DGRAM, 0);
    if(fd == -1)
        fatal("socket", "Unable to create udp socket");

    serverfd = socket(AF_INET, SOCK_STREAM, 0);
    if(serverfd == -1)
        fatal("socket", "Unable to create tcp socket");

    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    status = bind(fd,(struct sockaddr*)&addr, sizeof(addr));
    if(status == -1)
        fatal("bind", "Unable to bind to specified port");

    status = 1; /* no need for other var :) */
    status = setsockopt(serverfd, SOL_SOCKET, SO_REUSEADDR, &status,
            sizeof(status));
    if(status == -1)
        fatal("setsockopt", "Unable to set SO_REUSEADDR");

    status = bind(serverfd,(struct sockaddr*)&addr, sizeof(addr));
    if(status == -1)
        fatal("bind", "Unable to bind to specified port");

    status = listen(serverfd, 1);
    if(status == -1)
        fatal("listen", "Unable to receive connections");

    cfd = accept(serverfd, NULL, 0);
    if(cfd == -1)
        fatal("accept", "Unable to receive connection");

    preceived = breceived = errors = 0;
    last_ts = last_seq = start = 0;
    tot_delay = max_delay = 0; last_delay = min_delay = -1;
    while(true) {
        uint64_t ts = 0, seq = 0;
        ssize_t received;

        received = recvfrom(fd, buffer, buffer_sz, 0, 0, 0);
        now = current_time();

        if(received >= sizeof(uint64_t))
            ts = ((uint64_t *)buffer)[0];
        if(received >= 2 * sizeof(uint64_t))
            seq = ((uint64_t *)buffer)[1];

        if(pkt_size == -1) {
            /* init: first packet is ignored */
            pkt_size = received;
            last_ts = ts;
            last_seq = seq;
            start = now;
        } else {
            if(pkt_size != received) {
                errors++;
                fprintf(stderr, "Received packet of invalid size %ld.\n",
                        received);
            } else {
                preceived++;
                breceived += received;
                breceived += HDR_SIZE;
                if(ts) {
                    if(last_delay >= 0) {
                        double delta;
                        if(last_delay > now - ts)
                            delta = last_delay - (now - ts);
                        else
                            delta = (now - ts) - last_delay;
                        jitter += (delta - jitter) / 16.0;
                    }
                    last_delay = now - ts;
                    tot_delay += last_delay;
                    if(last_delay < min_delay)
                        min_delay = last_delay;
                    if(last_delay > max_delay)
                        max_delay = last_delay;
                }
                if((ts && ts <= last_ts) || (seq && seq <= last_seq)) {
                    errors++;
                    fprintf(stderr, "Packet received out of order.\n");
                }
                last_ts = ts;
                last_seq = seq;
            }
            if((max_pkts && preceived + errors >= max_pkts) ||
                    (max_time && now - start >= max_time) ||
                    (max_bytes && breceived >= max_bytes))
                break;
        }
    }
    free(buffer);

    /* Tell client to die */
    send(cfd, &magic, sizeof(magic), 0);
    status = close(cfd);
    if(status == -1)
        fatal("close", "Unable to close socket");
    status = close(serverfd);
    if(status == -1)
        fatal("close", "Unable to close socket");

    if(verbose) {
        printf("Received: %ld bytes %ld packets (size %ld/%ld) %ld errors.\n",
                breceived, preceived, pkt_size + HDR_SIZE, pkt_size, errors);
        printf("Delay: %ld/%ld/%ld (min/avg/max). Jitter: %lf. Time: %ld us\n",
                min_delay, tot_delay / preceived, max_delay, jitter,
                now - start);
        printf("Bandwidth: %ld bit/s.\n",
                (long)(1.0L * (breceived * 8000000) / (now - start)));
    } else {
        printf("brx:%ld prx:%ld pksz:%ld plsz:%ld err:%ld ",
                breceived, preceived, pkt_size + HDR_SIZE, pkt_size, errors);
        printf("mind:%ld avgd:%ld maxd:%ld jit:%lf time:%ld ",
                min_delay, tot_delay / preceived, max_delay, jitter,
                now - start);
    }

    status = close(fd);
    if(status == -1)
        fatal("close", "Unable to close socket");
}
#define CHECK_INT_ARG(arg, name, value)                         \
    if(strncmp(arg, "--"name"=", strlen("--"name"=")) == 0) {   \
        value = atoi(arg + strlen("--"name"="));                \
        continue;                                               \
    }
#define CHECK_LLINT_ARG(arg, name, value)                       \
    if(strncmp(arg, "--"name"=", strlen("--"name"=")) == 0) {   \
        value = atoll(arg + strlen("--"name"="));               \
        continue;                                               \
    }
#define CHECK_STR_ARG(arg, name, value)                         \
    if(strncmp(arg, "--"name"=", strlen("--"name"=")) == 0) {   \
        value = arg + strlen("--"name"=");                      \
        continue;                                               \
    }

static char *progname;
void usage(FILE *f) {
    char *filler, *sp = "                    ";
    if(strlen(progname) < strlen(sp))
        filler = sp + strlen(sp) - strlen(progname);
    else
        filler = sp;

    fprintf(f, "\n");
    fprintf(f, "Usage: %s --client [--host=HOST] [--port=PORT] "
            "[--pktsize=BYTES]\n", progname);
    fprintf(f, "       %s --server [--port=PORT] [--max-time=SECS] "
            "[--max-pkts=NUM]\n", progname);
    fprintf(f, "       %s          [--max-bytes=BYTES] [--verbose]\n", filler);
}

int main(int argc, char *argv[]) {
    uint64_t max_time = 0, max_pkts = 0, max_bytes = 0;
    int pkt_size = 1500, port = 5000;
    const char *to_ip = "127.0.0.1";
    bool server = false, client = false, verbose = false;
    char **arg = argv + 1;

    progname = strrchr(argv[0], '/');
    if(progname)
        progname++; /* skip over the slash */
    else
        progname = argv[0];

    for(; *arg != 0; arg++)
    {
        CHECK_INT_ARG(*arg, "pktsize", pkt_size);
        CHECK_INT_ARG(*arg, "port", port);
        CHECK_LLINT_ARG(*arg, "max-time", max_time);
        CHECK_LLINT_ARG(*arg, "max-pkts", max_pkts);
        CHECK_LLINT_ARG(*arg, "max-bytes", max_bytes);
        CHECK_STR_ARG(*arg, "host", to_ip);
        if(strcmp(*arg, "--server") == 0) {
            server = true;
            continue;
        }
        if(strcmp(*arg, "--client") == 0) {
            client = true;
            continue;
        }
        if(strcmp(*arg, "--verbose") == 0) {
            verbose = true;
            continue;
        }
        if(strcmp(*arg, "--help") == 0) {
            usage(stdout);
            exit(0);
        }
        fprintf(stderr, "Unknown parameter: %s\n", *arg);
        usage(stderr);
        exit(1);
    }
    if(client == server) {
        fprintf(stderr,
                "Exactly one of --client and --server must be specified.\n");
        usage(stderr);
        exit(1);
    }
    if(!(max_time || max_pkts || max_bytes))
        max_time = 10;
    max_time *= 1000000;
    if(client)
        run_client(to_ip, port, pkt_size);
    else
        run_server(port, max_time, max_pkts, max_bytes, verbose);
    return 0;
}
