from pathlib import Path

import cv2
import pytest

from planogram.blurring import OpenCvPersonBlurrer

MOCKUP_PHOTOS = sorted((Path(__file__).parent / "fixtures" / "mockup" / "photos").glob("*.jpg"))


@pytest.mark.parametrize("photo", MOCKUP_PHOTOS, ids=lambda p: p.stem)
def test_products_on_a_shelf_with_no_people_are_not_blurred(photo: Path) -> None:
    image = cv2.imread(str(photo))

    assert OpenCvPersonBlurrer().find_people(image) == []
