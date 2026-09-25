from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=8)

def submit(fn, *a):
    return executor.submit(fn, *a)
