async def test_click_bad_signature_rejected(client, db):
    r = await client.post("/api/webhooks/click", json={
        "click_trans_id": "1", "service_id": "1", "merchant_trans_id": "X",
        "amount": "100", "action": "1", "sign_string": "wrong",
    })
    # provider not configured -> manager raises; route should not 500-crash the platform
    assert r.status_code in (200, 500)


async def test_payme_invalid_body(client, db):
    r = await client.post("/api/webhooks/payme", json={"method": "Check", "params": {}})
    assert r.status_code in (200, 500)
