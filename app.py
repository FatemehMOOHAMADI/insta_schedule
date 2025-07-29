from flask_jwt_extended.exceptions import JWTExtendedException
from config import (app, db, Resource, api, request, create_access_token, jwt_required,
                    make_response, send_file, tehran, os, get_jwt_identity, jsonify)
from models import Users, generate_password_hash, check_password_hash, Post_insta
from flask_jwt_extended import unset_jwt_cookies
from tasks import upload_to_instagram, delete_instagram_post
from datetime import datetime
from celery_worker import celery
from werkzeug.utils import secure_filename
import jdatetime


# convert to persian calendar
def convert_jalali_to_gregorian(jalali_date_str, time_str):
    year, month, day = map(int, jalali_date_str.split('-'))
    hour, minute = map(int, time_str.split(':'))

    gregorian = jdatetime.datetime(year, month, day, hour, minute).togregorian()
    localized_datetime = tehran.localize(
        datetime(gregorian.year, gregorian.month, gregorian.day, gregorian.hour, gregorian.minute))
    return localized_datetime


# allowed extensions for the images in app
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# specify the allowed files, both useful in dashboard and edit module
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


class UserRegister(Resource):
    """
    register the users
    """

    def get(self):
        app.logger.info("access register route")
        return {"message": "this form is registering users"}, 200

    def post(self):
        data = request.get_json()

        # ask for the users username for our service
        if 'user_name' not in data:
            return {"message": "your user name is missing"}, 400

        # check if the chosen username already exits in the database
        if Users.query.filter_by(user_name=data['user_name']).first():
            return {"message": "user already exists"}, 400

        # check if the user has input the instagram username and password fields
        if 'username_insta' not in data:
            return {"message": "you have missed to input your instagram id "}, 400

        if 'password_insta' not in data:
            return {"message": "you have missed to input your instagram password"}, 400

        # check for the password fields
        if 'password' not in data:
            return {"message": "your password is missing"}, 400

        if 'confirm' not in data:
            return {"message": "your password confirmation is missing"}, 400

        # check if the fields are empty
        if not data['user_name'] or data['user_name'] == "":
            return {"message": "please enter your user name"}, 400

        if not data['username_insta'] or data['username_insta'] == "":
            return {"message": "please enter your instagram username"}, 400

        if not data['password_insta'] or data['password_insta'] == "":
            return {"message": "please enter your instagram password"}, 400

        if not data['password'] or data['password'] == "":
            return {"message": "please enter your password"}, 400

        if not data['confirm'] or data['confirm'] == "":
            return {"message": "please confirm your password"}, 400

        # check if the password and confirm match
        if data['password'] != data['confirm']:
            return {"message": "your password doesn't match. try again!"}, 400

        # convert password to hash
        new_password_hash = generate_password_hash(data['password'])
        # save the username and password to the database
        new_user = Users(
            user_name=data['user_name'],
            username_insta=data['username_insta'],
            password_insta=data['password_insta'],
            password=new_password_hash)

        try:
            db.session.add(new_user)
            db.session.commit()

            app.logger.info("user registered successfully")
            return {"message": "user created"}, 201
        except Exception as e:
            app.logger.info(str(e))
            return {"message": str(e)}, 404


class UserLogin(Resource):
    """
    login the user
    """

    def get(self):
        app.logger.info("get the login page")
        return {"message": "access to login page"}, 200

    def post(self):
        data = request.get_json()

        # check for the fields
        if 'user_name' not in data:
            return {"message": "user name missing"}, 400

        if 'password' not in data:
            return {"message": "password missing"}, 400

        user = Users.query.filter_by(user_name=data['user_name']).first()

        if not user:
            return {"message": "user not found"}, 404

        # check if the fields are empty
        if not data['user_name'] or data['user_name'] == "":
            return {"message": "please enter a valid user name"}, 404

        if not data['password'] or data['password'] == "" or not check_password_hash(user.password, data['password']):
            return {"message": "please enter a valid password"}, 400

        access_token = create_access_token(identity=str(user.id))

        response = make_response({
            "message": "you are logged in",
            "access_token": access_token,
            "user_id": user.id,
            "user_name": user.user_name,
        }, 200)

        # Set cookies if needed
        response.set_cookie(
            'access_token_cookie',
            value=access_token,
            httponly=True,
            samesite='Lax',
            secure=app.config.get('ENV') == 'production'
        )

        app.logger.info("user logged in")
        return response


