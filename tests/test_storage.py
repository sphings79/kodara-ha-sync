import os

import pytest

from custom_components.kodara_sync.storage import KodaraStore, StoreError

H = "a" * 64


@pytest.fixture
def store(tmp_path):
    s = KodaraStore(tmp_path / "k", quota_bytes=1000)
    s.prepare()
    return s


def test_prepare_makes_private_folders(store):
    assert (store.root / "devices").is_dir()
    assert (store.root / "files").is_dir()
    assert oct(os.stat(store.root).st_mode & 0o777) == "0o700"


@pytest.mark.parametrize(
    "path",
    [
        "../x",
        "devices/../../etc/passwd",
        "devices/a/b.snap",
        "files/short",
        f"files/{'A' * 64}",
        "view.json",
        "sync.json/",
        "/sync.json",
        "devices/x.txt",
        "",
    ],
)
def test_bad_paths_are_refused(store, path):
    with pytest.raises(StoreError) as err:
        store.write(path, b"x")
    assert err.value.status == 400
    with pytest.raises(StoreError):
        store.read(path)


def test_write_read_delete(store):
    store.write("sync.json", b"hello")
    assert store.read("sync.json") == (b"hello", 5)
    assert store.read("sync.json", 1, 3) == (b"ell", 5)
    assert oct(os.stat(store.root / "sync.json").st_mode & 0o777) == "0o600"
    store.delete("sync.json")
    store.delete("sync.json")
    with pytest.raises(StoreError) as err:
        store.read("sync.json")
    assert err.value.status == 404


def test_if_absent(store):
    store.write("sync.json", b"one", if_absent=True)
    with pytest.raises(StoreError) as err:
        store.write("sync.json", b"two", if_absent=True)
    assert err.value.status == 409
    assert store.read("sync.json")[0] == b"one"


def test_list_only_real_files(store):
    store.write("devices/aaa.snap", b"1")
    store.write("devices/bbb.snap", b"22")
    (store.root / "devices" / "junk.txt").write_bytes(b"x")
    store.write(f"files/{H}", b"333")
    names = [e["name"] for e in store.list("devices")]
    assert names == ["aaa.snap", "bbb.snap"]
    entry = store.list("devices")[1]
    assert entry["size"] == 2 and entry["modified"] > 0 and entry["version"]
    assert [e["name"] for e in store.list("files")] == [H]
    with pytest.raises(StoreError):
        store.list("..")


def test_chunked_upload(store):
    assert store.write("sync.json", b"ab", offset=0, total=6) is False
    assert not (store.root / "sync.json").exists()
    assert store.write("sync.json", b"cd", offset=2, total=6) is False
    assert store.write("sync.json", b"ef", offset=4, total=6) is True
    assert store.read("sync.json") == (b"abcdef", 6)
    assert not (store.root / "sync.json.part").exists()


def test_chunks_must_come_in_order(store):
    store.write("sync.json", b"ab", offset=0, total=6)
    with pytest.raises(StoreError) as err:
        store.write("sync.json", b"ef", offset=4, total=6)
    assert err.value.status == 409
    with pytest.raises(StoreError) as err:
        store.write("sync.json", b"ab", offset=0, total=1)
    assert err.value.status == 400


def test_restarting_an_upload_discards_the_old_part(store):
    store.write("sync.json", b"xx", offset=0, total=4)
    store.write("sync.json", b"ab", offset=0, total=4)
    assert store.write("sync.json", b"cd", offset=2, total=4) is True
    assert store.read("sync.json")[0] == b"abcd"


def test_quota(store):
    store.write(f"files/{H}", b"x" * 900)
    with pytest.raises(StoreError) as err:
        store.write("devices/a.snap", b"y" * 200)
    assert err.value.status == 507
    # Replacing a file counts only the difference.
    store.write(f"files/{H}", b"z" * 950)
    with pytest.raises(StoreError) as err:
        store.write("devices/a.snap", b"y" * 100, offset=0, total=100)
    assert err.value.status == 507


def test_view_file_is_separate_and_not_counted(store):
    assert store.read_view() is None
    store.write_view(b"x" * 5000)
    assert store.read_view() == b"x" * 5000
    assert store.used_bytes() == 0
    store.delete_view()
    assert store.read_view() is None
