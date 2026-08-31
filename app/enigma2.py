import logging
import xml.etree.ElementTree as ET
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

    async def get_text(self, path, params=None):
        async with httpx.AsyncClient(auth=self.auth, timeout=8, follow_redirects=True) as c:
            r = await c.get(self.base + path, params=params)
            r.raise_for_status()
            return r.text

    async def check(self):
        try:
            await self.get_json("/api/statusinfo")
            return True, "OpenWebif API OK"
        except Exception as e:
            try:
                await self.get_json("/api/boxinfo")
                return True, "OpenWebif API OK"
            except Exception:
                pass
            # Older OpenWebif installations commonly expose /web/about.
            try:
                async with httpx.AsyncClient(auth=self.auth, timeout=5) as c:
                    r = await c.get(self.base + "/web/about")
                    r.raise_for_status()
                    return True, "OpenWebif reachable"
            except Exception:
                return False, str(e)

    async def bouquets(self):
        """Bouquet-Liste lesen.

        Dokumentierte OpenWebif-Methoden (OpenWebif API documentation):
          - /api/bouquets?stype=tv  -> JSON
          - /api/getservices        -> JSON (ohne sRef = Bouquet-Liste)
          - /web/bouquets?stype=tv  -> XML
          - /web/getservices        -> XML (ohne sRef = Bouquet-Liste)
        Ein "/ajax/bouquets" existiert in OpenWebif nicht.
        """
        errors = []

        for path, params in [
            ("/api/bouquets", {"stype": "tv"}),
            ("/api/getservices", None),
        ]:
            try:
                data = await self.get_json(path, params)
                return self._normalize_bouquets(data)
            except Exception as e:
                errors.append(f"{path}: {e}")

        for path, params in [
            ("/web/bouquets", {"stype": "tv"}),
            ("/web/getservices", None),
        ]:
            try:
                text = await self.get_text(path, params)
                return self._normalize_bouquets(self._parse_service_xml(text))
            except Exception as e:
                errors.append(f"{path}: {e}")

        raise RuntimeError(
            "Cannot read bouquets from OpenWebif: " + " | ".join(errors)
        )

    def _normalize_bouquets(self, data):
        # /api/getservices bzw. /api/bouquets liefern:
        # {"services": [{"servicereference": "...", "servicename": "..."}, ...]}
        # Manche Forks liefern alternativ {"bouquets": [["ref", "name"], ...]}.
        raw = data
        if isinstance(data, dict):
            for key in ("services", "bouquets", "bouquets_tv", "tv"):
                val = data.get(key)
                if isinstance(val, list):
                    raw = val
                    break
        if isinstance(raw, dict):
            raw = raw.get("bouquets") or raw.get("services") or []
        result = []
        if not isinstance(raw, list):
            return result
        for b in raw:
            ref = name = None
            if isinstance(b, dict):
                ref = (b.get("servicereference") or b.get("serviceref")
                       or b.get("sref") or b.get("reference") or b.get("id"))
                name = (b.get("servicename") or b.get("name")
                        or b.get("title") or ref)
            elif isinstance(b, (list, tuple)):
                if len(b) >= 2:
                    ref, name = b[0], b[1]
                elif b:
                    ref = name = b[0]
            if ref:
                result.append({
                    "ref": str(ref),
                    "name": str(name) if name else str(ref),
                })
        return result

    def _parse_service_xml(self, text):
        # /web/bouquets und /web/getservices liefern:
        # <e2servicelist>
        #   <e2service>
        #     <e2servicereference>1:7:1:...</e2servicereference>
        #     <e2servicename>Favourites</e2servicename>
        #   </e2service>
        # </e2servicelist>
        root = ET.fromstring(text)
        result = []
        for svc in root.iter("e2service"):
            ref_el = svc.find("e2servicereference")
            name_el = svc.find("e2servicename")
            ref = (ref_el.text or "").strip() if ref_el is not None else ""
            name = (name_el.text or "").strip() if name_el is not None else ""
            if ref:
                result.append({"ref": ref, "name": name or ref})
        return result

    async def channels(self, bouquet_ref):
        """Sender eines Bouquets lesen.

        Korrekt ist getservices mit Parameter sRef:
          - /api/getservices?sRef=<bouquet ref>  -> JSON
          - /web/getservices?sRef=<bouquet ref>  -> XML
        """
        errors = []

        try:
            data = await self.get_json("/api/getservices", {"sRef": bouquet_ref})
            return self._normalize_channels(data)
        except Exception as e:
            errors.append(f"/api/getservices: {e}")

        try:
            text = await self.get_text("/web/getservices", {"sRef": bouquet_ref})
            return self._normalize_channels(self._parse_service_xml(text))
        except Exception as e:
            errors.append(f"/web/getservices: {e}")

        raise RuntimeError(
            "Cannot read channels from OpenWebif: " + " | ".join(errors)
        )

    def _normalize_channels(self, data):
        raw = data
        if isinstance(data, dict):
            for key in ("services", "channels"):
                val = data.get(key)
                if isinstance(val, list):
                    raw = val
                    break
        if isinstance(raw, dict):
            raw = raw.get("channels") or raw.get("services") or []
        result = []
        if not isinstance(raw, list):
            return result
        for ch in raw:
            ref = name = None
            if isinstance(ch, dict):
                ref = (ch.get("servicereference") or ch.get("serviceref")
                       or ch.get("sref") or ch.get("reference") or ch.get("id"))
                name = (ch.get("servicename") or ch.get("name")
                        or ch.get("title") or ref)
            elif isinstance(ch, (list, tuple)):
                if len(ch) >= 2:
                    ref, name = ch[0], ch[1]
                elif ch:
                    ref = name = ch[0]
            if ref:
                result.append({
                    "ref": str(ref),
                    "name": str(name) if name else str(ref),
                })
        return self._filter_markers(result)

    def _filter_markers(self, services):
        # 1:64:... = Bouquet-Marker (Trennzeilen, nicht abspielbar)
        # 1:7:...  = eingebettete (Sub-)Bouquets statt Sender
        return [
            s for s in services
            if not s["ref"].startswith(("1:64:", "1:7:"))
        ]

    def stream_url(self, service_ref):
        # OpenWebif/enigma2 uses URL-encoded service references on port 8001.
        encoded = quote(service_ref, safe="")
        host = self.base.split("://", 1)[1].split(":", 1)[0]
        userinfo = ""
        if self.auth:
            # Port 8001 nutzt dieselbe HTTP-Basic-Auth wie OpenWebif.
            userinfo = (
                quote(self.auth[0], safe="") + ":"
                + quote(self.auth[1], safe="") + "@"
            )
        return f"http://{userinfo}{host}:8001/{encoded}"
