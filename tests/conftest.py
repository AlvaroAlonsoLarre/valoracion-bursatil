import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
import pytest
from modelo_fundamental import build_fundamental_model

@pytest.fixture
def model_inputs():
    annual=pd.DataFrame({
      'Ingresos':[300.,360.,400.], 'Beneficio operativo':[90.,108.,120.],
      'Beneficio neto':[67.5,81.,90.], 'D&A':[30.,36.,40.], 'CAPEX':[45.,54.,60.],
      'Tasa fiscal':[.25]*3,'Deuda total':[50.,50.,50.],'Deuda neta':[20.,20.,20.],
      'EPS diluido':[6.75,8.1,9.], 'Flujo de caja operativo':[90.,108.,120.],
      'Dividendos':[6.,7.2,8.], 'Recompras de acciones':[3.,3.6,4.],
      'Gastos por intereses':[2.5]*3, 'Capital invertido aproximado':[80.,100.,120.],
      'NOPAT aproximado':[67.5,81.,90.]},index=[2023,2024,2025])
    q=pd.DataFrame({c:[annual.loc[2025,c]/4]*4 for c in annual},index=pd.date_range('2025-03-31',periods=4,freq='QE'))
    return dict(annual=annual,peers=pd.DataFrame(),price=100.,market_cap=1000.,
      shares_outstanding=10.,financial_currency='USD',quote_currency='USD',fx=1.,
      quarterly=q,fiscal_end_date='2025-12-31',as_of='2026-01-15',ticker='OTHER',info={'beta':1.})

@pytest.fixture
def build(model_inputs):
    return lambda **changes: build_fundamental_model(**{**model_inputs,**changes})
