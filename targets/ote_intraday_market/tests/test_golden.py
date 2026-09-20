"""Golden files load and point at existing fixtures; the platform runs the values."""

from pathlib import Path

from energy_platform.contracts.golden import load_golden

HERE = Path(__file__).parent


def test_goldens_reference_existing_fixtures() -> None:
    goldens = sorted((HERE / "golden").glob("*.yaml"))
    assert goldens
    for path in goldens:
        golden = load_golden(path)
        assert (HERE.parent / "fixtures" / golden.fixture).is_dir(), golden.fixture
