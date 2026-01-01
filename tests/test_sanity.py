def test_environment_sanity():
    assert True

def test_import_sanity():
    try:
        import insomnia_run
    except ImportError:
        assert False, "insomnia_run package not found. Did you run 'pip install -e .'?"
