"""Tests for FanOutService — bidder masking, payload shape."""

from __future__ import annotations

from auction_app.services.fanout_service import mask_bidder_id


class TestFanOutService:
    def test_mask_bidder_id_length(self) -> None:
        """SHA256 hex prefix is always 8 chars."""
        masked = mask_bidder_id("550e8400-e29b-41d4-a716-446655440000")
        assert len(masked) == 8
        assert all(c in "0123456789abcdef" for c in masked)

    def test_mask_bidder_id_deterministic(self) -> None:
        """Same input yields same mask."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert mask_bidder_id(uid) == mask_bidder_id(uid)

    def test_mask_bidder_id_different(self) -> None:
        """Different inputs yield different masks."""
        uid1 = "550e8400-e29b-41d4-a716-446655440000"
        uid2 = "660e8400-e29b-41d4-a716-446655440001"
        assert mask_bidder_id(uid1) != mask_bidder_id(uid2)
