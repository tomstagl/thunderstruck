from myapp.models import Order

def export():
    return list(Order.objects.all())
