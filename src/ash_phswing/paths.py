"""Repository-relative locations of data and results."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DATA = os.path.join(ROOT, 'data')
PARAMS = os.path.join(DATA, 'parameters')
ASPEN = os.path.join(DATA, 'aspen')
POOL = os.path.join(DATA, 'pool')
RESULTS = os.path.join(ROOT, 'results')

DESIGN_FLOWSHEET = os.path.join(ASPEN, 'design_COMP_p130.json')
LADDER_DIR = os.path.join(ASPEN, 'ladder')
POOL_CSV = os.path.join(POOL, 'pool_261026n5.csv')


def results_dir(*sub):
    d = os.path.join(RESULTS, *sub)
    os.makedirs(d, exist_ok=True)
    return d
