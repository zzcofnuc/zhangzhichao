from __future__ import annotations

import math

import numpy as np

from .models import AnalysisResult, AnalysisSummary, FrameMeasurement, ProcessingConfig, SignalData


def analyze_signal(signal: SignalData, config: ProcessingConfig) -> AnalysisResult:
    samples = np.asarray(signal.samples, dtype=float)
    if samples.size < 16:
        raise ValueError("信号长度不足。")

    processed = preprocess_signal(samples)
    spectrum_frequency_hz, spectrum_magnitude_db, spectrum_magnitude = compute_spectrum(processed, signal.sample_rate_hz, config.window_name)
    dominant_frequency_hz = measure_peak_frequency_from_spectrum(spectrum_frequency_hz, spectrum_magnitude, config)
    frames = analyze_frames(processed, signal.sample_rate_hz, config)

    dominant_speed_mps = frequency_to_speed(dominant_frequency_hz, config.carrier_frequency_hz)
    filtered_speeds = np.array([item.filtered_speed_mps for item in frames], dtype=float) if frames else np.array([dominant_speed_mps])
    snrs = np.array([item.snr_db for item in frames], dtype=float) if frames else np.array([0.0])

    summary = AnalysisSummary(
        source_name=signal.source_name,
        duration_s=signal.duration_s,
        sample_rate_hz=signal.sample_rate_hz,
        num_samples=int(signal.samples.size),
        num_frames=len(frames),
        dominant_frequency_hz=dominant_frequency_hz,
        dominant_speed_mps=dominant_speed_mps,
        dominant_speed_kmh=dominant_speed_mps * 3.6,
        average_speed_mps=float(filtered_speeds.mean()),
        max_speed_mps=float(filtered_speeds.max()),
        average_snr_db=float(snrs.mean()),
    )
    return AnalysisResult(
        signal=signal,
        config=config,
        summary=summary,
        frames=frames,
        processed_samples=processed,
        spectrum_frequency_hz=spectrum_frequency_hz,
        spectrum_magnitude_db=spectrum_magnitude_db,
    )


def preprocess_signal(samples: np.ndarray) -> np.ndarray:
    centered = samples - np.mean(samples)
    peak = np.max(np.abs(centered))
    if peak <= 1e-12:
        return centered
    return centered / peak


def compute_spectrum(samples: np.ndarray, sample_rate_hz: float, window_name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    window = build_window(samples.size, window_name)
    fft_values = np.fft.rfft(samples * window)
    magnitude = np.abs(fft_values)
    magnitude_db = 20.0 * np.log10(magnitude + 1e-12)
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate_hz)
    return freqs, magnitude_db, magnitude


def measure_peak_frequency_from_spectrum(freqs: np.ndarray, magnitude: np.ndarray, config: ProcessingConfig) -> float:
    mask = (freqs >= config.min_frequency_hz) & (freqs <= config.max_frequency_hz)
    if not np.any(mask):
        raise ValueError("频率搜索范围无有效数据。")
    band_freqs = freqs[mask]
    band_mag = magnitude[mask]
    peak_index = int(np.argmax(band_mag))
    return quadratic_peak_frequency(band_freqs, band_mag, peak_index)


def analyze_frames(samples: np.ndarray, sample_rate_hz: float, config: ProcessingConfig) -> list[FrameMeasurement]:
    frame_size = max(256, int(config.frame_size))
    step = max(1, int(frame_size * (1.0 - min(0.95, max(0.0, config.overlap_ratio)))))
    window = build_window(frame_size, config.window_name)

    if samples.size < frame_size:
        padded = np.zeros(frame_size, dtype=float)
        padded[: samples.size] = samples
        samples = padded

    frames: list[FrameMeasurement] = []
    filtered_speed = None
    for start in range(0, samples.size - frame_size + 1, step):
        frame = samples[start : start + frame_size]
        fft_values = np.fft.rfft(frame * window)
        magnitude = np.abs(fft_values)
        freqs = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate_hz)
        mask = (freqs >= config.min_frequency_hz) & (freqs <= config.max_frequency_hz)
        if not np.any(mask):
            continue

        band_freqs = freqs[mask]
        band_mag = magnitude[mask]
        peak_index = int(np.argmax(band_mag))
        peak_frequency_hz = quadratic_peak_frequency(band_freqs, band_mag, peak_index)
        amplitude = float(band_mag[peak_index])
        noise_floor = float(np.median(band_mag) + 1e-12)
        snr_db = 20.0 * math.log10((amplitude + 1e-12) / noise_floor)
        raw_speed_mps = frequency_to_speed(peak_frequency_hz, config.carrier_frequency_hz)

        if filtered_speed is None:
            filtered_speed = raw_speed_mps
        else:
            alpha = min(1.0, max(0.01, config.smoothing_alpha))
            filtered_speed = alpha * raw_speed_mps + (1.0 - alpha) * filtered_speed

        frames.append(
            FrameMeasurement(
                timestamp_s=(start + frame_size / 2.0) / sample_rate_hz,
                frequency_hz=peak_frequency_hz,
                raw_speed_mps=raw_speed_mps,
                filtered_speed_mps=float(filtered_speed),
                amplitude=amplitude,
                snr_db=float(snr_db),
            )
        )
    return frames


def build_window(size: int, window_name: str) -> np.ndarray:
    name = window_name.lower()
    if name == "hamming":
        return np.hamming(size)
    if name == "blackman":
        return np.blackman(size)
    return np.hanning(size)


def quadratic_peak_frequency(freqs: np.ndarray, magnitude: np.ndarray, peak_index: int) -> float:
    if peak_index <= 0 or peak_index >= magnitude.size - 1:
        return float(freqs[peak_index])
    left = magnitude[peak_index - 1]
    center = magnitude[peak_index]
    right = magnitude[peak_index + 1]
    denominator = left - 2.0 * center + right
    if abs(denominator) < 1e-12:
        return float(freqs[peak_index])
    offset = 0.5 * (left - right) / denominator
    bin_width = float(freqs[1] - freqs[0]) if freqs.size > 1 else 0.0
    return float(freqs[peak_index] + offset * bin_width)


def frequency_to_speed(frequency_hz: float, carrier_frequency_hz: float) -> float:
    return float(frequency_hz * 299_792_458.0 / (2.0 * carrier_frequency_hz))
