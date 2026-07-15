"""Tests for the SQLite-backed JobRegistry (restart durability + field round-trip)."""

import pytest

from service.jobs import Job, JobRegistry


def _reg(tmp_path):
    return JobRegistry(db_path=tmp_path / "jobs.db")


def test_create_get_roundtrip(tmp_path):
    reg = _reg(tmp_path)
    job = reg.create(game_id="3_cash_paradise", mode="prod", publishable=True)
    got = reg.get(job.id)
    assert isinstance(got, Job)
    assert got.id == job.id and got.game_id == "3_cash_paradise"
    assert got.mode == "prod" and got.publishable is True
    assert got.status == "queued" and got.local_available is True


def test_get_and_update_unknown(tmp_path):
    reg = _reg(tmp_path)
    assert reg.get("nope") is None
    assert reg.update("nope", status="succeeded") is None


def test_update_scalar_list_and_dict_fields(tmp_path):
    reg = _reg(tmp_path)
    job = reg.create(game_id="g", mode="prod", publishable=True)
    reg.update(job.id, status="running")
    updated = reg.update(
        job.id,
        status="succeeded",
        files=["index.json", "books_base.jsonl.zst", "lookUpTable_base_0.csv"],
        deploy_status="uploaded",
        s3_files=[{"name": "index.json", "url": "https://cdn/x/index.json"}],
        events_file={"name": "books_events.json", "url": "https://cdn/x/books_events.json"},
        local_available=False,
    )
    # returned object reflects the update
    assert updated.status == "succeeded" and updated.deploy_status == "uploaded"
    assert updated.local_available is False
    # re-fetch: list + dict fields round-tripped through JSON intact
    got = reg.get(job.id)
    assert got.files == ["index.json", "books_base.jsonl.zst", "lookUpTable_base_0.csv"]
    assert got.s3_files[0]["url"] == "https://cdn/x/index.json"
    assert got.events_file["name"] == "books_events.json"


def test_unknown_field_raises(tmp_path):
    reg = _reg(tmp_path)
    job = reg.create(game_id="g", mode="dev", publishable=False)
    with pytest.raises(ValueError):
        reg.update(job.id, bogus_field=1)


def test_to_public_hides_server_paths(tmp_path):
    reg = _reg(tmp_path)
    job = reg.create(game_id="g", mode="dev", publishable=False)
    reg.update(job.id, zip_path="/app/x/publish.zip", events_path="/app/x/books_events.json")
    pub = reg.get(job.id).to_public()
    assert "zip_path" not in pub and "events_path" not in pub
    assert "events_file" in pub  # public S3 descriptor is kept


def test_restart_durability(tmp_path):
    # First "process": create + finish a job.
    reg1 = _reg(tmp_path)
    job = reg1.create(game_id="durable", mode="prod", publishable=True)
    reg1.update(job.id, status="succeeded", s3_files=[{"name": "index.json", "url": "u"}])

    # Second "process": a fresh registry on the SAME db file still sees it.
    reg2 = _reg(tmp_path)
    got = reg2.get(job.id)
    assert got is not None
    assert got.status == "succeeded"
    assert got.s3_files[0]["url"] == "u"
    assert [j.id for j in reg2.list()] == [job.id]
