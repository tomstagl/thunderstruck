from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=8)


def render_page(request):
    return executor.submit(build_page, request).result(timeout=5)


def nightly_export(rows):
    return list(executor.map(export_row, rows))
