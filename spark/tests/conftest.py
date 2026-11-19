import os
import sys
from pathlib import Path

import pytest

SPARK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPARK_DIR))

import airlines_spark  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    session = airlines_spark.create_spark("airlines-spark-tests")
    yield session
    session.stop()
