import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")
import pytest  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    from ifit.engine import Engine
    return Engine()