class UserDashboard(Resource):
    """
    upload and schedule post
    """

    method_decorators = {
        'get': [jwt_required()],
        'post': [jwt_required()],
    }

    def get(self, user_name):
        current_user_id = get_jwt_identity()
        current_user_obj = Users.query.get(current_user_id)

        if not current_user_obj:
            return {"message": "user not FOUND!"}, 404

        if current_user_obj.user_name != user_name:
            return {"message": "Access denied, you are not the user"}, 403

        app.logger.info("GET request to UserDashboard. Instructing to use POST for actions.")
        return {"message": "access dashboard"}, 200

    def post(self, user_name):

        user_id = get_jwt_identity()
        current_user_obj = Users.query.get(user_id)

        if not current_user_obj:
            return {"message": "user not FOUND!"}, 404

        # receive the image
        if 'image' not in request.files:
            return {"message": "please upload photo"}, 400

        file = request.files['image']

        caption = request.form.get('caption')
        jalali_date = request.form.get("jalali_date")
        time_str = request.form.get("schedule_time")

        if not file or file.filename == "":
            return {"message": "file invalid"}, 400

        if not caption or caption == "":
            return {"message": "please enter caption of the post"}, 400

        if not jalali_date or jalali_date == "":
            return {"message": "please set a date for uploading your post"}, 400

        if not time_str or time_str == "":
            return {"message": "please set the time for uploading your post"}, 400

        try:

            # save the photos that user sends in a folder
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(app.static_folder, 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            file_path = os.path.join(upload_folder, filename)
            relative_path = os.path.join('uploads', filename)

            if not allowed_file(file.filename):
                return {"message": "invalid file type"}, 400

            file.save(file_path)

            # set the time to tehran local time
            run_at = convert_jalali_to_gregorian(jalali_date, time_str)

            # make the task
            task = upload_to_instagram.apply_async(
                args=[relative_path, caption, current_user_obj.username_insta, current_user_obj.password_insta],
                eta=run_at,
            )

            new_post = Post_insta(
                user_id=current_user_obj.id,
                path=relative_path,
                caption=caption,
                schedule_time=run_at,
                status="scheduled",
                task_id=task.id,
            )

            db.session.add(new_post)
            db.session.commit()

            app.logger.info("post created")
            return {
                "message": "the post is uploaded",
                "post_id": new_post.id,
                "task_id": task.id,
            }, 200

        except Exception as e:
            app.logger.info("could not create the post")
            return {"message": str(e)}, 400


class UserHistory(Resource):
    """Get user's post history with task status"""

    method_decorators = {
        'get': [jwt_required()],
    }

    def get(self, user_name):

        # identify the user
        user_id = get_jwt_identity()
        current_user_obj = Users.query.get(user_id)

        if not current_user_obj:
            return {"message": "user not FOUND!"}, 404

        # get the post information from database
        user_posts = Post_insta.query.filter_by(user_id=user_id).order_by(Post_insta.schedule_time.desc()).all()

        # iterate over each post to get each field to show status of each task
        posts_data = []
        for post in user_posts:

            current_post_error = None
            post_status_updated = False

            # Check Celery task status if task_id exists
            if post.task_id and post.status == "scheduled":
                task = celery.AsyncResult(post.task_id)

                # Update post status in database if task completed
                if task.ready():
                    if task.successful():
                        post.status = "success"
                        if isinstance(task.result, dict) and "post_id" in task.result:
                            post.instagram_post_id = str(task.result.get("post_id"))
                    else:
                        post.status = "failed"
                        current_post_error = str(task.result)

                    post_status_updated = True

                if post_status_updated:
                    try:
                        db.session.commit()
                    except Exception as e:
                        app.logger.info(f"error committing post status update for post {post.id}: {str(e)}")
                        db.session.rollback()

            post_data = post.to_json()

            # show the status of each task
            if post.task_id:
                task = celery.AsyncResult(post.task_id)
                post_data["task_status"] = task.status

                if current_post_error == "failed":
                    post_data["error"] = current_post_error

                elif task.failed():
                    post_data["error"] = str(task.result)

            # display the time according to tehran timezone
            schedule_time = post.schedule_time.astimezone(tehran)
            jalali_datetime = jdatetime.datetime.fromgregorian(datetime=schedule_time)
            post_data["jalali_scheduled"] = jalali_datetime.strftime("%Y-%m-%d %H:%M")

            posts_data.append(post_data)

        app.logger.info("get the history page")
        return posts_data, 200


class UserPostDelete(Resource):

    """
    this route is for deleting posts
    """

    method_decorators = {
        'delete': [jwt_required()],
    }

    def delete(self, post_id):
        user_id = get_jwt_identity()
        current_user_obj = Users.query.get(user_id)

        if not current_user_obj:
            return {"message": "user not FOUND!"}, 404

        post_to_delete = Post_insta.query.filter_by(id=post_id, user_id=user_id).first()

        if not post_to_delete:
            return {"message": "post not found"}, 404

        try:
            if post_to_delete.path and os.path.exists(os.path.join(app.static_folder, post_to_delete.path)):
                os.remove(os.path.join(app.static_folder, post_to_delete.path))
                app.logger.info(f"Local file {post_to_delete.path} deleted.")

            if post_to_delete.status == "scheduled" and post_to_delete.task_id:
                celery.control.revoke(post_to_delete.task_id, terminate=True)
                app.logger.info(f"Revoke Celery task {post_to_delete.task_id} for delete post {post_id}")

            if post_to_delete.status == "success" and post_to_delete.instagram_post_id:
                delete_instagram_post.apply_async(
                    args=[post_to_delete.instagram_post_id, current_user_obj.username_insta,
                          current_user_obj.password_insta]
                )
                app.logger.info(f"Scheduled deletion of Instagram post {post_to_delete.instagram_post_id}.")

            db.session.delete(post_to_delete)
            db.session.commit()

            app.logger.info(f"post {post_id} deleted by user {user_id}")
            return {"message": "post deleted successfully"}, 200

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"error deleting post {post_id}: {str(e)}")
            return {"message": f"error deleting post {post_id}: {str(e)}"}, 400


