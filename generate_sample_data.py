from pathlib import Path

from doppler_app.models import ProcessingConfig
from doppler_app.signal_io import generate_synthetic_signal, save_signal_csv


def main() -> None:
    root = Path(__file__).resolve().parent
    samples_dir = root / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    config = ProcessingConfig(
        sample_rate_hz=24_000.0,
        carrier_frequency_hz=24.125e9,
        frame_size=2048,
        overlap_ratio=0.5,
        min_frequency_hz=20.0,
        max_frequency_hz=6_000.0,
    )

    signal = generate_synthetic_signal(
        duration_s=4.0,
        config=config,
        target_speed_mps=12.0,
        speed_profile_mps=None,
        noise_level=0.18,
    )
    save_signal_csv(samples_dir / "demo_signal.csv", signal)


if __name__ == "__main__":
    main()
