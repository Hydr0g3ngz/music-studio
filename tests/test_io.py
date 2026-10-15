from concurrent.futures import ThreadPoolExecutor

from music_studio.io import read_json, write_json


def test_concurrent_atomic_writers_never_publish_partial_json(tmp_path):
    path = tmp_path / "job.json"
    write_json(path, {"writer": -1, "count": -1})

    def writer(identifier):
        for count in range(25):
            write_json(path, {"writer": identifier, "count": count})
            assert set(read_json(path)) == {"writer", "count"}

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(writer, range(3)))
    assert read_json(path)["count"] == 24
    assert list(tmp_path.glob("*.tmp")) == []
