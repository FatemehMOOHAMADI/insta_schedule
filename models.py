from config import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

""" this file is for database models """


class Users(db.Model):
    __tablename__ = 'Users'

    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(80), unique=True, nullable=False)
    username_insta = db.Column(db.String(120), unique=False, nullable=False)
    password_insta = db.Column(db.String(120), nullable=False)
    password = db.Column(db.String(200), nullable=False)

    post = db.relationship("Post_insta", back_populates="user", lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def to_json(self):
        return {
            "id": self.id,
            "user_name": self.user_name,
            "username_insta": self.username_insta
        }


class Post_insta(db.Model):
    __tablename__ = 'Post_insta'

    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(600), nullable=True, default="")
    schedule_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    task_id = db.Column(db.String(100), nullable=True)
    instagram_post_id = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("Users.id"), nullable=False)
    user = db.relationship("Users", back_populates="post")

    def to_json(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "scheduled": self.schedule_time.isoformat(),
            "caption": self.caption,
            "path": self.path,
            "status": self.status,
            "task_id": self.task_id,
            "instagram_post_id": self.instagram_post_id,
        }
