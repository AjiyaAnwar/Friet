import pytest
from decimal import Decimal
from app.services.lcl_service import LCLService
from app.repositories.lcl_repository import LCLRepositoryFake
from app.schemas.lcl import ConsolidationCreate

@pytest.fixture
def repo():
    return LCLRepositoryFake()

@pytest.fixture
def service(repo):
    return LCLService(repo)

def test_generate_suggestions(service):
    suggestions = service.generate_suggestions()
    
    assert len(suggestions) > 0
    
    # Check suggestion for mbl-1
    mbl_1_sugg = next(s for s in suggestions if s.mbl_id == 'mbl-1')
    assert mbl_1_sugg.total_weight == Decimal('19000.00') # hbl-1 (5000) + hbl-2 (12000) = 17000? Wait, hbl-3 is 4000. So 5000+12000=17000, +4000=21000 > 20000. So hbl-1 and hbl-2 only. Total weight: 17000.
    # Let me calculate exactly:
    # mbl-1 max weight 20000, cbm 30
    # hbl-1: 5000, 10
    # hbl-2: 12000, 15
    # hbl-3: 4000, 5
    # sorted: hbl-1 (added -> 5000, 10)
    # hbl-2 (added -> 17000, 25)
    # hbl-3 (not added, 17000+4000=21000 > 20000)
    assert mbl_1_sugg.hbl_ids == ['hbl-1', 'hbl-2']
    assert mbl_1_sugg.total_weight == Decimal('17000.00')
    assert mbl_1_sugg.total_cbm == Decimal('25.00')
    assert mbl_1_sugg.weight_utilization == Decimal('85.00') # 17000 / 20000 = 0.85
    assert mbl_1_sugg.cbm_utilization == Decimal('83.33') # 25 / 30 = 0.8333...
    
    # Check suggestion for mbl-2
    mbl_2_sugg = next(s for s in suggestions if s.mbl_id == 'mbl-2')
    assert mbl_2_sugg.hbl_ids == ['hbl-4']
    assert mbl_2_sugg.total_weight == Decimal('10000.00')
    assert mbl_2_sugg.weight_utilization == Decimal('40.00')
    assert mbl_2_sugg.cbm_utilization == Decimal('33.33')

def test_calculate_cost_allocation(service, repo):
    consolidation = service.create_consolidation(ConsolidationCreate(
        mbl_id='mbl-1',
        hbl_ids=['hbl-1', 'hbl-2']
    ))
    
    allocation = service.calculate_cost_allocation(consolidation.id)
    
    # mbl-1 cost: 5000
    # hbl-1 weight: 5000, cbm: 10 -> cw = max(5000, 10000) = 10000
    # hbl-2 weight: 12000, cbm: 15 -> cw = max(12000, 15000) = 15000
    # total cw: 25000
    
    # hbl-1 ratio: 10000/25000 = 0.4 -> 5000 * 0.4 = 2000.00
    # hbl-2 ratio: 15000/25000 = 0.6 -> 5000 * 0.6 = 3000.00
    
    assert allocation.total_cost == Decimal('5000.00')
    assert len(allocation.allocations) == 2
    
    alloc_1 = next(a for a in allocation.allocations if a.hbl_id == 'hbl-1')
    assert alloc_1.allocated_cost == Decimal('2000.00')
    
    alloc_2 = next(a for a in allocation.allocations if a.hbl_id == 'hbl-2')
    assert alloc_2.allocated_cost == Decimal('3000.00')
