from __future__ import annotations

import csv
import wave
from pathlib import Path

import numpy as np

from .models import ProcessingConfig, SignalData


def read_signal_file(path: str | Path, sample_rate_hint_hz: float | None = None) -> SignalData:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return _read_text_signal(path, sample_rate_hint_hz)
    if suffix == ".wav":
        return _read_wav_signal(path)
    raise ValueError(f"暂不支持的文件格式: {suffix}")


def _read_text_signal(path: Path, sample_rate_hint_hz: float | None) -> SignalData:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        first_line = handle.readline().strip()

    skiprows = 0
    if first_line:
        try:
            [float(token) for token in first_line.replace(",", " ").split()]
        except ValueError:
            skiprows = 1

    delimiter = "," if path.suffix.lower() == ".csv" else None
    data = np.loadtxt(path, delimiter=delimiter, ndmin=2, skiprows=skiprows)

    if data.shape[1] == 1:
        if sample_rate_hint_hz is None:
            raise ValueError("单列信号文件需要提供采样率。")
        samples = data[:, 0]
        sample_rate_hz = float(sample_rate_hint_hz)
        time_axis_s = np.arange(samples.size, dtype=float) / sample_rate_hz
    else:
        time_axis_s = data[:, 0]
        samples = data[:, 1]
        delta = np.diff(time_axis_s)
        valid_delta = delta[delta > 0]
        if valid_delta.size == 0:
            raise ValueError("时间列无有效采样间隔。")
        sample_rate_hz = float(1.0 / np.median(valid_delta))

    return SignalData(
        samples=np.asarray(samples, dtype=float),
        sample_rate_hz=sample_rate_hz,
        source_name=path.name,
        time_axis_s=np.asarray(time_axis_s, dtype=float),
        path=path,
    )


def _read_wav_signal(path: Path) -> SignalData:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate_hz = float(wav_file.getframerate())
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        frame_count = wav_file.getnframes()
        raw_bytes = wav_file.readframes(frame_count)

    dtype_map = {1: np.uint8, 2: np.int16, 4: np.int32}
    if sample_width not in dtype_map:
        raise ValueError("仅支持 8/16/32 位 WAV 文件。")

    samples = np.frombuffer(raw_bytes, dtype=dtype_map[sample_width]).astype(float)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    if sample_width == 1:
        samples = (samples - 128.0) / 128.0
    elif sample_width == 2:
        samples = samples / 32768.0
    else:
        samples = samples / 2147483648.0

    time_axis_s = np.arange(samples.size, dtype=float) / sample_rate_hz
    return SignalData(samples=samples, sample_rate_hz=sample_rate_hz, source_name=path.name, time_axis_s=time_axis_s, path=path)


def save_signal_csv(path: str | Path, signal: SignalData) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stacked = np.column_stack((signal.time_axis_s, signal.samples))
    np.savetxt(path, stacked, delimiter=",", header="time_s,amplitude", comments="")


def save_analysis_csv(path: str | Path, frames: list) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp_s", "frequency_hz", "speed_mps", "speed_kmh", "snr_db"])
        for frame in frames:
            writer.writerow(
                [
                    f"{frame.timestamp_s:.6f}",
                    f"{frame.frequency_hz:.3f}",
                    f"{frame.filtered_speed_mps:.3f}",
                    f"{frame.filtered_speed_mps * 3.6:.3f}",
                    f"{frame.snr_db:.3f}",
                ]
            )


def generate_synthetic_signal(
    duration_s: float,
    config: ProcessingConfig,
    target_speed_mps: float,
    acceleration_mps2: float = 0.0,
    end_acceleration_mps2: float | None = None,
    speed_profile_mps: np.ndarray | None = None,
    amplitude: float = 1.0,
    noise_level: float = 0.15,
) -> SignalData:
    sample_count = max(1, int(duration_s * config.sample_rate_hz))
    time_axis_s = np.arange(sample_count, dtype=float) / config.sample_rate_hz
    if speed_profile_mps is not None:
        speed_series = np.asarray(speed_profile_mps, dtype=float)
        if speed_series.size != sample_count:
            raise ValueError("速度曲线长度与采样长度不一致。")
    else:
        if end_acceleration_mps2 is None:
            acceleration_series = np.full(sample_count, acceleration_mps2, dtype=float)
        else:
            acceleration_series = np.linspace(acceleration_mps2, end_acceleration_mps2, sample_count, dtype=float)
        speed_series = target_speed_mps + np.cumsum(acceleration_series) / config.sample_rate_hz
    doppler_frequency = (2.0 * speed_series) / config.wavelength_m
    phase = 2.0 * np.pi * np.cumsum(doppler_frequency) / config.sample_rate_hz
    clean_signal = amplitude * np.sin(phase)
    harmonics = 0.10 * np.sin(2.0 * phase + 0.2)
    noise = np.random.default_rng(20260613).normal(0.0, noise_level, sample_count)
    samples = clean_signal + harmonics + noise
    return SignalData(samples=samples.astype(float), sample_rate_hz=config.sample_rate_hz, source_name="synthetic_demo", time_axis_s=time_axis_s)
