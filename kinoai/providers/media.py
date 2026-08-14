"""Media provayderlar: rasm va video generatsiya.

Provider-agnostic qoida saqlanadi — biznes logikada provayder nomi yo'q.
Model ID lar ENV orqali beriladi, chunki ular tez-tez o'zgaradi va
kod almashtirish shart bo'lmasligi kerak.

Kalit bo'lmasa DemoMedia ishlaydi: haqiqiy so'rov yubormaydi, rangli
placeholder rasm/video yasaydi. Butun oqim bir tiyinsiz sinaladi.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass
class Asset:
    path: str = ""
    url: str = ""
    cost: float = 0.0
    provider: str = ""
    model: str = ""
    meta: dict | None = None


def _download(url: str, dst: str) -> str:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "kinoai/0.5"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dst, "wb") as f:
        f.write(r.read())
    return dst


def _post(url: str, body: dict, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise MediaError(f"{e.code}: {e.read()[:400].decode(errors='replace')}")
    except Exception as e:
        raise MediaError(str(e)) from e


def _get(url: str, headers: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise MediaError(f"{e.code}: {e.read()[:400].decode(errors='replace')}")
    except Exception as e:
        raise MediaError(str(e)) from e


# --------------------------------------------------------------- interfeys

class MediaProvider(ABC):
    name = "base"

    # Narx ENV orqali — provayder tarifi o'zgarsa kod tegilmaydi
    price_image = float(os.getenv("PRICE_PER_IMAGE", "0.04"))
    price_video_sec = float(os.getenv("PRICE_PER_VIDEO_SECOND", "0.22"))

    @abstractmethod
    def image(self, prompt: str, aspect: str, out: str) -> Asset:
        ...

    @abstractmethod
    def video(self, prompt: str, seconds: float, out: str,
              start_image: str = "", start_url: str = "",
              aspect: str = "16:9", resolution: str = "480p",
              audio: bool = True) -> Asset:
        ...

    def est_image(self, n: int = 1) -> float:
        return n * self.price_image

    def est_video(self, seconds: float) -> float:
        return seconds * self.price_video_sec


# ------------------------------------------------------------------- demo

class DemoMedia(MediaProvider):
    """Kalitsiz rejim. FFmpeg bilan placeholder yasaydi."""

    name = "demo"
    COLORS = ["0x2E5C8A", "0x8A5C2E", "0x2E8A5C", "0x8A2E5C",
              "0x5C2E8A", "0x8A8A2E", "0x2E8A8A", "0x5A5A5A"]
    _n = 0

    def _size(self, aspect: str) -> str:
        return "1080x1920" if aspect == "9:16" else "1280x720"

    def image(self, prompt: str, aspect: str, out: str) -> Asset:
        c = self.COLORS[DemoMedia._n % len(self.COLORS)]
        DemoMedia._n += 1
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"color=c={c}:s={self._size(aspect)}",
             "-frames:v", "1", out],
            capture_output=True,
        )
        return Asset(path=out, cost=0.0, provider="demo", model="demo")

    def video(self, prompt, seconds, out, start_image="", start_url="",
              aspect="16:9", resolution="480p", audio=True) -> Asset:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        if start_image and Path(start_image).exists():
            src = ["-loop", "1", "-i", start_image]
            vf = f"scale={self._size(aspect).replace('x', ':')},zoompan=" \
                 f"z='min(zoom+0.0012,1.15)':d={int(seconds*24)}:fps=24"
        else:
            c = self.COLORS[DemoMedia._n % len(self.COLORS)]
            DemoMedia._n += 1
            src = ["-f", "lavfi", "-i",
                   f"color=c={c}:s={self._size(aspect)}:r=24"]
            vf = "null"
        subprocess.run(
            ["ffmpeg", "-y", *src, "-t", f"{seconds}", "-vf", vf,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
            capture_output=True,
        )
        return Asset(path=out, cost=0.0, provider="demo", model="demo")


# ------------------------------------------------------------------ fal.ai

class FalMedia(MediaProvider):
    """fal.ai queue API.

    Naqsh: POST -> request_id + status_url -> polling -> response_url.
    Model ID lar ENV orqali, chunki ular tez-tez o'zgaradi.
    """

    name = "fal"
    BASE = "https://queue.fal.run"

    def __init__(self, key: str) -> None:
        self.key = key
        self.h = {"Authorization": f"Key {key}"}
        self.m_image = os.getenv("FAL_IMAGE_MODEL",
                                 "fal-ai/bytedance/seedream/v4/text-to-image")
        self.m_video = os.getenv("FAL_VIDEO_MODEL",
                                 "fal-ai/bytedance/seedance/v1/pro/image-to-video")
        self.m_video_t2v = os.getenv(
            "FAL_VIDEO_T2V_MODEL",
            "fal-ai/bytedance/seedance/v1/pro/text-to-video")

    def _submit(self, model: str, payload: dict,
                poll: float = 3.0, limit: int = 400) -> dict:
        r = _post(f"{self.BASE}/{model}", payload, self.h)
        status_url = r.get("status_url")
        response_url = r.get("response_url")
        if not status_url:
            return r  # ba'zi modellar sinxron javob beradi

        for _ in range(limit):
            time.sleep(poll)
            st = _get(status_url, self.h)
            state = st.get("status", "")
            if state == "COMPLETED":
                return _get(response_url or status_url, self.h)
            if state in ("FAILED", "ERROR", "CANCELLED"):
                raise MediaError(f"fal: {state} — {str(st)[:300]}")
        raise MediaError("fal: kutish vaqti tugadi")

    @staticmethod
    def _first_url(res: dict, *keys: str) -> str:
        for k in keys:
            v = res.get(k)
            if isinstance(v, dict) and v.get("url"):
                return v["url"]
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if v[0].get("url"):
                    return v[0]["url"]
        raise MediaError(f"javobda URL yo'q: {str(res)[:300]}")

    def image(self, prompt: str, aspect: str, out: str) -> Asset:
        res = self._submit(self.m_image, {
            "prompt": prompt,
            "image_size": ("portrait_16_9" if aspect == "9:16"
                           else "landscape_16_9"),
            "num_images": 1,
        })
        url = self._first_url(res, "images", "image")
        _download(url, out)
        return Asset(path=out, url=url, cost=self.price_image,
                     provider="fal", model=self.m_image)

    def video(self, prompt, seconds, out, start_image="", start_url="",
              aspect="16:9", resolution="480p", audio=True) -> Asset:
        payload = {
            "prompt": prompt,
            "duration": int(round(seconds)),
            "resolution": resolution,
            "aspect_ratio": aspect,
            "generate_audio": bool(audio),
        }
        if start_url:
            payload["image_url"] = start_url
            model = self.m_video
        else:
            model = self.m_video_t2v

        res = self._submit(model, payload, poll=5.0)
        url = self._first_url(res, "video", "videos")
        _download(url, out)
        return Asset(path=out, url=url, cost=self.est_video(seconds),
                     provider="fal", model=model)


# ------------------------------------------------------- ommaviy fayl URL

class Uploader(ABC):
    """Image-to-video uchun rasm OMMAVIY URL bo'lishi kerak.

    Railway lokal fayli tashqi provayder uchun ko'rinmaydi — bu
    hujjatdagi 'Muhim storage qarori' bandining aynan o'zi.
    """

    @abstractmethod
    def put(self, path: str) -> str:
        ...


class FalUploader(Uploader):
    """fal.ai o'z storage'i — qo'shimcha S3 kerak emas."""

    URL = "https://rest.alpha.fal.ai/storage/upload/initiate"

    def __init__(self, key: str) -> None:
        self.h = {"Authorization": f"Key {key}"}

    def put(self, path: str) -> str:
        p = Path(path)
        ct = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") \
            else "image/png"
        r = _post(self.URL, {"file_name": p.name, "content_type": ct}, self.h)
        upload_url = r.get("upload_url")
        file_url = r.get("file_url")
        if not upload_url or not file_url:
            raise MediaError(f"upload initiate: {str(r)[:200]}")
        req = urllib.request.Request(
            upload_url, data=p.read_bytes(), method="PUT",
            headers={"content-type": ct},
        )
        urllib.request.urlopen(req, timeout=180)
        return file_url


class NoUploader(Uploader):
    def put(self, path: str) -> str:
        return ""


def from_env() -> tuple[MediaProvider, Uploader]:
    if key := os.getenv("FAL_API_KEY"):
        return FalMedia(key), FalUploader(key)
    return DemoMedia(), NoUploader()
