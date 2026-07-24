from match_engine import aggregate_match, make_item_result, make_not_scored_item_result, rank_match_results
from schemas import Alignment, Category, MatchConfiguration, NotScoredReason, RequirementType, ResultLane, UnknownReason


def cfg():
    return MatchConfiguration(vacancy_id='V',category_weights={
        Category.PRACT:10,Category.CAP:30,Category.TASK:20,Category.TEAM:15,Category.CAREER:5,Category.MOT:10,Category.ENV:10})


def test_not_scored_does_not_reduce_coverage():
    items=[
        make_item_result(talent_id='A',vacancy_id='V',element_id='MOT-LEARN',category=Category.MOT,alignment=Alignment.ALIGNED,item_importance=5,requirement_type=RequirementType.IMPORTANT,reason='ok'),
        make_not_scored_item_result(talent_id='A',vacancy_id='V',element_id='MOT-RECOGNITION',category=Category.MOT,not_scored_reason=NotScoredReason.NOT_TOP_FIVE),
    ]
    r=aggregate_match(talent_id='A',vacancy_id='V',item_results=items,config=cfg())
    mot=next(x for x in r.category_results if x.category==Category.MOT)
    assert mot.coverage_percent==100.0 and mot.not_scored_item_count==1


def test_unknown_activated_reduces_coverage_and_lane():
    items=[
        make_item_result(talent_id='A',vacancy_id='V',element_id='PRACT-START',category=Category.PRACT,alignment=Alignment.ALIGNED,item_importance=5,requirement_type=RequirementType.IMPORTANT,reason='ok'),
        make_item_result(talent_id='A',vacancy_id='V',element_id='PRACT-SPONSOR',category=Category.PRACT,alignment=Alignment.UNKNOWN,item_importance=5,requirement_type=RequirementType.IMPORTANT,reason='silent',unknown_reason=UnknownReason.VACANCY_NOT_SPECIFIED),
    ]
    r=aggregate_match(talent_id='A',vacancy_id='V',item_results=items,config=cfg())
    assert r.overall_coverage_percent==50.0 and r.lane==ResultLane.CLARIFICATION_REQUIRED


def test_critical_mismatch_has_critical_lane():
    item=make_item_result(talent_id='C',vacancy_id='V',element_id='CAP-CERT',category=Category.CAP,alignment=Alignment.MISALIGNED,item_importance=5,requirement_type=RequirementType.CRITICAL,reason='gap')
    r=aggregate_match(talent_id='C',vacancy_id='V',item_results=[item],config=cfg())
    assert r.lane==ResultLane.CRITICAL_REVIEW


def test_priority_lane_outranks_clarification():
    clean=aggregate_match(talent_id='B',vacancy_id='V',item_results=[make_item_result(talent_id='B',vacancy_id='V',element_id='CAP-X',category=Category.CAP,alignment=Alignment.ALIGNED,item_importance=5,requirement_type=RequirementType.IMPORTANT,reason='ok')],config=cfg())
    unclear=aggregate_match(talent_id='A',vacancy_id='V',item_results=[make_item_result(talent_id='A',vacancy_id='V',element_id='CAP-X',category=Category.CAP,alignment=Alignment.UNKNOWN,item_importance=5,requirement_type=RequirementType.IMPORTANT,reason='unknown',unknown_reason=UnknownReason.REQUIRES_VERIFICATION)],config=cfg())
    assert rank_match_results([unclear,clean])[0].talent_id=='B'
