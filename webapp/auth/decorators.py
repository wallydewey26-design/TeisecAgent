from functools import wraps
from flask import session, redirect, url_for, request


def login_required(f):
    """Decorator that requires the user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session:
            # Store the intended destination server-side so the login route
            # never has to trust user-supplied redirect values.
            session['login_next'] = request.path
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    """Decorator that requires the user to have a specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session:
                session['login_next'] = request.path
                return redirect(url_for('main.login'))
            from .credentials import get_permissions
            if permission not in get_permissions(session['role']):
                return ('Forbidden: your role does not have permission to access this resource.', 403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
