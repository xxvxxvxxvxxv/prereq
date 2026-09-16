#!/usr/bin/env python3
"""Run the local app: python3 start.py. No package installation required."""
import argparse
import logging
import os
import threading
import webbrowser
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server,WSGIServer,WSGIRequestHandler

class Server(ThreadingMixIn,WSGIServer):
    daemon_threads=True
class Handler(WSGIRequestHandler):
    def log_message(self,format,*args):
        pass  # Do not persist course searches or request queries.

def main():
    parser=argparse.ArgumentParser(description='Prereq · Sabancı course map')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--offline',action='store_true',help='Use only bundled/cached data; make no upstream requests')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if args.offline:
        os.environ['PREREQ_OFFLINE']='1'
    from prereq.app import App
    app=App()
    logging.basicConfig(level=logging.WARNING,format='%(levelname)s: %(message)s')
    try:
        server=make_server('127.0.0.1',args.port,app,server_class=Server,handler_class=Handler)
    except OSError as exc:
        parser.exit(1,f'Could not start: {exc}\nTry python3 start.py --port 8766\n')
    url=f'http://127.0.0.1:{args.port}'
    print(f'\n  PREREQ  /  Sabancı course map\n  {url}\n  {"Offline snapshots only" if args.offline else "Live catalog refresh enabled"}\n  Press Ctrl+C to stop.\n',flush=True)
    if not args.no_browser:
        threading.Timer(0.5,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close(); app.service.close()

if __name__=='__main__':
    main()
