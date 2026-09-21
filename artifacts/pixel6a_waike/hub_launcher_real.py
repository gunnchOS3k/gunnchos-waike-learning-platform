import os
from pathlib import Path
from app.main import HubConfig, create_app
import uvicorn

db = Path(r'''/Users/gunnchos/Downloads/gunnchos-7gc-research-product-spine/repos/gunnchos-waike-learning-platform/.worktrees/pr21-real-gunnchai-ai-final-closure/services/hub/data/pixel_pilot/pilot.db''')
os.environ.pop("WAIKE_ALLOW_FAKE_AI", None)
os.environ["WAIKE_ALLOW_FAKE_AI"] = "0"
os.environ["GUNNCHAI_PROVIDER"] = "nearby_edge"
os.environ["GUNNCHAI_NEARBY_EDGE_URL"] = "http://127.0.0.1:8799"
os.environ["GUNNCHAI_NEARBY_MINT_URL"] = "http://127.0.0.1:8798"
os.environ["GUNNCHAI_ROOT"] = r'''/Users/gunnchos/Downloads/gunnchos-7gc-research-product-spine/repos/gunnchAI3k/.worktrees/pr54-llamacpp-cli-compat-closure'''
os.environ["WAIKE_PIXEL_PILOT"] = "true"
app = create_app(
    config=HubConfig(production_auth_enabled=True, fixture_auth_enabled=False, version="pixel-pilot-real"),
    db_path=db,
    seed=False,
)
from app.pilot.full_curriculum_seed import inventory_from_db, seed_full_curriculum
inv = inventory_from_db(app.state.db)
if not inv.get("all_18_loaded"):
    inv = seed_full_curriculum(app.state.db, identity=app.state.identity, sections=app.state.sections)
app.state.curriculum_inventory = inv
app.state.pixel_pilot = True
uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
