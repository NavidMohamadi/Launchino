from source_classification import classify_vacancy_url


def test_greenhouse_url_routes_to_api():
    result = classify_vacancy_url("https://boards.greenhouse.io/example/jobs/123")
    assert result.source_id == "greenhouse_public_api"
    assert result.board_identifier == "example"


def test_lever_url_routes_to_api():
    result = classify_vacancy_url("https://jobs.lever.co/example/abc")
    assert result.source_id == "lever_public_api"
    assert result.board_identifier == "example"


def test_linkedin_is_blocked_direct_source():
    result = classify_vacancy_url("https://www.linkedin.com/jobs/view/123")
    assert result.classification == "blocked_direct_source"
    assert result.source_id == "linkedin_direct"
