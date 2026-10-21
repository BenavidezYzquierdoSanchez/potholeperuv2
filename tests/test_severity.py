from backend.core import add_visual_severity
import pytest

def test_visual_severity_boundaries():
    rows=[{'area_mascara_px':0},{'area_mascara_px':20},{'area_mascara_px':100},{'area_mascara_px':300}]
    assert [r['severidad_visual'] for r in add_visual_severity(rows,100,100)]==['sin_mascara','baja','media','alta']

def test_visual_severity_invalid_thresholds():
    with pytest.raises(ValueError):add_visual_severity([],100,100,.1,.05)
