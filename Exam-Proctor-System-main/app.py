import importlib.util
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(PROJECT_ROOT, "exam_proctor")
APP_FILE = os.path.join(APP_DIR, "app.py")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

spec = importlib.util.spec_from_file_location("exam_proctor_app", APP_FILE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load app module from {APP_FILE}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
