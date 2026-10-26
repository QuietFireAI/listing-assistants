#!/usr/bin/env python3
"""desk_door - lets your browser reach the Broker Desk while the dispatcher
stays on a network with no way out (agent isolation V1, 2026-10-26).

The dispatcher container is on a closed network (no internet). This door
container sits on that network and on a normal one, and does one thing:
passes bytes between your browser and the Desk's port. It holds no
records, no key and no settings, and compose publishes it on this
computer's own address only (127.0.0.1), so other machines cannot reach it.

    python tools/desk_door.py <dispatcher host> <port>
"""
import socket
import sys
import threading


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python tools/desk_door.py <dispatcher host> <port>", file=sys.stderr)
        return 2
    host, port = argv[0], int(argv[1])
    server = socket.create_server(("0.0.0.0", port))
    print(f"desk door: :{port} -> {host}:{port}", flush=True)
    while True:
        client, _ = server.accept()
        try:
            upstream = socket.create_connection((host, port), timeout=10)
            upstream.settimeout(None)
        except OSError:
            client.close()
            continue
        threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
