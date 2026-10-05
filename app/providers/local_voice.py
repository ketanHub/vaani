import asyncio
import ctypes
import importlib.util
import io
import queue
import threading
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.domain.voice import Language
from app.providers.base import PCMChunk
from app.services.language import detect_language


class LocalWhisperSTT:
    def __init__(
        self,
        *,
        model_name: str = "small",
        download_root: str = "models/whisper",
        device: str = "cpu",
        compute_type: str = "int8",
        num_workers: int = 1,
    ) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")

        self._model_name = model_name
        self._download_root = download_root
        self._device = device
        self._compute_type = compute_type
        self._num_workers = num_workers
        self._model: Any = None
        self._model_lock = threading.Lock()

    def _preload_cuda_runtime(self) -> None:
        if self._device != "cuda":
            return

        for package, names in (
            ("nvidia.cublas", ("libcublasLt.so.12", "libcublas.so.12")),
            (
                "nvidia.cudnn",
                (
                    "libcudnn.so.9",
                    "libcudnn_ops.so.9",
                    "libcudnn_adv.so.9",
                    "libcudnn_cnn.so.9",
                ),
            ),
        ):
            spec = importlib.util.find_spec(package)
            if spec is None or not spec.submodule_search_locations:
                raise RuntimeError(
                    f"{package} is required for CUDA local voice support"
                )
            lib_dir = Path(next(iter(spec.submodule_search_locations))) / "lib"
            for name in names:
                path = lib_dir / name
                if path.exists():
                    ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is not None:
                return self._model

            self._preload_cuda_runtime()
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
                num_workers=self._num_workers,
                download_root=self._download_root,
            )

        return self._model

    async def warm_up(self) -> None:
        await asyncio.to_thread(self._get_model)

    def _transcribe_sync(
        self,
        audio: bytes,
        whisper_language: str | None,
    ) -> tuple[str, str]:
        model = self._get_model()
        segments, info = model.transcribe(
            io.BytesIO(audio),
            language=whisper_language,
            vad_filter=True,
            beam_size=3,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text, str(info.language or "")

    async def transcribe(
        self,
        audio: bytes,
        language_hint: Language | None = None,
    ) -> tuple[str, Language]:
        whisper_language = language_hint if language_hint in {"en", "hi"} else None
        text, reported_language = await asyncio.to_thread(
            self._transcribe_sync,
            audio,
            whisper_language,
        )

        if not text:
            detected: Language = "hi" if reported_language == "hi" else "en"
            return "", detected

        return text, language_hint or detect_language(text)


class LocalPiperTTS:
    def __init__(
        self,
        *,
        english_model: str = "models/piper/en_US-lessac-medium.onnx",
        hindi_model: str = "models/piper/hi_IN-priyamvada-medium.onnx",
        use_cuda: bool = False,
        num_workers: int = 1,
    ) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")

        self._english_model = Path(english_model)
        self._hindi_model = Path(hindi_model)
        self._use_cuda = use_cuda
        self._num_workers = num_workers
        self._voice_pools: dict[str, queue.LifoQueue[Any]] = {}
        self._pool_init_lock = threading.Lock()

    def _voice_key(self, language: Language) -> str:
        return "hi" if language == "hi" else "en"

    def _load_voice(self, language: Language) -> Any:
        from piper.voice import PiperVoice

        key = self._voice_key(language)
        model_path = self._hindi_model if key == "hi" else self._english_model
        return PiperVoice.load(
            model_path,
            use_cuda=self._use_cuda,
        )

    def _get_pool(self, language: Language) -> queue.LifoQueue[Any]:
        key = self._voice_key(language)
        pool = self._voice_pools.get(key)
        if pool is not None:
            return pool

        with self._pool_init_lock:
            pool = self._voice_pools.get(key)
            if pool is not None:
                return pool

            pool = queue.LifoQueue(maxsize=self._num_workers)
            for _ in range(self._num_workers):
                pool.put(self._load_voice(language))
            self._voice_pools[key] = pool
            return pool

    async def warm_up(self, language: Language = "en") -> None:
        await asyncio.to_thread(self._get_pool, language)

    def _synthesize_chunks_sync(
        self,
        text: str,
        language: Language,
    ) -> list[PCMChunk]:
        pool = self._get_pool(language)
        voice = pool.get()
        try:
            return [
                PCMChunk(
                    sample_rate=chunk.sample_rate,
                    sample_width=chunk.sample_width,
                    channels=chunk.sample_channels,
                    audio=chunk.audio_int16_bytes,
                )
                for chunk in voice.synthesize(text)
            ]
        finally:
            pool.put(voice)

    async def stream_pcm(
        self,
        text: str,
        language: Language,
    ) -> AsyncIterator[PCMChunk]:
        chunks = await asyncio.to_thread(
            self._synthesize_chunks_sync,
            text,
            language,
        )
        for chunk in chunks:
            yield chunk

    def _synthesize_wav_sync(
        self,
        text: str,
        language: Language,
    ) -> bytes:
        pool = self._get_pool(language)
        voice = pool.get()
        try:
            output = io.BytesIO()
            with wave.open(output, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
            return output.getvalue()
        finally:
            pool.put(voice)

    async def synthesize(
        self,
        text: str,
        language: Language,
    ) -> bytes:
        return await asyncio.to_thread(
            self._synthesize_wav_sync,
            text,
            language,
        )
