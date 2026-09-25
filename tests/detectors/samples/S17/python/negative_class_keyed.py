class NestedField:
    def __init__(self):
        self._serializer_cache = {}

    def to_representation(self, instance):
        if instance.__class__ not in self._serializer_cache:
            self._serializer_cache[instance.__class__] = serializer_for(instance)
        return self._serializer_cache[instance.__class__].to_representation(instance)
