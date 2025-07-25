from celery import Celery
from config import app

'''This file is to get celery workers up and running'''

celery = Celery(
    app.import_name,
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0',
    include=['tasks'],
)

celery.conf.update(
    timezone='Asia/Tehran',
    enable_utc=False,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json'
)


class ContextTask(celery.Task):
    """
    A custom Celery Task class that provides a Flask application context
    for each task execution. This is crucial when your tasks need access
    to Flask's `current_app` or other context-dependent features.
    """
    def __call__(self, *args, **kwargs):
        with app.app_context():
            return self.run(*args, **kwargs)


celery.Task = ContextTask


import tasks
