import importlib
import importlib.util


def import_module(path: str, name: str = "__main__"):
    try:
        return importlib.import_module(path)
    except ImportError:
        pass

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module
