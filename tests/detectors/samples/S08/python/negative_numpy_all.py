import numpy as np

def check(a, b):
    mask = np.isclose(a, b)
    return mask.all()
