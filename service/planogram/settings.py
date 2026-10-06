import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    db_path: Path
    image_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("PLANOGRAM_DATA_DIR", "data"))
        return cls(
            api_key=os.environ["PLANOGRAM_API_KEY"],
            db_path=Path(os.environ.get("PLANOGRAM_DB_PATH", data_dir / "planogram.sqlite")),
            image_dir=Path(os.environ.get("PLANOGRAM_IMAGE_DIR", data_dir / "images")),
        )
