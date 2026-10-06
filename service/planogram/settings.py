import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    db_path: Path
    image_dir: Path

    match_threshold: float = 0.70
    """Embedding similarity below which a Facing is an Unknown Product. Set high on purpose:
    an Unknown Product costs a Manager one click, a wrong match corrupts a Planogram."""
    match_margin: float = 0.05
    """How far the best Product must lead the runner-up before a match is trusted."""
    detection_threshold: float = 0.15
    verification_threshold: float = 0.60
    """Recognition confidence below which a Compliance Check leaves an area Unverified rather
    than report a Deviation or confirm compliance there. Precision first: a Manager sent to fix
    something that is not broken stops trusting the report."""
    detector_model: str = "google/owlv2-base-patch16-ensemble"
    embedding_model: str = "facebook/dinov2-small"
    photo_retention_months: int = 6
    """How long a Shelf Photo is kept after upload before the retention sweep deletes it (ADR 0003)."""
    retention_sweep_hours: float = 1.0
    """How often the retention sweep runs; it also runs when the service starts."""

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        data_dir = Path(env.get("PLANOGRAM_DATA_DIR", "data"))
        return cls(
            api_key=env["PLANOGRAM_API_KEY"],
            db_path=Path(env.get("PLANOGRAM_DB_PATH", data_dir / "planogram.sqlite")),
            image_dir=Path(env.get("PLANOGRAM_IMAGE_DIR", data_dir / "images")),
            match_threshold=float(env.get("PLANOGRAM_MATCH_THRESHOLD", cls.match_threshold)),
            match_margin=float(env.get("PLANOGRAM_MATCH_MARGIN", cls.match_margin)),
            detection_threshold=float(env.get("PLANOGRAM_DETECTION_THRESHOLD", cls.detection_threshold)),
            verification_threshold=float(env.get("PLANOGRAM_VERIFICATION_THRESHOLD", cls.verification_threshold)),
            detector_model=env.get("PLANOGRAM_DETECTOR_MODEL", cls.detector_model),
            embedding_model=env.get("PLANOGRAM_EMBEDDING_MODEL", cls.embedding_model),
            photo_retention_months=int(env.get("PLANOGRAM_PHOTO_RETENTION_MONTHS", cls.photo_retention_months)),
            retention_sweep_hours=float(env.get("PLANOGRAM_RETENTION_SWEEP_HOURS", cls.retention_sweep_hours)),
        )
