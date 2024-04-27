from json import JSONEncoder, dumps
from typing import Any
import numpy as np

class NumpyEncoder(JSONEncoder):
    def default(self, obj: object) -> Any:
        if isinstance(obj, np.integer):
            return int(obj)

        if isinstance(obj, np.floating):
            return float(obj)

        if isinstance(obj, np.ndarray):
            return obj.tolist()

        return super(NumpyEncoder, self).default(obj)

def serialize(data: np.ndarray) -> str:
    return dumps(data, cls=NumpyEncoder)