def draw_labels(canvas, labels, y):
    cursor = y + PADDING
    for i, label in enumerate(labels):
        cursor += LINE_HEIGHT
        canvas.add(Text(label, insert=(0, cursor - LINE_HEIGHT / 2)))


def draw_units(canvas, height, unit_height):
    for ru in range(0, height):
        y_offset = BORDER + ru * unit_height
        canvas.add(Rect(insert=(0, y_offset)))


def tokenize(source):
    cursor = 0
    while cursor < len(source):
        yield source[cursor]
        cursor += 1
