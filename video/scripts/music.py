"""Rebuild the MorningDAW score (optional) and remake mix.wav.

Requires ffmpeg and NumPy. Rebuilding the score also needs a local MorningDAW
1.6.3 install and the hermes-morningdaw `mdaw` package. The film itself renders
from the bundled WAVs and does not need those tools.

  python3 scripts/music.py                  # remake mix from existing score/voice/sfx
  python3 scripts/music.py --rebuild-score  # generate, patch, mix stems, then remake mix
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
DURATION = 90.0
N = int(DURATION * SR)
DROP = 20.0
# Kick on the stems mix started 5 ms late; shift the bed earlier so the drop
# lands at 20.00 s.
OFFSET_S = 0.005
BED_LUFS = -22.0
FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]


def run(args, **kw):
    return subprocess.run(args, check=True, **kw)


def read_f32(path, sr=SR, ac=2, duration=None):
    cmd = FF[:-1] + ["-i", str(path), "-ar", str(sr), "-ac", str(ac)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-f", "f32le", "-"]
    raw = run(cmd, capture_output=True).stdout
    a = np.frombuffer(raw, dtype="<f4").copy()
    if ac > 1:
        if a.size % ac:
            a = a[: a.size - a.size % ac]
        a = a.reshape(-1, ac)
    return a


def write_wav(path, data, sr=SR, ch=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(data, dtype=np.float32)
    if x.ndim == 1:
        x = x[:, None]
    ch = ch or x.shape[1]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def measure(path, t=None):
    import re
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path)]
    if t is not None:
        cmd += ["-t", str(t)]
    cmd += ["-af", "ebur128=peak=true", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True).stderr

    def grab(pat):
        ms = list(re.finditer(pat, e))
        return float(ms[-1].group(1)) if ms else None

    return {
        "input_i": grab(r"I:\s+(-?[\d.]+) LUFS"),
        "input_tp": grab(r"Peak:\s+(-?[\d.]+) dBFS") or grab(r"True peak:\s+(-?[\d.]+) dBTP"),
        "input_lra": grab(r"LRA:\s+([\d.]+) LU"),
        "input_thresh": grab(r"Threshold:\s+(-?[\d.]+) LUFS"),
    }


def loudnorm_two_pass(src, dest, I=-15, TP=-1.5, LRA=11):
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(src),
           "-af", f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True).stderr
    j = json.JSONDecoder().raw_decode(e[e.rfind("{"):])[0]
    f = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}:measured_I={j['input_i']}:"
         f"measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
         f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    run(FF + ["-i", str(src), "-af", f, "-ar", str(SR), "-c:a", "pcm_s16le", str(dest)])
    return j


def _mdaw():
    try:
        from mdaw import tools  # type: ignore
        return tools
    except ImportError:
        for cand in (Path.home() / "hermes-morningdaw", Path("/workspace/hermes-morningdaw")):
            if (cand / "mdaw").is_dir():
                sys.path.insert(0, str(cand))
                from mdaw import tools  # type: ignore
                return tools
        raise SystemExit("Cannot import mdaw. Install hermes-morningdaw or add it to PYTHONPATH.")


def rebuild_score(root: Path, tools) -> Path:
    """Call the same mdaw tool functions the Hermes plugin exposes."""
    md = root / "assets/audio/morningdaw"
    spec = json.loads((md / "spec.json").read_text())
    project = md / "one-live-screen.mdproject"
    inst = tools.check_install({})
    if not inst.get("installed"):
        raise SystemExit("MorningDAW is not installed. " + str(inst.get("download_url") or ""))
    tools.generate({"out": str(project), "title": spec.get("title", "One Live Screen"), "spec": spec})
    listed = tools.list_instruments({"project": str(project)})
    tracks = { (t.get("name") or "").strip().lower(): int(t["track"]) for t in listed["tracks"] }
    patches = {
        "pad": ("patches_factory/Pads/Choir Pad Thing.fxp", None, "Choir Pad"),
        "arp": ("patches_factory/Plucks/Bell 1.fxp", None, "Bell Arp"),
        "bass": ("patches_factory/Basses/Sub 2.fxp", None, "Sub 2"),
        "lead": ("patches_factory/Leads/Sine Lead.fxp", {"a_portamento": "-2.0"}, "Sine Lead"),
        "stab": ("patches_factory/Keys/Organ 1.fxp", None, "Organ Stab"),
    }
    for role, (patch, params, name) in patches.items():
        args = {"project": str(project), "track": tracks[role], "patch": patch, "name": name}
        if params:
            args["params"] = params
        tools.add_instrument(args)
    for ev in (
        {"target": f"track:{tracks['pad']}", "plugin": "dragonfly-hall", "name": "Hall Pad"},
        {"target": f"track:{tracks['arp']}", "plugin": "dragonfly-hall", "name": "Hall Bells"},
        {"target": "pad:40", "plugin": "dragonfly-room", "name": "Room Snare"},
        {"target": "master", "plugin": "airwindows:ToTape6", "name": "ToTape6"},
    ):
        tools.add_effect({"project": str(project), **ev})
    ab = tools.ab_check({"project": str(project), "seconds": 28})
    (md / "ab_check.json").write_text(json.dumps(ab, indent=2, default=str) + "\n")
    if not ab.get("all_changed", False):
        raise SystemExit(f"ab_check left unchanged effects: {ab}")
    out = md / "score-stems"
    res = tools.mix_stems({
        "project": str(project),
        "out": str(out),
        "seconds": 94,
        "bus_comp": True,
        "limit": True,
        "stems": [
            {"name": "drums", "tracks": [0], "parallel_comp": 0.4},
            {"name": "pads", "tracks": [1], "highpass": 120, "eq": [[2500, -4]]},
            {"name": "keys", "tracks": [2, 4], "highpass": 120, "eq": [[2500, -4]]},
            {"name": "bass", "tracks": [3], "highpass": 35},
            {"name": "lead", "tracks": [5], "highpass": 120, "eq": [[2500, -4]]},
        ],
    })
    if not res.get("qa_ok"):
        raise SystemExit(f"mix_stems QA failed: {res}")
    mp3 = Path(str(out) + ".mp3")
    if mp3.exists():
        mp3.unlink()
    return Path(str(out) + ".wav")


def remake_mix(root: Path, score_src: Path, already_bed: bool = False) -> None:
    audio = root / "assets/audio"
    cues = json.loads((root / "assets/narration-timing.json").read_text())
    tmp = audio / ".mix-tmp"
    tmp.mkdir(exist_ok=True)
    score_adj = audio / "score.wav"
    if already_bed:
        if Path(score_src).resolve() != score_adj.resolve():
            shutil.copy(score_src, score_adj)
        bed_m = measure(score_adj, t=90)
    else:
        score = read_f32(score_src, sr=SR, ac=2)
        shift = int(round(OFFSET_S * SR))
        if shift > 0:
            score = score[shift:]
        if len(score) < N:
            score = np.vstack([score, np.zeros((N - len(score), 2), np.float32)])
        else:
            score = score[:N]
        fade_in = np.minimum(1, np.arange(N) / (0.015 * SR))
        fade_out = np.minimum(1, (N - 1 - np.arange(N)) / (1.0 * SR))
        score *= fade_in[:, None] * fade_out[:, None]
        raw_score = tmp / "score-48k.wav"
        write_wav(raw_score, score, sr=SR, ch=2)
        m = measure(raw_score, t=90)
        bed_gain = BED_LUFS - float(m["input_i"])
        run(FF + ["-i", str(raw_score), "-af", f"volume={bed_gain}dB", "-c:a", "pcm_s16le", str(score_adj)])
        bed_m = measure(score_adj, t=90)

    voice = np.zeros(N, np.float32)
    for c in cues:
        a = read_f32(root / c["file"], sr=SR, ac=1).reshape(-1)
        s = int(round(c["start"] * SR))
        e = min(N, s + len(a))
        if s < N and e > s:
            voice[s:e] += a[: e - s]
    vo_path = tmp / "voice-bed.wav"
    write_wav(vo_path, voice, sr=SR, ch=1)
    raw_mix = tmp / "mix-pre.wav"
    fc = (
        "[1:a]asplit=2[vo][sc];"
        "[0:a][sc]sidechaincompress=threshold=0.05:ratio=6:attack=15:release=220:makeup=1:knee=6[ducked];"
        "[vo][2:a][ducked]amix=inputs=3:normalize=0:dropout_transition=0,"
        f"atrim=0:{DURATION},afade=t=out:st={DURATION-1.2}:d=1.2[out]"
    )
    run(FF + ["-i", str(score_adj), "-i", str(vo_path), "-i", str(audio / "sfx.wav"),
              "-filter_complex", fc, "-map", "[out]", "-ar", str(SR), "-ac", "2",
              "-c:a", "pcm_s16le", str(raw_mix)])
    mix_path = audio / "mix.wav"
    ln = loudnorm_two_pass(raw_mix, mix_path)
    final = measure(mix_path)
    if final["input_tp"] is not None and final["input_tp"] > -1.05:
        extra = -1.2 - final["input_tp"]
        trim = tmp / "mix-trim.wav"
        run(FF + ["-i", str(mix_path), "-af", f"volume={extra}dB", "-c:a", "pcm_s16le", str(trim)])
        trim.replace(mix_path)
        final = measure(mix_path)
    shutil.rmtree(tmp, ignore_errors=True)
    report = {
        "bpm": 120,
        "key": "D minor",
        "chords": ["Dm", "Bb", "F", "C"],
        "seed": 1,
        "downbeat": 0,
        "drop": DROP,
        "drop_offset_ms": OFFSET_S * 1000,
        "score": "MorningDAW 1.6.3 + Surge XT + Dragonfly + Airwindows ToTape6",
        "voice": {
            "model": "Kokoro-82M v1.0 fp32 ONNX",
            "id": "blend_heart_bella_60",
            "mix": "0.6 af_heart + 0.4 af_bella",
            "speed": 1.0,
            "lang": "en-us",
            "polish": "de-ess + 2.5/3.8 kHz presence + 70 Hz highpass",
        },
        "bed_lufs": {k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in bed_m.items()},
        "pcm": {k: (f"{v:.2f}" if isinstance(v, float) else v) for k, v in final.items()},
        "loudnorm": "I=-15:TP=-1.5:LRA=11 two-pass",
        "loudnorm_first_pass": ln,
    }
    (audio / "mastering.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild-score", action="store_true",
                   help="Regenerate the MorningDAW project and stem mix first")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    stems = root / "assets/audio/morningdaw/score-stems.wav"
    bundled = root / "assets/audio/score.wav"
    if args.rebuild_score:
        stems = rebuild_score(root, _mdaw())
        remake_mix(root, stems)
    else:
        # Remake the 90 s bed+mix from the existing stems if present, else the bundled score.
        if stems.is_file():
            remake_mix(root, stems)
        else:
            # Bundled score.wav is already shifted and levelled to -22 LUFS.
            remake_mix(root, bundled, already_bed=True)


if __name__ == "__main__":
    main()
