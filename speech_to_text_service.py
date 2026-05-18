#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shared speech-to-text adapter for bot transports.

Telegram and MAX adapters use this module only to convert voice/audio bytes to
plain text. The business pipeline still receives text through
MessageHandlerService.
"""

import json
import logging
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

try:
    from decouple import config
except ImportError:  # pragma: no cover
    config = None

logger = logging.getLogger(__name__)

YANDEX_STT_ENDPOINT = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
STT_AUDIO_LIMIT_BYTES = 1024 * 1024
STT_SOURCE_AUDIO_LIMIT_BYTES = 20 * 1024 * 1024
YANDEX_STT_ALLOWED_RATES = {8000, 16000, 48000}


class SpeechToTextError(Exception):
    """Speech-to-text conversion failed."""

    def __init__(self, message: str, *, code: str = "speech_error", status: int = 400):
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    if config is not None:
        return config(name, default=default)
    return os.getenv(name, default)


class YandexSpeechToTextService:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        iam_token: Optional[str] = None,
        folder_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ):
        self.api_key = api_key or _env("YANDEX_API_KEY")
        self.iam_token = iam_token or _env("YANDEX_IAM_TOKEN")
        self.folder_id = folder_id or _env("YANDEX_FOLDER_ID")
        self.endpoint = endpoint or _env("YANDEX_STT_ENDPOINT", YANDEX_STT_ENDPOINT)

    def recognize(
        self,
        audio_bytes: bytes,
        *,
        audio_format: Optional[str] = None,
        sample_rate_hertz: int = 16000,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not audio_bytes:
            raise SpeechToTextError("Audio is empty.", code="empty_audio")
        if len(audio_bytes) > STT_SOURCE_AUDIO_LIMIT_BYTES:
            raise SpeechToTextError("Audio file is too large.", code="audio_too_large", status=413)

        detected_format = audio_format or self.detect_audio_format(audio_bytes, metadata=metadata)
        if detected_format == "oggopus":
            recognition_bytes = audio_bytes
            yandex_format = "oggopus"
            yandex_sample_rate = None
        else:
            recognition_bytes, yandex_sample_rate = self.convert_to_lpcm(audio_bytes)
            yandex_format = "lpcm"

        text = self._recognize_yandex(
            recognition_bytes,
            audio_format=yandex_format,
            sample_rate_hertz=yandex_sample_rate or sample_rate_hertz,
        )
        return {
            "text": text,
            "provider": "yandex_speechkit",
            "format": yandex_format,
            "source_format": detected_format,
            "source_size": len(audio_bytes),
            "recognition_size": len(recognition_bytes),
        }

    def detect_audio_format(self, audio_bytes: bytes, *, metadata: Optional[Dict[str, Any]] = None) -> str:
        metadata = metadata or {}
        mime_type = str(metadata.get("mime_type") or "").lower()
        file_name = str(metadata.get("file_name") or "").lower()
        if audio_bytes.startswith(b"OggS") or "ogg" in mime_type or file_name.endswith(".ogg"):
            return "oggopus"
        if "opus" in mime_type or file_name.endswith(".opus"):
            return "oggopus"
        return "convert"

    def convert_to_lpcm(self, source_bytes: bytes) -> tuple[bytes, int]:
        suffix = ".audio"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as source:
            source.write(source_bytes)
            source_path = source.name
        output_path = f"{source_path}.pcm"
        try:
            command = [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                source_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                output_path,
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, timeout=30)
            except FileNotFoundError as exc:
                raise SpeechToTextError(
                    "ffmpeg is not installed for audio conversion.",
                    code="ffmpeg_missing",
                    status=500,
                ) from exc
            except subprocess.CalledProcessError as exc:
                logger.warning("ffmpeg audio conversion failed: %s", exc.stderr.decode("utf-8", errors="replace")[:500])
                raise SpeechToTextError(
                    "Audio conversion failed.",
                    code="audio_conversion_failed",
                ) from exc

            with open(output_path, "rb") as converted:
                converted_bytes = converted.read(STT_AUDIO_LIMIT_BYTES + 1)
            if len(converted_bytes) > STT_AUDIO_LIMIT_BYTES:
                raise SpeechToTextError("Audio is too long for synchronous STT.", code="audio_too_large", status=413)
            return converted_bytes, 16000
        finally:
            for path in (source_path, output_path):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    def _auth_header(self) -> tuple[str, bool]:
        if self.api_key:
            return f"Api-Key {self.api_key}", False
        if self.iam_token:
            return f"Bearer {self.iam_token}", True
        raise SpeechToTextError("Yandex SpeechKit is not configured.", code="stt_not_configured", status=500)

    def _recognize_yandex(self, audio_bytes: bytes, *, audio_format: str, sample_rate_hertz: int = 16000) -> str:
        if audio_format not in {"lpcm", "oggopus"}:
            raise SpeechToTextError("Unsupported audio format.", code="invalid_audio_format")
        if audio_format == "lpcm" and sample_rate_hertz not in YANDEX_STT_ALLOWED_RATES:
            raise SpeechToTextError("Unsupported sample rate.", code="invalid_sample_rate")
        if len(audio_bytes) > STT_AUDIO_LIMIT_BYTES:
            raise SpeechToTextError("Audio is too long for synchronous STT.", code="audio_too_large", status=413)

        auth_header, requires_folder = self._auth_header()
        query = {
            "lang": "ru-RU",
            "format": audio_format,
        }
        if audio_format == "lpcm":
            query["sampleRateHertz"] = str(sample_rate_hertz)
        if requires_folder:
            if not self.folder_id:
                raise SpeechToTextError("YANDEX_FOLDER_ID is not configured.", code="stt_not_configured", status=500)
            query["folderId"] = self.folder_id

        request = urllib.request.Request(
            f"{self.endpoint}?{urllib.parse.urlencode(query)}",
            data=audio_bytes,
            headers={
                "Authorization": auth_header,
                "Content-Type": "application/octet-stream",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.warning("Yandex STT HTTP %s: %s", exc.code, error_body[:500])
            raise SpeechToTextError("Yandex SpeechKit returned an error.", code="stt_upstream_error", status=502) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.exception("Yandex STT request failed")
            raise SpeechToTextError("Yandex SpeechKit is unavailable.", code="stt_unavailable", status=502) from exc

        return (payload.get("result") or "").strip()


def recognize_audio_bytes(
    audio_bytes: bytes,
    *,
    audio_format: Optional[str] = None,
    sample_rate_hertz: int = 16000,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return YandexSpeechToTextService().recognize(
        audio_bytes,
        audio_format=audio_format,
        sample_rate_hertz=sample_rate_hertz,
        metadata=metadata,
    )
