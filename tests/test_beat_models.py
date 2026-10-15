import pytest

from music_studio.beat_models import beat_checkpoint


def test_optional_checkpoint_offline_and_integrity_errors(tmp_path):
    config = {"rhythm_checkpoint": "small0", "offline": True, "model_dir": str(tmp_path)}
    with pytest.raises(RuntimeError, match="missing offline"):
        beat_checkpoint(config)
    path = tmp_path / "beat_this/small0.ckpt"
    path.parent.mkdir()
    path.write_bytes(b"invalid model")
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        beat_checkpoint(config)
