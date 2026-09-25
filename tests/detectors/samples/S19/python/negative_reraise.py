import os

def write(path, data):
    f = open(path + ".tmp", "w")
    try:
        f.write(data)
    except:
        os.unlink(path + ".tmp")
        raise
