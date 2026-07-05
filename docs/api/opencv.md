# OpenCV

`ws://127.0.0.1:8000/ws/opencv`

Image sharpening service. The client uploads an image once (keyed by its URL), then can request unsharp-mask sharpening of that cached image; the sharpened result is returned as a PNG binary frame.

- **Handler**: `fluxghost/api/opencv.py` (`opencv_mixin`), wrapper `fluxghost/websocket/opencv.py`, route `fluxghost/http_websocket_route.py:29` - **Beam Studio client**: `packages/core/src/web/helpers/api/open-cv.ts` (`OpenCVWebSocket`, used by the Sharpen dialog `app/components/dialogs/image/Sharpen.tsx`)

## Connection

No URL parameters. Commands are plain-text frames `<cmd> <params...>` dispatched via `cmd_mapping` (`fluxghost/api/opencv.py:19-22`, `fluxghost/api/misc.py:29-56`). The connection holds per-session state: `self.imgs`, a dict mapping the client-supplied URL string to the decoded OpenCV image, plus an access-order history deque (`fluxghost/api/opencv.py:23-31`). State is lost when the socket closes.

## Commands

### `upload <img_url> <file_length>`

Uploads an image and caches it under `img_url` (`fluxghost/api/opencv.py:33-48`). `img_url` is an opaque key — the server never fetches it; the client sends the actual bytes. The image is decoded with PIL and converted `RGBA → BGRA` (`cv2.COLOR_RGBA2BGRA`), so it should have an alpha channel (Beam Studio uploads the blob fetched from an object URL).

```
→ upload blob:file:///1234-abcd 152833
← {"status": "continue"}
→ <binary chunks totalling 152833 bytes>
← {"status": "ok"}
```

Binary upload follows the standard `BinaryUploadHelper` flow (`fluxghost/api/misc.py:59-89`): stream binary frames until exactly `file_length` bytes have arrived.

### `sharpen <img_url> <sharpness> <radius>`

Applies an unsharp mask to the previously uploaded image (`fluxghost/api/opencv.py:50-65`). `sharpness` is parsed as float, `radius` as int. Implementation: Gaussian blur with kernel size `2 * radius + 1`, then `cv2.addWeighted(img, 1 + sharpness, blur, -sharpness, 0)`. The result is PNG-encoded and sent as a **single raw binary frame** with no preceding JSON header.

```
→ sharpen blob:file:///1234-abcd 3.5 2
← <binary frame: PNG bytes>
```

If `img_url` has not been uploaded on this connection:

```
→ sharpen blob:file:///1234-abcd 3.5 2
← {"status": "need_upload"}
```

The Beam Studio client reacts to `need_upload` by fetching the URL, running `upload`, and re-sending the same `sharpen` command (`open-cv.ts:82-112`).

## Errors

- Unknown command, or non-numeric `sharpness`/`radius`/`file_length` (`ValueError`) → `{"status": "Error", "message": "BAD_PARAM_TYPE"}` — capitalized `Error` (`fluxghost/api/misc.py:50-52`).
- Text frame during an active upload → `{"status": "fatal", "symbol": ["PROTOCOL_ERROR"], "error": "PROTOCOL_ERROR"}` (`fluxghost/api/misc.py:48`).
- Binary frame with no upload in progress → fatal `BAD_PROTOCOL`; more bytes than declared → fatal `BAD_LENGTH...` (`fluxghost/api/misc.py:17-27`, `86-89`).
- `sharpen` on an unknown key is not an error — it returns `{"status": "need_upload"}` as shown above.
- There is no try/except around image decoding or sharpening; a corrupt upload raises an uncaught exception in the handler instead of producing an error frame.

## Example Session

```
→ sharpen blob:file:///1234-abcd 3.5 2
← {"status": "need_upload"}
→ upload blob:file:///1234-abcd 152833
← {"status": "continue"}
→ <binary: 152833 bytes of PNG>
← {"status": "ok"}
→ sharpen blob:file:///1234-abcd 3.5 2
← <binary frame: sharpened PNG>
→ sharpen blob:file:///1234-abcd 5.0 4
← <binary frame: sharpened PNG>
```

## Notes

- Because the source image stays cached, the Sharpen dialog can re-run `sharpen` with different parameters cheaply after the first upload.
- `update_history` (`fluxghost/api/opencv.py:26-31`) keeps a most-recently-used deque capped at 5 entries, but only the deque is trimmed — evicted URLs are **not** deleted from `self.imgs`, so decoded images accumulate for the lifetime of the connection.
- `sharpness` and `radius` are not range-checked. `radius` values ≥ 0 yield valid odd kernel sizes; the client UI is responsible for sensible bounds.
- The binary response is a bare `send_binary` (`fluxghost/api/opencv.py:65`) — unlike `ApiBase.send_binary_buffer` there is no `{"status": "binary", ...}` preamble. The frontend simply resolves the first Blob it receives.
