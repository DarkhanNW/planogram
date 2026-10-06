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
    detector_model: str = "google/owlv2-base-patch16-ensemble"
    embedding_model: str = "facebook/dinov2-small"

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
            detector_model=env.get("PLANOGRAM_DETECTOR_MODEL", cls.detector_model),
            embedding_model=env.get("PLANOGRAM_EMBEDDING_MODEL", cls.embedding_model),
        )
