import hashlib
import threading
import wave
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import pyttsx3
except Exception:  # pragma: no cover
    pyttsx3 = None


AUDIO_LOCK = threading.Lock()
AUDIO_PROFILE_VERSION = "multi_voice_v2"


def build_dialogue_audio_text(turns: List[Dict]) -> str:
    lines = [str(turn.get("en", "")).strip() for turn in turns]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return " ... ".join(lines)


def _available_voice_ids() -> List[str]:
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 is not installed.")

    engine = pyttsx3.init()
    try:
        voices = engine.getProperty("voices") or []
        voice_ids = [str(item.id) for item in voices if getattr(item, "id", None)]
    finally:
        engine.stop()

    if not voice_ids:
        raise RuntimeError("No local TTS voices available.")

    english_ids = []
    for voice_id in voice_ids:
        upper = voice_id.upper()
        if (
            "_EN-" in upper
            or "\\TTS_MS_EN-" in upper
            or "ENGLISH" in upper
            or "EN-US" in upper
            or "EN-GB" in upper
        ):
            english_ids.append(voice_id)

    if english_ids:
        return english_ids
    return voice_ids


def _pick_voice_pair(dialogue_id: str, voice_ids: List[str]) -> Tuple[str, str]:
    seed = int(hashlib.sha1(dialogue_id.encode("utf-8")).hexdigest(), 16)
    first_idx = seed % len(voice_ids)
    if len(voice_ids) == 1:
        second_idx = first_idx
    else:
        second_idx = (first_idx + 1) % len(voice_ids)
    return voice_ids[first_idx], voice_ids[second_idx]


def _profile_hash(voice_a: str, voice_b: str, rate_a: int, rate_b: int) -> str:
    raw = f"{AUDIO_PROFILE_VERSION}|{voice_a}|{voice_b}|{rate_a}|{rate_b}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _synthesize_line_wav(text: str, out_path: Path, voice_id: str, rate: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    engine = pyttsx3.init()
    try:
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.setProperty("rate", rate)
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
    finally:
        engine.stop()

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Failed to synthesize speech line.")


def _concat_wav_files(source_files: List[Path], out_path: Path, silence_ms: int) -> None:
    if not source_files:
        raise RuntimeError("No source WAV files to combine.")

    with wave.open(str(source_files[0]), "rb") as first:
        nchannels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()
        comptype = first.getcomptype()
        compname = first.getcompname()

    silence_frames = int((framerate * silence_ms) / 1000.0)
    silence_bytes = b"\x00" * silence_frames * nchannels * sampwidth

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.setcomptype(comptype, compname)

        for idx, path in enumerate(source_files):
            with wave.open(str(path), "rb") as src:
                if (
                    src.getnchannels() != nchannels
                    or src.getsampwidth() != sampwidth
                    or src.getframerate() != framerate
                ):
                    raise RuntimeError("Audio format mismatch in source files.")
                out.writeframes(src.readframes(src.getnframes()))
            if idx < len(source_files) - 1:
                out.writeframes(silence_bytes)


def ensure_dialogue_wav(
    audio_dir: Path,
    dialogue_id: str,
    turns: List[Dict],
    base_rate: int = 165,
) -> Path:
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 is not installed.")

    cleaned_turns = []
    for item in turns:
        sentence = str(item.get("en", "")).strip()
        if not sentence:
            continue
        speaker = str(item.get("speaker", "A")).strip().upper()
        speaker = "A" if speaker != "B" else "B"
        cleaned_turns.append({"speaker": speaker, "en": sentence})

    if not cleaned_turns:
        raise RuntimeError("No dialogue text to synthesize.")

    voice_ids = _available_voice_ids()
    voice_a, voice_b = _pick_voice_pair(dialogue_id, voice_ids)
    rate_seed = int(hashlib.sha1(f"{dialogue_id}|rate".encode("utf-8")).hexdigest(), 16)
    delta = (rate_seed % 11) - 5
    rate_a = max(145, min(195, base_rate + 10 + delta))
    rate_b = max(145, min(195, base_rate - 10 + delta))
    profile = _profile_hash(voice_a, voice_b, rate_a, rate_b)

    audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = audio_dir / f"{dialogue_id}_{profile}.wav"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    with AUDIO_LOCK:
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        segment_dir = audio_dir / "_segments" / profile
        segment_files = []
        for idx, row in enumerate(cleaned_turns):
            voice_id = voice_a if row["speaker"] == "A" else voice_b
            rate = rate_a if row["speaker"] == "A" else rate_b
            seg_path = segment_dir / f"{dialogue_id}_{idx:02d}_{row['speaker']}.wav"
            if not seg_path.exists() or seg_path.stat().st_size == 0:
                _synthesize_line_wav(row["en"], seg_path, voice_id, rate)
            segment_files.append(seg_path)

        tmp_path = audio_dir / f"{dialogue_id}_{profile}.tmp.wav"
        if tmp_path.exists():
            tmp_path.unlink()
        _concat_wav_files(segment_files, tmp_path, silence_ms=260)

        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise RuntimeError("Failed to generate dialogue audio file.")

        tmp_path.replace(out_path)
        return out_path


def _playlist_key(dialogue_ids: List[str], source_files: List[Path]) -> str:
    source_sig = ",".join(path.name for path in source_files)
    joined = ",".join(dialogue_ids) + "|" + source_sig
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def ensure_playlist_wav(
    audio_dir: Path,
    dialogue_ids: List[str],
    source_files: List[Path],
    silence_ms: int = 320,
) -> Path:
    if not dialogue_ids or not source_files or len(dialogue_ids) != len(source_files):
        raise RuntimeError("Invalid playlist input.")

    audio_dir.mkdir(parents=True, exist_ok=True)
    key = _playlist_key(dialogue_ids, source_files)
    out_path = audio_dir / f"playlist_{key}.wav"

    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    with AUDIO_LOCK:
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        tmp_path = audio_dir / f"playlist_{key}.tmp.wav"
        if tmp_path.exists():
            tmp_path.unlink()

        _concat_wav_files(source_files, tmp_path, silence_ms=silence_ms)

        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            raise RuntimeError("Failed to generate playlist audio file.")

        tmp_path.replace(out_path)
        return out_path
