"""Regenerate the 12 narration cues with the chosen Kokoro-82M v1.0 fp32 voice.

Uses a 60/40 blend of the stock af_heart and af_bella styles. No Terry voice
or clone. Spoken respellings keep captions on the correct spellings.

  python3 scripts/voice.py --model-dir /path/to/kokoro   # dir has kokoro-v1.0.onnx and voices-v1.0.bin
"""
from __future__ import annotations

import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort
from kokoro_onnx import Kokoro

REPLACEMENTS = [
    ("WorldSim", "World Sim"),
    ("HolyC", "Holy Cee"),
    ("TempleOS", "Temple O S"),
    ("HBBS/1", "H B B S one"),
    ("COM2", "COM two"),
    ("QEMU", "Q E M U"),
    ("Nous", "Noos"),
    ("Codex", "Kohdex"),
    ("capybara", "cap-ee-bar-ah"),
]


def spoken(text: str) -> str:
    t = text
    for src, dst in sorted(REPLACEMENTS, key=lambda kv: -len(kv[0])):
        t = t.replace(src, dst)
    return t


def caption(text: str) -> str:
    return (text.replace("Holy C", "HolyC").replace("World Sim", "WorldSim")
                .replace("H B B S one", "HBBS/1").replace("COM two", "COM2")
                .replace("Temple O S", "TempleOS"))


def trim(samples: np.ndarray, sr: int) -> np.ndarray:
    active = np.flatnonzero(np.abs(samples) > 0.002)
    if len(active) == 0:
        return samples
    start = max(0, int(active[0]) - int(0.01 * sr))
    end = min(len(samples), int(active[-1]) + int(0.05 * sr))
    return samples[start:end]


def write_wav(path: Path, samples: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(np.asarray(samples, dtype=np.float32), -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def polish(src: Path, dest: Path) -> None:
    af = ",".join([
        "highpass=f=70",
        "deesser=i=0.18:m=0.35:f=0.5:s=o",
        "equalizer=f=2500:t=q:w=1.2:g=1.5",
        "equalizer=f=3800:t=q:w=1.3:g=2.0",
        "alimiter=limit=0.95:attack=5:release=50",
    ])
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", str(src), "-af", af, "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(dest)],
        check=True,
    )


def stamp(t: float) -> str:
    n = max(0, int(round(t * 1000)))
    return f"{n // 3600000:02}:{n // 60000 % 60:02}:{n // 1000 % 60:02},{n % 1000:03}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", type=Path, required=True,
                   help="Directory with kokoro-v1.0.onnx (fp32) and voices-v1.0.bin")
    p.add_argument("--voice", default="blend_heart_bella_60",
                   help="af_heart, af_bella, or blend_heart_bella_60 (default)")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2
    so.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.model_dir / "kokoro-v1.0.onnx"),
                                   sess_options=so, providers=["CPUExecutionProvider"])
    model = Kokoro.from_session(session, str(args.model_dir / "voices-v1.0.bin"))
    if args.voice == "blend_heart_bella_60":
        style = 0.6 * model.get_voice_style("af_heart") + 0.4 * model.get_voice_style("af_bella")
    else:
        style = model.get_voice_style(args.voice)
    cues = json.loads((root / "narration.json").read_text())
    out = root / "assets/audio/voice"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / ".tmp"
    tmp.mkdir(exist_ok=True)
    timing = []
    for i, c in enumerate(cues):
        text = spoken(c["text"])
        window = c["deadline"] - c["start"]
        chosen = None
        for speed in (1.0, 1.02, 1.05, 0.95, 0.9):
            samples, sr = model.create(text, voice=style, speed=speed, lang="en-us")
            samples = trim(np.asarray(samples, dtype=np.float32), sr)
            dur = len(samples) / sr
            if dur < window - 0.05 and float(np.max(np.abs(samples))) < 0.999:
                chosen = (samples, sr, speed, dur)
                break
        if chosen is None:
            raise SystemExit(f"cue {i} does not fit its deadline even at speed 1.05")
        samples, sr, speed, dur = chosen
        raw = tmp / f"{i:02}-raw.wav"
        write_wav(raw, samples, sr)
        dest = out / f"{i:02}.wav"
        polish(raw, dest)
        raw.unlink()
        with wave.open(str(dest), "rb") as w:
            end = c["start"] + w.getnframes() / w.getframerate()
        assert end < c["deadline"], (i, end, c["deadline"])
        timing.append({
            "start": c["start"], "deadline": c["deadline"],
            "text": caption(c["text"]), "end": end,
            "file": f"assets/audio/voice/{i:02}.wav",
        })
        print(i, round(end - c["start"], 3), "speed", speed, flush=True)
    tmp.rmdir()
    (root / "assets/narration-timing.json").write_text(json.dumps(timing, indent=2) + "\n")
    (root / "captions").mkdir(exist_ok=True)
    (root / "captions/narration.srt").write_text(
        "\n\n".join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}"
                    for i, c in enumerate(timing)) + "\n"
    )


if __name__ == "__main__":
    main()
