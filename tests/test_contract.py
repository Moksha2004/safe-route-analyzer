from app.models.schemas import AnalyzeResponse
from app.models.schemas import AnalyzeRequest


def test_contract_disallows_safety_claims_and_requires_limitations():
    payload = {"routes": [], "parsedPreferences": {}, "safetyClaims": False, "limitations": ["not crime data"], "dataLimitations": ["not crime data"]}
    response = AnalyzeResponse.model_validate(payload)
    assert response.safetyClaims is False
    assert response.limitations


def test_default_route_count_is_three():
    request = AnalyzeRequest(start="Bellandur", destination="Marathahalli")
    assert request.maxRoutes == 3
