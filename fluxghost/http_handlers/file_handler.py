
from mimetypes import types_map as MIME_TYPE  # noqa
import platform
import logging
import select
import time
import os
import re
from io import BytesIO
logger = logging.getLogger(__name__)


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


if platform.platform().startswith("Windows"):
    def get_last_modify(filepath):
        return time.strftime("%a, %d %b %Y %H:%M:%S UTC",
                             time.gmtime(os.path.getmtime(filepath)))
else:
    def get_last_modify(filepath):
        return time.strftime("%a, %d %b %Y %H:%M:%S %Z",
                             time.gmtime(os.stat(filepath).st_mtime))


BUF_SIZE = 65536

file_caches = {"none": "none"}

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
        return os.path.abspath(path).startswith(self.basedir)

    def get_mime(self, extname):
        return MIME_TYPE.get(extname, "binary")

    def handle_request(self, handler, path):
        path = self.clean_path(path)

        try:
            if not self.url_check(path):
                handler.response_403(body="BAD PATH")
            elif not os.path.isfile(path):
                handler.response_404()
            else:
                self.make_response(handler, path)
        except BrokenPipeError as e:
            logger.debug("Error: %s", e)

    def make_response(self, handler, filepath):
        length = os.path.getsize(filepath)

        req_range = handler.headers.get("Range", None)
        start, until = self.proc_range_request(handler, length, req_range)

        fileName, fileExtension = os.path.splitext(filepath)

        handler.send_header('Content-Type', self.get_mime(fileExtension))
        handler.send_header('Content-Length', length - start)
        handler.send_header('Last-Modified', get_last_modify(filepath))

        if not handler.close_connection:
            handler.send_header('Connection', 'Keep-Alive')

        handler.end_headers()
        handler.wfile.flush()
        file_cache = BytesIO()
        do_cache = True if length < 1024000 else False
        if filepath in file_caches:
            f = file_caches[filepath]
            do_cache = False
            print("Cached ", filepath)
        with open(filepath, "rb") as f:
            buf = bytearray(16384)
            mv = memoryview(buf)
            fd_dist = handler.wfile.fileno()

            while True:
                l = f.readinto(mv)
                if l:
                    sent = 0
                    while sent != l:
                        select.select((), (fd_dist, ), ())
                        sent += handler.wfile.write(mv[sent:l])
                        if do_cache:
                            file_cache.write(mv[sent:l])
                else:
                    break
            
            if do_cache:
                print("Caching ", filepath)
                file_caches[filepath] = file_cache

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
