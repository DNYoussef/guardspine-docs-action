"""Tests for docsync evidence pack hash chain integrity."""

from docsync.claims import ClaimResult, ClaimStatus, EvidenceRef
from docsync.evidence import DocEvidencePack


def test_empty_pack_verifies():
    pack = DocEvidencePack(manifest_hash="abc123")
    ok, msg = pack.verify()
    assert ok is True
    assert msg == "ok"


def test_single_claim_chain():
    result = ClaimResult(
        claim_id="c0001",
        claim_text="API uses JWT",
        status=ClaimStatus.PASS,
        evidence=[EvidenceRef(source_type="code", path="auth.py", line=10, matched=True)],
        message="1/1 evidence found",
    )
    pack = DocEvidencePack(manifest_hash="deadbeef", results=[result])
    chain = pack.build_hash_chain()
    assert len(chain) == 1

    ok, msg = pack.verify()
    assert ok is True
    assert msg == "ok"


def test_multi_claim_chain():
    results = [
        ClaimResult(claim_id=f"c{i:04d}", claim_text=f"Claim {i}", status=ClaimStatus.PASS)
        for i in range(5)
    ]
    pack = DocEvidencePack(manifest_hash="test", results=results)
    pack.build_hash_chain()

    assert len(pack.hash_chain) == 5
    ok, msg = pack.verify()
    assert ok is True


def test_tampered_chain_fails():
    results = [
        ClaimResult(claim_id="c0000", claim_text="Original", status=ClaimStatus.PASS),
        ClaimResult(claim_id="c0001", claim_text="Second", status=ClaimStatus.FAIL),
    ]
    pack = DocEvidencePack(manifest_hash="test", results=results)
    pack.build_hash_chain()

    # Tamper with chain
    pack.hash_chain[0] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    ok, msg = pack.verify()
    assert ok is False
    assert "hash mismatch" in msg


def test_to_json_roundtrip():
    result = ClaimResult(
        claim_id="c0000",
        claim_text="Port is 8080",
        status=ClaimStatus.FAIL,
        message="no matching evidence found",
    )
    pack = DocEvidencePack(manifest_hash="aaa", results=[result])
    json_str = pack.to_json()

    assert '"claim_id": "c0000"' in json_str
    assert '"status": "fail"' in json_str
    assert "immutability_proof" in json_str


def test_immutability_proof_has_root_hash():
    results = [
        ClaimResult(claim_id="c0000", claim_text="Test", status=ClaimStatus.PASS),
    ]
    pack = DocEvidencePack(manifest_hash="xyz", results=results)
    pack.build_hash_chain()

    assert "root_hash" in pack.immutability_proof
    assert pack.immutability_proof["root_hash"].startswith("sha256:")
