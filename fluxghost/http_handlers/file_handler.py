
from mimetypes import types_map as MIME_TYPE
import logging
import select
import time
import os
import re

logger = logging.getLogger(__name__)

from sendfile import sendfile


MIME_TYPE.update({
    ".css": "text/css",
    ".htm": "text/html",
    ".html": "text/html",
    ".ico": "image/x-icon",
    ".js": "application/x-javascript",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".txt": "text/plain"
})

BUF_SIZE = 65536


class FileHandler(object):
    def __init__(self, basedir):
        self.basedir = os.path.abspath(basedir)

    def clean_path(self, path):
        # Remove ? or # in url
        rmatch = re.search("(\#|\?)", path)
        if rmatch:
            path = path[:rmatch.start()]
        return os.path.join(self.basedir, path)

    def url_check(self, path):
        # Check path is safe or not
        return path == os.path.abspath(path)

    def get_mime(self, extname):
        return MIME_TYPE.get(extname, "binary")

    def handle_request(self, handler, path):
        path = self.clean_path(path)

        if not self.url_check(path):
            handler.response_403(body="BAD PATH")
        elif not os.path.isfile(path):
            handler.response_404()
        else:
            self.make_response(handler, path)

    def get_last_modify(self, filepath):
        return time.strftime("%a, %d %b %Y %H:%M:%S %Z",
                             time.gmtime(os.stat(filepath).st_mtime))

    def make_response(self, handler, filepath):
        length = os.path.getsize(filepath)

        req_range = handler.headers.get("Range", None)
        start, until = self.proc_range_request(handler, length, req_range)

        fileName, fileExtension = os.path.splitext(filepath)

        handler.send_header('Content-Type', self.get_mime(fileExtension))
        handler.send_header('Content-Length', length - start)
        handler.send_header('Last-Modified', self.get_last_modify(filepath))

        if not handler.close_connection:
            handler.send_header('Connection', 'Keep-Alive')

        handler.end_headers()
        handler.wfile.flush()

        offset = start

        with open(filepath, "r") as f:
            fd_from, fd_dist = f.fileno(), handler.wfile.fileno()

            while (length - f.tell()) > BUF_SIZE:
                select.select((), (fd_dist, ), ())
                if sendfile(fd_dist, fd_from, offset, BUF_SIZE) == 0:
                    logging.debug("Fuck you google chrome go to hell")
                    return

            # Last chunk
            sendfile(fd_dist, fd_from, offset, length - f.tell())

    def proc_range_request(self, handler, file_length, request_range):
        if request_range:
            _s, _u = request_range.split("=")[1].split("-")
            start = int(_s == "" and "0" or _s)
            until = int(_u == "" and file_length or _u)
            until = until

            handler.send_response(206, 'OK')
            handler.send_header('Content-Range',
                                "bytes %i-%i/%i" % (start, until - 1,
                                                    file_length))
            handler.send_header('Accept-Ranges', 'bytes')

            return start, until
        else:
            handler.send_response(200, 'OK')
            handler.send_header('Content-Range', "%i" % (file_length, ))

            return 0, file_length
