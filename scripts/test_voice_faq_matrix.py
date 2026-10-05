import asyncio
import json

import httpx

from app.domain.voice import Language
from app.providers.local_voice import LocalPiperTTS


CASES: list[tuple[str, Language, str, str]] = [
    ("hours-en", "en", "What are your opening hours?", "hours"),
    ("location-en", "en", "Where are you located?", "location"),
    ("services-en", "en", "What services do you offer?", "services"),
    ("fee-en", "en", "What is the consultation fee?", "fee"),
    ("appointments-en", "en", "Can I book an appointment?", "appointments"),
    ("hours-hi", "hi", "क्लिनिक कब खुलता है?", "hours"),
    ("location-hi", "hi", "पता क्या है?", "location"),
    ("services-hi", "hi", "क्या सेवाएं हैं?", "services"),
    ("fee-hi", "hi", "फीस कितनी है?", "fee"),
    ("appointments-hi", "hi", "अपॉइंटमेंट बुक करना है", "appointments"),
]


async def main() -> None:
    tts = LocalPiperTTS(num_workers=1)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8010",
        timeout=30.0,
    ) as client:
        results: list[dict[str, object]] = []

        for name, language, prompt, expected_source in CASES:
            audio = await tts.synthesize(prompt, language)
            response = await client.post(
                "/v1/dev/local-voice/tenants/demo-clinic/turn",
                data={
                    "call_id": f"matrix-{name}",
                    "language_hint": language,
                },
                files={
                    "audio": (
                        f"{name}.wav",
                        audio,
                        "audio/wav",
                    )
                },
            )
            body = response.json()
            ok = (
                response.status_code == 200
                and body.get("grounded") is True
                and body.get("handoff_required") is False
                and body.get("source_ids") == [expected_source]
            )
            results.append(
                {
                    "name": name,
                    "language": language,
                    "prompt": prompt,
                    "transcript": body.get("transcript"),
                    "source_ids": body.get("source_ids"),
                    "grounded": body.get("grounded"),
                    "ok": ok,
                }
            )

        passed = sum(bool(result["ok"]) for result in results)
        print(
            json.dumps(
                {
                    "passed": passed,
                    "total": len(results),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        if passed != len(results):
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
