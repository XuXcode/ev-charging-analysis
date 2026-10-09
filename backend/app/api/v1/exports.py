"""Short-lived, bounded attachment transport; never recomputes analysis."""

import hashlib
import time
import uuid
from threading import Lock
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.schemas.common import APIResponse

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_POOL_BYTES = 32 * 1024 * 1024
TTL_SECONDS = 300
router = APIRouter(prefix="/api/v1/exports", tags=["图表附件"])


class AttachmentPool:
    def __init__(self):
        self.items = {}
        self.lock = Lock()

    def put(self, filename, data):
        with self.lock:
            now = time.monotonic()
            self.items = {key: item for key, item in self.items.items() if item["expires"] > now}
            if sum(len(item["data"]) for item in self.items.values()) + len(data) > MAX_POOL_BYTES:
                raise HTTPException(503, "附件缓存暂满，请稍后重试或使用本地下载")
            token = uuid.uuid4().hex
            self.items[token] = {
                "filename": filename,
                "data": data,
                "hash": hashlib.sha256(data).hexdigest(),
                "expires": now + TTL_SECONDS,
            }
            return token, self.items[token]["hash"]

    def get(self, token):
        with self.lock:
            item = self.items.get(token)
            if item is None or item["expires"] <= time.monotonic():
                self.items.pop(token, None)
                raise HTTPException(404, "附件已过期，请重新导出")
            return item


@router.post("", response_model=APIResponse[dict])
async def prepare(request: Request, filename: str = Query(..., min_length=1, max_length=160)):
    if any(c in filename for c in "/\\:\r\n") or not filename.lower().endswith((".csv", ".png")):
        raise HTTPException(422, "仅接受无路径的CSV或PNG文件名")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_FILE_BYTES:
            raise HTTPException(413, "附件不得超过8MiB")
        data.extend(chunk)
    if not data:
        raise HTTPException(422, "附件不能为空")
    if filename.lower().endswith(".png"):
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(422, "PNG文件签名不匹配")
    else:
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(422, "CSV须为UTF-8编码") from None
    token, digest = request.app.state.attachment_pool.put(filename, bytes(data))
    return APIResponse(
        data={
            "id": token,
            "sha256": digest,
            "expiresInSeconds": TTL_SECONDS,
            "notice": "原文件字节短时转存，不修改指标；服务重启后需重新导出。",
        }
    )


@router.get("/{token}", response_class=Response)
def attachment(
    request: Request, token: str, expected_hash: str = Query(..., pattern=r"^[a-f0-9]{64}$")
):
    item = request.app.state.attachment_pool.get(token)
    if item["hash"] != expected_hash:
        raise HTTPException(409, "附件内容哈希不匹配")
    media_type = "image/png" if item["filename"].lower().endswith(".png") else "text/csv"
    return Response(
        content=item["data"],
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename=chart-export; filename*=UTF-8''"
            + quote(item["filename"], safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "X-Content-SHA256": item["hash"],
        },
    )
