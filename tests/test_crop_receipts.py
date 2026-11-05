"""Tests for collision-safe receipt crop output handling."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src import crop_receipts as crop_module


class _Box:
    xyxy = np.array([[10, 10, 40, 40]])


class _Boxes:
    def cpu(self):
        return self

    def numpy(self):
        return [_Box()]


class _Model:
    def __init__(self, _model_path):
        pass

    def __call__(self, _image):
        return [SimpleNamespace(boxes=_Boxes())]


def test_single_image_crop_uses_source_name_and_refuses_overwrite(
    tmp_path, monkeypatch
):
    source = tmp_path / "receipt.jpg"
    source.touch()
    output = tmp_path / "crops"
    monkeypatch.setattr(crop_module, "YOLO", _Model)
    monkeypatch.setattr(
        crop_module.cv2, "imread", lambda _path: np.ones((60, 60, 3), dtype=np.uint8)
    )
    monkeypatch.setattr(
        crop_module.cv2,
        "imwrite",
        lambda path, _image: (Path(path).touch() is None),
    )

    first = crop_module.crop_receipts_for_images("model.pt", [source], output)
    second = crop_module.crop_receipts_for_images("model.pt", [source], output)

    assert first[0].error is None
    assert first[0].receipt_paths[0].name.startswith("receipt_")
    assert second[0].receipt_paths == ()
    assert "Refusing to overwrite" in second[0].error


def test_same_named_images_from_different_sources_get_distinct_outputs(
    tmp_path, monkeypatch
):
    first_source = tmp_path / "one" / "receipt.jpg"
    second_source = tmp_path / "two" / "receipt.jpg"
    first_source.parent.mkdir()
    second_source.parent.mkdir()
    first_source.touch()
    second_source.touch()
    monkeypatch.setattr(crop_module, "YOLO", _Model)
    monkeypatch.setattr(
        crop_module.cv2, "imread", lambda _path: np.ones((60, 60, 3), dtype=np.uint8)
    )
    monkeypatch.setattr(
        crop_module.cv2,
        "imwrite",
        lambda path, _image: (Path(path).touch() is None),
    )

    results = crop_module.crop_receipts_for_images(
        "model.pt", [first_source, second_source], tmp_path / "crops"
    )

    assert all(result.error is None for result in results)
    assert results[0].receipt_paths[0].name != results[1].receipt_paths[0].name
