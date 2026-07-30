"""Pure-logic tests for src/task_years.py's compute_total_years_experience."""

from __future__ import annotations

from datetime import date

from task_years import compute_total_years_experience


def test_empty_jobs_is_zero():
    assert compute_total_years_experience([]) == 0


def test_single_completed_job():
    jobs = [{"start_date": "2015-01-01", "end_date": "2019-01-01"}]
    assert compute_total_years_experience(jobs) == 4


def test_non_overlapping_jobs_sum():
    jobs = [
        {"start_date": "2015-01-01", "end_date": "2019-01-01"},
        {"start_date": "2020-01-01", "end_date": "2022-01-01"},
    ]
    assert compute_total_years_experience(jobs) == 6


def test_overlapping_concurrent_jobs_do_not_double_count():
    jobs = [
        {"start_date": "2020-01-01", "end_date": "2023-01-01"},
        {"start_date": "2021-01-01", "end_date": "2022-01-01"},  # fully inside the first
    ]
    assert compute_total_years_experience(jobs) == 3


def test_current_job_uses_as_of_date():
    jobs = [{"start_date": "2020-01-01", "current": True}]
    assert compute_total_years_experience(jobs, as_of=date(2024, 1, 1)) == 4


def test_missing_start_date_is_skipped_not_raised():
    jobs = [{"end_date": "2019-01-01"}, {"start_date": "2015-01-01", "end_date": "2019-01-01"}]
    assert compute_total_years_experience(jobs) == 4


def test_end_before_start_is_skipped():
    jobs = [{"start_date": "2020-01-01", "end_date": "2019-01-01"}]
    assert compute_total_years_experience(jobs) == 0


def test_unparseable_dates_are_skipped_not_raised():
    jobs = [{"start_date": "not-a-date", "end_date": "2019-01-01"}]
    assert compute_total_years_experience(jobs) == 0


def test_current_without_end_date_still_computed():
    jobs = [{"start_date": "2015-01-01", "current": True}]
    assert compute_total_years_experience(jobs, as_of=date(2020, 1, 1)) == 4


def test_non_current_job_missing_end_date_is_skipped():
    jobs = [{"start_date": "2015-01-01"}]
    assert compute_total_years_experience(jobs) == 0
