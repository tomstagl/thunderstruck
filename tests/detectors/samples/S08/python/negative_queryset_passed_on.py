from django.shortcuts import get_object_or_404

from .models import Dashboard, Region


class RegionListView(ObjectListView):
    queryset = add_related_count(
        Region.objects.all(),
        Site,
        "region",
        "site_count",
    )


def dashboard(request):
    return get_object_or_404(Dashboard.objects.all(), user=request.user)


def field_kwargs(model):
    return {"queryset": model.objects.all()}
