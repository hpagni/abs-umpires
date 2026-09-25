"""tests/model: register the `fast` marker that `make test-model-fast` selects.

pyproject.toml runs pytest with --strict-markers and registers only `network`, so an
unregistered `fast` mark would be a collection error. Owner: the model-tests lane.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "fast: an MT test that reads stored artefacts and refits nothing"
    )
