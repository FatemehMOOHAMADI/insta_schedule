from celery_worker import celery
import instagrapi
from config import os
import logging

"""This file is to define celery tasks"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

logger = logging.getLogger(__name__)


@celery.task(bind=True, retry=3, retry_backoff=True)
def upload_to_instagram(self, relative_path_image, caption, username, password):
    try:

        abs_path = os.path.join(STATIC_DIR, relative_path_image)

        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Image file not found at {abs_path}")

        client = instagrapi.Client()

        session_dir = f"sessions"
        os.makedirs(session_dir, exist_ok=True)
        session_file = os.path.join(session_dir, f"{username}.json")

        if os.path.exists(session_file):
            try:
                client.load_settings(session_file)
                client.login(username, password)
            except Exception as e:
                logger.warning(f"Failed to load or use session for {username}: {e}. Attempting full login.")
                client.login(username, password)
                client.dump_settings(session_file)

        else:
            client.login(username, password)
            client.dump_settings(session_file)

        post_id = client.photo_upload(path=abs_path, caption=caption)
        return {
            "success": True,
            "message": "Post uploaded to insta",
            "post_id": post_id.pk,
            "username": username,
        }

    except instagrapi.exceptions.LoginRequired as e:
        logger.error(f"Login failed for {username}: {str(e)}")
        # Do not retry for a login error, as it's a permanent issue
        raise e
    except Exception as e:
        logger.error(f"the uploading failed {str(e)}")
        raise self.retry(exc=e, countdown=60)
