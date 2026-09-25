import os

def remove(p):
    try:
        os.remove(p)
    except FileNotFoundError:
        pass
