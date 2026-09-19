import numpy as np
import pytest
from numpy.testing import assert_allclose

from pkpd_lab import Scenario, simulate
from pkpd_lab.experiments import population, sensitivity, with_pk


def test_zero_variability_collapses_to_reference():
    s = Scenario()
    frame = population(s, subjects=4, clearance_cv=0, volume_cv=0)
    reference = simulate(s).frame.central_mg_l
    for col in ("p05_mg_l", "p50_mg_l", "p95_mg_l"):
        assert_allclose(frame[col], reference)


def test_population_reproducible_ordered_and_seed_sensitive():
    a = population(Scenario(), subjects=5, seed=17)
    b = population(Scenario(), subjects=5, seed=17)
    c = population(Scenario(), subjects=5, seed=18)
    assert a.equals(b)
    assert not a.equals(c)
    assert np.all(a.p05_mg_l <= a.p50_mg_l)
    assert np.all(a.p50_mg_l <= a.p95_mg_l)


def test_sensitivity_increasing_clearance_reduces_auc():
    frame = sensitivity(Scenario(), "clearance_l_h")
    assert np.all(np.diff(frame.auc_0_end_mg_h_l) < 0)
    assert_allclose(frame.factor, [0.8, 1, 1.2])


def test_invalid_experiments_fail_explicitly():
    with pytest.raises(ValueError):
        with_pk(Scenario(), bioavailability=1.2)
    with pytest.raises(ValueError):
        sensitivity(Scenario(), "unknown")
    with pytest.raises(ValueError):
        sensitivity(Scenario(), "absorption_lag_h")
    with pytest.raises(ValueError):
        population(Scenario(), subjects=1)
    with pytest.raises(ValueError):
        population(Scenario(), clearance_cv=-0.1)
