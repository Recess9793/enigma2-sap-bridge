import base64
import logging
from urllib.parse import quote
import httpx

log = logging.getLogger("enigma2")

class Enigma2Client:
    def __init__(self, host, port, user="", password=""):
        self.base = f"http://{host}:{port}"
        self.auth = (user, password) if user else None

    async def get_json(self, path, params=None):
        async with httpx.AsyncClient(auth=self.auth, timeout=8, follow_redirects=True) as c:
            r = await c.get(self.base + path, params=params)
            r.raise_for_status()
            return r.json()

    async def check(self):
        try:
            await self.get_json("/api/boxinfo")
            return True, "OpenWebif API OK"
        except Exception as e:
            # Older OpenWebif installations commonly expose /web/about.
            try:
                async with httpx.AsyncClient(auth=self.auth, timeout=5) as c:
                    r = await c.get(self.base + "/web/about")
                    r.raise_for_status()
                return True, "OpenWebif reachable"
            except Exception:
                return False, str(e)

    async def bouquets(self):
        # OpenWebif's AJAX API exposes bouquet lists. Different OpenWebif
        # generations return slightly different JSON shapes, so normalize here.
        candidates = [
            ("/ajax/bouquets", {"stype": "tv"}),
            ("/api/bouquets", {"stype": "tv"}),
        ]
        last = None
        for path, params in candidates:
            try:
                data = await self.get_json(path, params)
                return self._normalize_bouquets(data)
            except Exception as e:
                last = e
        raise RuntimeError(f"Cannot read bouquets from OpenWebif: {last}")

    def _normalize_bouquets(self, data):
        raw = data
        if isinstance(data, dict):
            for key in ("bouquets", "bouquets_tv", "tv", "result"):
                if key in data:
                    raw = data[key]
                    break
        result = []
        if isinstance(raw, dict):
            raw = raw.get("bouquets", [])
        if not isinstance(raw, list):
            return result
        for b in raw:
            if not isinstance(b, dict):
                continue
            ref = b.get("serviceref") or b.get("sref") or b.get("reference") or b.get("id")
            name = b.get("servicename") or b.get("name") or b.get("title") or ref
            if ref:
                result.append({"ref": str(ref), "name": str(name)})
        return result

    async def channels(self, bouquet_ref):
        data = await self.get_json("/ajax/channels", {
            "id": bouquet_ref,
            "stype": "tv",
        })
        return self._normalize_channels(data, bouquet_ref)

    def _normalize_channels(self, data, bouquet_ref):
        raw = data
        if isinstance(data, dict):
            for key in ("channels", "services", "result"):
                if key in data:
                    raw = data[key]
                    break
        if isinstance(raw, dict):
            raw = raw.get("channels") or raw.get("services") or []
        result = []
        if not isinstance(raw, list):
            return result
        for ch in raw:
            if not isinstance(ch, dict):
                continue
            ref = ch.get("sref") or ch.get("serviceref") or ch.get("reference") or ch.get("id")
            name = ch.get("name") or ch.get("servicename") or ch.get("title") or ref
            if ref:
                result.append({"ref": str(ref), "name": str(name)})
        return result

    def stream_url(self, service_ref):
        # OpenWebif/enigma2 uses URL-encoded service references on port 8001.
        encoded = quote(service_ref, safe="")
        return f"http://{self.base.split('://',1)[1].split(':')[0]}:8001/{encoded}"
