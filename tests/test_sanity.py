def test_import_sanity():
    module = __import__("insomnia_run")

    assert module is not None
