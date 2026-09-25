class Serializer:
    def to_representation(self, data):
        if data:
            cache = {}
            for item in data:
                cache[item.pk] = item
            return [cache[pk] for pk in sorted(cache)]
        return []