class UserPostEdit(Resource):
    """
    this route is for editing the posts
    """

    method_decorators = {
        'put': [jwt_required()]
    }

    def put(self, post_id):
        user_id = get_jwt_identity()
        current_user_obj = Users.query.get(user_id)

        if not current_user_obj:
            return {"message": "user not found"}, 404

        post_to_edit = Post_insta.query.filter_by(id=post_id, user_id=user_id).first()

        if not post_to_edit:
            return {"message": "no post found to edit"}, 403

        data = request.form
        file = request.files.get("photo")

        needs_reschedule = False
        old_instagram_post_id = None

        if file and allowed_file(file.filename):
            if post_to_edit.path and os.path.exists(os.path.join(app.static_folder, post_to_edit.path)):
                os.remove(os.path.join(app.static_folder, post_to_edit.path))
                app.logger.info(f"Removed old image: {post_to_edit.path}")

            filename = secure_filename(file.filename)
            upload_folder = os.path.join(app.static_folder, 'uploads')
            new_relative_path = os.path.join('uploads', filename)
            new_full_path = os.path.join(app.static_folder, new_relative_path)

            try:
                file.save(new_full_path)
                post_to_edit.path = new_relative_path
                needs_reschedule = True

                app.logger.info(f"new image saved for post {post_id}: {new_full_path}")

            except Exception as e:
                return {"message": f"error saving the edited photo: {str(e)}"}, 400

        elif file:  # file exists but not allowed
            return {"message": "Invalid file type for photo"}, 400

        if "caption" in data and data["caption"] is not None and data["caption"] != post_to_edit.caption:
            post_to_edit.caption = data["caption"]
            needs_reschedule = True

        jalali_date = data.get("jalali_date")
        time_str = data.get("schedule_time")
        new_schedule_time = None

        if jalali_date and time_str:
            try:
                new_schedule_time = convert_jalali_to_gregorian(jalali_date, time_str)
                if post_to_edit.schedule_time != new_schedule_time:
                    post_to_edit.schedule_time = new_schedule_time
                    needs_reschedule = True
            except Exception as e:
                return {"message": f"Invalid date or time format: {str(e)}"}, 400
        elif (jalali_date and not time_str) or (not jalali_date and time_str):
            return {"message": "Both 'jalali_date' and 'schedule_time' must be provided to update schedule."}, 400

        try:
            if needs_reschedule:
                if post_to_edit.task_id and post_to_edit.status == "scheduled":
                    celery.control.revoke(post_to_edit.task_id, terminate=True)
                    app.logger.info(f"Revoked old Celery task {post_to_edit.task_id} for post {post_id}")

                if post_to_edit.status == "success" and post_to_edit.instagram_post_id:
                    old_instagram_post_id = post_to_edit.instagram_post_id
                    delete_instagram_post.apply_async(
                        args=[old_instagram_post_id, current_user_obj.username_insta, current_user_obj.password_insta]
                    )
                    app.logger.info(
                        f"Scheduled deletion of old Instagram post {old_instagram_post_id} for post {post_id}.")
                    post_to_edit.instagram_post_id = None  # Clear old Instagram ID

                # Schedule a new upload task
                if post_to_edit.path and post_to_edit.caption and post_to_edit.schedule_time:
                    new_task = upload_to_instagram.apply_async(
                        args=[post_to_edit.path, post_to_edit.caption, current_user_obj.username_insta,
                              current_user_obj.password_insta],
                        eta=post_to_edit.schedule_time,
                    )
                    post_to_edit.task_id = new_task.id
                    post_to_edit.status = "scheduled"
                    app.logger.info(f"New Celery task {new_task.id} scheduled for post {post_id}")
                else:
                    return {"message": "Cannot reschedule post: missing image, caption or schedule time."}, 400

            db.session.commit()
            app.logger.info(f"Post {post_id} updated by user {user_id}")
            return {"message": "Post updated successfully", "post": post_to_edit.to_json()}, 200
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating post {post_id}: {str(e)}")
            return {"message": f"Error updating post: {str(e)}"}, 400


class UserLogout(Resource):
    """
    logout route
    """

    method_decorators = {
        'post': [jwt_required()],
    }

    def post(self):
        response = make_response({"message": "you are logged out"}, 200)

        unset_jwt_cookies(response)
        app.logger.info("user logged out")
        return response


# api routes
api.add_resource(UserRegister, '/')
api.add_resource(UserLogin, '/login')
api.add_resource(UserLogout, '/logout')
# api.add_resource(UserDashboard, '/dashboard')
api.add_resource(UserDashboard, '/<string:user_name>/dashboard')
api.add_resource(UserHistory, '/<string:user_name>/history')
api.add_resource(UserPostDelete, '/<int:post_id>/delete')
api.add_resource(UserPostEdit, '/<int:post_id>/edit')


@app.errorhandler(JWTExtendedException)
def handle_jwt_errors(e):
    return jsonify({"message": str(e)}), 401


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)
