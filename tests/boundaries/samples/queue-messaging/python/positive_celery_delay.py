# own-packages: proj
from celery import shared_task

from proj.models import User


@shared_task
def send_welcome(user_id):
    return user_id


def register(email):
    user = User.create(email)
    send_welcome.delay(user.id)  # boundary: queue/messaging
    return user
