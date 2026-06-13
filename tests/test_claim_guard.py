from msquared_agent.claim_guard import check_claims

def test_forbidden_claims():
    high_risk_text = "M² proves truth about the model."
    risk, risks = check_claims(high_risk_text)
    assert risk == "block"
    assert len(risks) > 0


def test_diia_certification_claims_are_blocked():
    risk, risks = check_claims("DIIaC certifies compliance for this decision.")
    assert risk == "block"
    assert "diia_certifies_compliance" in risks

def test_safe_content():
    safe_text = "DIIaC helps with governed decisions."
    risk, risks = check_claims(safe_text)
    assert risk == "low"
