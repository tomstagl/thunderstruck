from django.views.generic import ListView

from .models import Region


class RegionListView(ListView):
    queryset = Region.objects.all()
    paginate_by = 50


def tag_names(obj):
    return [tag.name for tag in obj.tags.all()]
