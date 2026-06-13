from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


SPEED_OF_LIGHT_MPS = 299_792_458.0


@dataclass(slots=True)
class SignalData:
    samples: np.ndarray
    sample_rate_hz: float
    source_name: str
    time_axis_s: np.ndarray
    path: Optional[Path] = None

    @property
    def duration_s(self) -> float:
        if self.samples.size == 0:
            return 0.0
        return float(self.samples.size / self.sample_rate_hz)


@dataclass(slots=True)
class ProcessingConfig:
    sample_rate_hz: float
    carrier_frequency_hz: float
    frame_size: int = 2048
    overlap_ratio: float = 0.5
    min_frequency_hz: float = 20.0
    max_frequency_hz: float = 6_000.0
    smoothing_alpha: float = 0.30
    window_name: str = "hann"

    @property
    def wavelength_m(self) -> float:
        return SPEED_OF_LIGHT_MPS / self.carrier_frequency_hz


@dataclass(slots=True)
class FrameMeasurement:
    timestamp_s: float
    frequency_hz: float
    raw_speed_mps: float
    filtered_speed_mps: float
    amplitude: float
    snr_db: float


@dataclass(slots=True)
class AnalysisSummary:
    source_name: str
    duration_s: float
    sample_rate_hz: float
    num_samples: int
    num_frames: int
    dominant_frequency_hz: float
    dominant_speed_mps: float
    dominant_speed_kmh: float
    average_speed_mps: float
    max_speed_mps: float
    average_snr_db: float


@dataclass(slots=True)
class AnalysisResult:
    signal: SignalData
    config: ProcessingConfig
    summary: AnalysisSummary
    frames: list[FrameMeasurement] = field(default_factory=list)
    processed_samples: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    spectrum_frequency_hz: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
    spectrum_magnitude_db: np.ndarray = field(default_factory=lambda: np.array([], dtype=float))
